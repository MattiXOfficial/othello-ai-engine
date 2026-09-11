"""Game Server Module."""

import queue
import socket
import threading
import time

from othello.common.i18n_manager import I18nManager
from othello.network.discovery_service import DiscoveryService
from othello.network.game_router import GameRouter
from othello.network.player_manager import PlayerManager


def _(message):
    return I18nManager().gettext(message)


class GameServer:
    """Handles TCP incoming connections for the dedicated game server.

    Accepts multiple clients via multithreading. Delegates state tracking to
    PlayerManager and matchmaking to GameRouter.

    """

    TIMEOUT = 60  # seconds

    def __init__(
        self,
        port: int = 12345,
        server_name: str = "OthelloServer",
        log_queue: queue.Queue = None,
    ):
        self.port = port
        self.server_name = server_name
        self.log_queue = log_queue
        self.server_socket = None
        self.message_queue = queue.Queue()

        self.is_running = False
        self.server_thread = None

        self.discovery = DiscoveryService(
            server_name=self.server_name, tcp_port=self.port
        )

        self.discovery = DiscoveryService(
            server_name=self.server_name, tcp_port=self.port
        )
        self.player_manager = PlayerManager(self)
        self.game_router = GameRouter(self)

    def _log(self, message: str):
        """Logs a message to the queue or prints to console."""
        if self.log_queue:
            self.log_queue.put(message)
        else:
            print(message)

    def start_server(self, is_daemon: bool = True):
        """Starts the TCP server and the UDP discovery service."""
        if self.is_running:
            self._log(_("Server is already running."))
            return

        try:
            self.server_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            )
            self.server_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
            )
            self.server_socket.bind(("", self.port))
            self.server_socket.listen(10)
            self.server_socket.settimeout(1.0)
        except Exception as e:
            self._log(
                _("Failed to start server on port {port}: {error}").format(
                    port=self.port, error=e
                )
            )
            return

        self.is_running = True
        self.discovery.start_broadcasting()

        self.server_thread = threading.Thread(
            target=self._accept_loop, daemon=is_daemon
        )
        self.server_thread.start()

        # Start timeout checker thread
        threading.Thread(target=self._check_timeouts_loop, daemon=True).start()

        self._log(
            _(
                "GameServer started on port {port}. "
                "Listening for connections..."
            ).format(port=self.port)
        )

    def stop_server(self):
        """Stops the server, disconnects clients, and stops discovery."""
        self.is_running = False
        if self.discovery:
            self.discovery.stop_broadcasting()

        with self.player_manager.lock:
            for conn in list(self.player_manager.players_by_conn.keys()):
                try:
                    conn.sendall("QUIT\n".encode("utf-8"))
                    conn.close()
                except Exception:
                    pass
            self.player_manager.players_by_conn.clear()

        with self.game_router.lock:
            self.game_router.games.clear()

        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

        self._log(_("GameServer stopped."))

    def _accept_loop(self):
        """Thread loop that accepts new clients."""
        while self.is_running:
            try:
                conn, addr = self.server_socket.accept()
                threading.Thread(
                    target=self._handle_client, args=(conn, addr), daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle_client(self, conn, addr):
        """Thread method to handle a single client's network traffic."""
        ghost_info = self.player_manager._remove_ghost_connection(addr)

        if ghost_info and ghost_info.get("game_id"):
            self.game_router.handle_sudden_disconnect(ghost_info)

        # Assign a temporary ID until they authenticate or CONNECT
        temp_id = f"Temp_{id(conn)}"
        self.player_manager._add_player(conn, addr, temp_id=temp_id)

        while self.is_running:
            try:
                data = conn.recv(1024)
                if not data:
                    break

                self.player_manager._update_activity(conn)

                messages = data.decode("utf-8").strip().split("\n")
                for msg in messages:
                    if msg:
                        self._process_message(conn, msg.strip())
            except OSError:
                break

        self._disconnect_client(conn)

    def _process_message(self, conn, msg: str):
        """Delegates a single message from a client to the manager."""
        client_info = self.player_manager._get_player(conn)
        if not client_info:
            return

        # convert the command for case sensitive
        parts = msg.strip().split(" ", 1)
        command = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if command == "PING":
            self._send(conn, "PONG")
        elif command == "CONNECT":
            if client_info["id"].startswith("Temp_"):
                new_id = self.player_manager._generate_new_id()
                self.player_manager._update_player_id(conn, new_id)
                self._log(
                    _("Client connected from {addr} as {player_id}").format(
                        addr=client_info["addr"], player_id=new_id
                    )
                )
                self._send(conn, f"YOUR_ID {new_id}")
                self._send(
                    conn,
                    f"INFO Welcome {new_id}! You are in the lobby. "
                    "Type 'players' to see players.",
                )
        elif command == "QUIT":
            self._disconnect_client(conn)
        elif command == "SERVER_STATUS":
            raw = self.get_server_status()
            self._send_prefixed_list(conn, "SERVER_STATUS", raw)
        elif command == "PLAYERS":
            raw = self.player_manager._get_players_list(
                args.strip() if args else None
            )
            self._send_prefixed_list(conn, "PLAYERS_LIST", raw)
        elif command == "ACCEPT":
            self.game_router.handle_accept_request(conn)
        elif command == "DECLINE":
            self.game_router.handle_decline_request(conn)
        elif command == "CANCEL":
            self.game_router.handle_cancel_request(conn)
        elif command in ("AWAY", "BACK"):
            game_id = client_info.get("game_id")
            if game_id:
                with self.game_router.lock:
                    self.game_router.games.pop(game_id, None)

                opponent_conn = client_info.get("opponent")
                with self.player_manager.lock:
                    client_info["game_id"] = None
                    client_info["opponent"] = None
                    client_info["color"] = None

                if opponent_conn:
                    opp_info = self.player_manager._get_player(opponent_conn)
                    if opp_info and opp_info.get("game_id") == game_id:
                        with self.player_manager.lock:
                            opp_info["game_id"] = None
                            opp_info["opponent"] = None
                            opp_info["color"] = None

            if command == "AWAY":
                self.player_manager._set_status(conn, "away")
                self._log(
                    _("Player {id} is now away.").format(id=client_info["id"])
                )
                self._send(conn, "INFO You are now away.")
            else:
                self.player_manager._set_status(conn, "idle")
                self._log(
                    _("Player {id} is back.").format(id=client_info["id"])
                )
                self._send(conn, "INFO You are back.")
        elif command == "WAITGAME":
            status_msg = self.game_router.get_wait_status(conn)
            self._send(conn, status_msg)
        elif command == "SCOREBOARD":
            raw = self.player_manager._get_scoreboard()
            self._send_prefixed_list(conn, "SCOREBOARD", raw)
        elif command == "NEW" and args:
            self.game_router.handle_new_game_request(conn, args.strip())
        elif command == "RECONNECT" and args:
            player_id = args.strip()
            if self.player_manager._reconnect_player(
                conn,
                self.player_manager._get_player(conn).get("addr"),
                player_id,
            ):
                info = self.player_manager._get_player(conn)
                if info:
                    actual_id = info["id"]
                    self._send(conn, f"YOUR_ID {actual_id}")
                    if info.get("status") == "ingame":
                        self.game_router.handle_reconnect(conn, info)
                    else:
                        self._send(
                            conn,
                            f"INFO Welcome {actual_id}! "
                            "Reconnection successful.",
                        )
            else:
                self._send(conn, "ERROR Reconnection failed.")
                if client_info["id"].startswith("Temp_"):
                    new_id = self.player_manager._generate_new_id()
                    self.player_manager._update_player_id(conn, new_id)
                    self._send(conn, f"YOUR_ID {new_id}")
                    self._send(
                        conn, f"INFO Welcome {new_id}! You are in the lobby."
                    )
        elif command == "MOVE" and args:
            self.game_router.process_move(conn, args.strip(), client_info)
        elif command == "NAME" and args:
            old_id = client_info["id"]
            success, result = self.player_manager._update_player_id(
                conn, args.strip()
            )
            if success:
                self._send(conn, f"NAME_OK {result}")
                self._log(
                    _("Player {old_id} changed name to {result}").format(
                        old_id=old_id, result=result
                    )
                )
                with self.player_manager.lock:
                    for c in self.player_manager.players_by_conn:
                        if c != conn:
                            self._send(
                                c,
                                f"INFO Player {old_id} changed their "
                                f"name to {result}.",
                            )
            else:
                self._send(conn, f"ERROR {result}")
        elif command == "ABANDON":
            self.game_router.handle_abandon_request(conn)
        else:
            self._send(conn, f"ERROR Unknown command: {msg}")

    def _send_prefixed_list(self, conn, prefix: str, raw_content: str):
        """Helper to send a multi-line response where each line is prefixed.

        :param conn: The socket connection to send to.
        :param prefix: The string prefix for each line.
        :param raw_content: The multi-line string content.
        """
        if not raw_content:
            return
        prefixed = "\n".join(
            f"{prefix} {line}" for line in raw_content.split("\n")
        )
        self._send(conn, prefixed)

    def _send(self, conn, msg: str):
        """Helper to send string messages over the connection."""
        try:
            conn.sendall((msg + "\n").encode("utf-8"))
        except OSError:
            self._disconnect_client(conn)

    def _disconnect_client(self, conn):
        """Cleans up a client connection by alerting the router and manager."""
        client_info = self.player_manager._get_player(conn)
        status = client_info.get("status") if client_info else None

        if client_info:
            self._log(
                _("Client {id} disconnected.").format(id=client_info["id"])
            )
            if status == "ingame":
                info = self.player_manager._mark_disconnected(conn)
                if info:
                    self.game_router.handle_sudden_disconnect(info)
            elif status == "waitgame":
                self.game_router.handle_sudden_disconnect(
                    client_info, conn=conn
                )
                self.player_manager._remove_player(conn)
            else:
                self.player_manager._remove_player(conn)

        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass

    def _check_timeouts_loop(self):
        """Periodically disconnects silent clients.

        This prevents ghost connections.
        """
        while self.is_running:
            try:
                inactive_conns = self.player_manager._get_inactive_conns(
                    timeout_seconds=300
                )
                for conn in inactive_conns:
                    self._log(_("Disconnecting client due to timeout."))
                    self._send(conn, "ERROR Connection timed out.")
                    self._disconnect_client(conn)

                timed_out_players = (
                    self.player_manager._check_disconnection_timeouts(
                        timeout_seconds=self.TIMEOUT
                    )
                )
                for info in timed_out_players:
                    self._log(
                        _(
                            "Player {id} 60s reconnection window " "expired."
                        ).format(id=info["id"])
                    )
                    self.game_router.handle_disconnect_timeout(info)

                self.game_router.check_invitation_timeouts()

            except Exception:
                pass
            time.sleep(10)

    def get_server_status(self) -> str:
        """Returns string representation of the current server load."""
        with self.player_manager.lock:
            num_clients = len(self.player_manager.players_by_conn)
        with self.game_router.lock:
            num_games = len(self.game_router.games)

        status = [
            _("--- {name} Status ---").format(name=self.server_name),
            _("Port: {port}").format(port=self.port),
            _("Connected Clients: {num}").format(num=num_clients),
            _("Active Games: {num}").format(num=num_games),
        ]
        return "\n".join(status)
