"""Game Client Module (TCP Socket Client)."""

import queue
import socket
import threading
import time

from othello.common.i18n_manager import I18nManager
from othello.player.network_player import NetworkPlayer
from othello.player.real_player import RealPlayer


def _(message):
    return I18nManager().gettext(message)


class GameClient:
    """Handles TCP outbound connections to a GameServer.

    Runs a background listener thread that pushes incoming commands to a queue.

    """

    def __init__(self, ip: str, port: int = 12345):
        self.ip = ip
        self.port = port
        self.socket = None
        self.is_connected = False
        self.listen_thread = None

        self.message_queue = queue.Queue()
        self.game_session = None

        self.client_id = None

    def join(self):
        """Attempts to connect to the given IP and port."""
        if self.is_connected:
            print(
                _(
                    "Disconnecting from previous server before "
                    "joining new one..."
                )
            )
            self.quit()

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.ip, self.port))
            self.is_connected = True
            print(
                _("Connected to {ip}:{port}!").format(
                    ip=self.ip, port=self.port
                )
            )

            # background listener
            self.listen_thread = threading.Thread(
                target=self._listen_loop, daemon=True
            )
            self.listen_thread.start()

            # Trigger reconnection if we previously had an ID
            if self.client_id:
                print(
                    _("Attempting to reconnect as {id}...").format(
                        id=self.client_id
                    )
                )
                self.send_message(f"RECONNECT {self.client_id}")
            else:
                self.send_message("CONNECT")

            return True
        except Exception as e:
            print(
                _("Failed to connect to {ip}:{port}: {error}").format(
                    ip=self.ip, port=self.port, error=e
                )
            )
            if self.socket:
                self.socket.close()
                self.socket = None
            return False

    def get_server_status(self) -> str:
        """Returns the status of the connection."""
        if self.is_connected:
            return _("Client: Connected to {ip}:{port}").format(
                ip=self.ip, port=self.port
            )
        return _("Client: Not connected")

    def send_message(self, msg: str):
        """Sends a generic string message to the server."""
        if not self.is_connected:
            return
        try:
            self.socket.sendall(f"{msg}\n".encode("utf-8"))
        except Exception as e:
            print(_("Error sending message: {error}").format(error=e))
            self.quit()

    def ping(self):
        """Sends a PING message to the server."""
        if not self.is_connected:
            print(_("Cannot ping: Not connected."))
            return
        self.send_message("PING")

    def quit(self):
        """Sends a QUIT message and closes the socket gracefully."""
        if not self.is_connected:
            return

        self.is_connected = False

        time.sleep(0.1)

        try:
            if self.socket:
                self.socket.settimeout(0.5)
                self.socket.sendall("QUIT\n".encode("utf-8"))
                # Give server time to process the quit message
                try:
                    self.socket.recv(1024)
                except (socket.timeout, OSError):
                    pass
        except OSError:
            pass

        try:
            if self.socket:
                self.socket.close()
        except OSError:
            pass
        finally:
            self.socket = None

        print(_("Disconnected from server."))

    def _listen_loop(self):
        """Background thread listening for server messages."""
        self.socket.settimeout(1.0)

        while self.is_connected:
            try:
                if not (data := self.socket.recv(1024)):
                    self._handle_disconnect()
                    break

                messages = data.decode("utf-8").strip().split("\n")
                for msg in messages:
                    if msg:
                        text = msg.strip()
                        # Internal state management for YOUR_ID and NAME_OK
                        if text.startswith("YOUR_ID "):
                            new_id = text[8:].strip()
                            self.client_id = new_id
                            if self.game_session:
                                self.game_session.last_client_id = new_id
                        elif text.startswith("NAME_OK "):
                            new_id = text[8:].strip()
                            self.client_id = new_id
                            if self.game_session:
                                self.game_session.last_client_id = new_id
                        elif text.startswith("SYNC_BOARD "):
                            if self.game_session:
                                self.game_session.sync_board(text[11:].strip())

                        self.message_queue.put(text)

            except socket.timeout:
                continue
            except ConnectionResetError:
                self._handle_disconnect()
                break
            except OSError:
                if self.is_connected:
                    self._handle_disconnect()
                break

        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None

    def _handle_disconnect(self):
        """Handles the disconnection logic.

        Notifies the main thread via the queue.
        """
        if not self.is_connected:
            return
        self.is_connected = False
        self.message_queue.put("__DISCONNECTED__")

    def _setup_network_game(self, local_role: str):
        """Configures GameSession players for network multiplayer."""
        if not self.game_session:
            return

        # board  refresh and reset game session
        self.game_session.reset_game({})

        # who is who
        remote_role = "O" if local_role == "X" else "X"

        # Local keyboard input for chosen role
        self.game_session.players[local_role] = RealPlayer(local_role)

        # Queue-based NetworkPlayer for the remaining role
        net_player = NetworkPlayer(remote_role, self.message_queue)
        net_player.game_session = self.game_session
        self.game_session.players[remote_role] = net_player
