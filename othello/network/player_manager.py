"""Player Manager Module (Refactored)."""

import threading
import time

from othello.common.i18n_manager import I18nManager


def _(message):
    return I18nManager().gettext(message)


class PlayerManager:
    """Manages metadata, states, and scoreboards for network players.

    Provides thread-safe access to player status, tracking, and metrics.

    """

    def __init__(self, game_server):
        self.server = game_server
        self.lock = threading.Lock()

        # dict for players conn
        self.players_by_conn = {}

        # dict with wins, losses, played
        self.scoreboard = {}

        # track disconnected players for 60s for the reconnection window
        # { player_id: {"info": info_dict, "disconnect_time": time.time()} }
        self.disconnected_players = {}

        self.player_id_counter = 1

    def _add_player(self, conn, addr, temp_id: str = None) -> str:
        """Adds a new client connection.

        Assigns a unique permanent player ID or a temporary one.

        :param conn: The socket connection of the client.
        :param addr: The address tuple (IP, port) of the client.
        :param temp_id: Explicit temporary ID to assign (optional).
        :return: The generated or assigned player ID.
        """
        with self.lock:
            if temp_id:
                player_id = temp_id
            else:
                player_id = self._generate_new_id()

            self.players_by_conn[conn] = {
                "addr": addr,
                "last_activity": time.time(),
                "id": player_id,
                "status": "idle",
                "opponent": None,
                "game_id": None,
                "color": None,
            }
            if player_id not in self.scoreboard:
                self.scoreboard[player_id] = {
                    "wins": 0,
                    "losses": 0,
                    "played": 0,
                }
            return player_id

    def _generate_new_id(self) -> str:
        """Internal helper to generate a unique default player ID.

        :return: A string like 'Player_1'.
        """
        pid = f"Player_{self.player_id_counter}"
        self.player_id_counter += 1
        return pid

    def _remove_player(self, conn) -> str | None:
        """Removes a client connection entirely.

        :param conn: The socket connection to remove.
        :return: The player ID that was removed, or None if not found.
        """
        with self.lock:
            if conn in self.players_by_conn:
                player_id = self.players_by_conn[conn]["id"]
                del self.players_by_conn[conn]
                return player_id
            return None

    def _mark_disconnected(self, conn) -> dict | None:
        """Moves a client to the disconnected_players pool.

        This allows for potential reconnection within a grace period.

        :param conn: The socket connection of the client who disconnected.
        :return: The dictionary of player information, or None if not found.
        """
        with self.lock:
            if conn in self.players_by_conn:
                info = self.players_by_conn[conn]
                player_id = info["id"]
                # Save it keeping its ingame info intact
                self.disconnected_players[player_id] = {
                    "info": info,
                    "disconnect_time": time.time(),
                }
                del self.players_by_conn[conn]
                return info
            return None

    def _bind_player(self, conn, addr, info):
        """Internal helper to bind a connection to player info."""
        info["addr"] = addr
        info["last_activity"] = time.time()
        self.players_by_conn[conn] = info

    def _find_info_by_id(
        self, player_id: str
    ) -> tuple[str | None, dict | None, str]:
        """Internal helper to find player info by ID across all pools.

        :param player_id: The ID to search for.
        :return: A tuple (found_id, info, pool_name) where pool_name can be
            'active', 'disconnected' or 'none'.
        """
        pid_lower = player_id.lower()
        # 1. Check active
        for conn, info in self.players_by_conn.items():
            if info["id"].lower() == pid_lower:
                return info["id"], info, "active"
        # 2. Check disconnected
        for pid, record in self.disconnected_players.items():
            if pid.lower() == pid_lower:
                return pid, record["info"], "disconnected"
        return None, None, "none"

    def _reconnect_player(self, conn, addr, player_id: str) -> bool:
        """Restores a previously disconnected player."""
        pool = None
        with self.lock:
            found_id, info, pool = self._find_info_by_id(player_id)

            if pool == "disconnected":
                del self.disconnected_players[found_id]
                self._bind_player(conn, addr, info)
                return True

            if pool == "active":
                # Handle TCP race condition
                old_conn = None
                for c, inf in self.players_by_conn.items():
                    if inf["id"] == found_id:
                        old_conn = c
                        break

                if old_conn and old_conn != conn:
                    del self.players_by_conn[old_conn]
                    try:
                        old_conn.close()
                    except Exception:
                        pass
                    self._bind_player(conn, addr, info)
                    return True

        if pool == "none":
            success, _ = self._update_player_id(conn, player_id)
            return success

        return False

    def _check_disconnection_timeouts(self, timeout_seconds=60.0) -> list:
        """Returns and completely removes players who didn't reconnect.

        They are removed if they didn't reconnect in time.
        """
        timed_out_infos = []
        with self.lock:
            now = time.time()
            to_remove = []
            for pid, record in self.disconnected_players.items():
                if now - record["disconnect_time"] > timeout_seconds:
                    timed_out_infos.append(record["info"])
                    to_remove.append(pid)
            for pid in to_remove:
                del self.disconnected_players[pid]
        return timed_out_infos

    def _remove_ghost_connection(self, addr):
        """Removes an existing connection from the same IP if it was 'ingame'.

        This helps with fast reconnection in case of local network instability.

        :param addr: The address tuple of the new connection.
        :return: The info of the removed ghost connection, or None.
        """
        client_ip = addr[0]
        with self.lock:
            # Find an existing connection from the same IP
            # that is currently in a game
            target_conn = None
            ghost_info = None
            for conn, info in self.players_by_conn.items():
                if info["addr"][0] == client_ip and info["status"] == "ingame":
                    target_conn = conn
                    ghost_info = info.copy()
                    break

            if target_conn:
                del self.players_by_conn[target_conn]
                self.server._log(
                    _("Removed ghost connection for {p} ({ip})").format(
                        p=ghost_info["id"], ip=client_ip
                    )
                )
            return ghost_info

    def _get_player(self, conn) -> dict | None:
        """Returns the dictionary info for a given connection.

        :param conn: The socket connection of the client.
        :return: The player information dict, or None if not found.
        """
        with self.lock:
            return self.players_by_conn.get(conn)

    def _get_player_by_id(self, target_id: str) -> tuple:
        """Finds a player connection and info by their assigned string ID.

        :param target_id: The player ID string to look for.
        :return: A tuple containing (conn, info_dict), or (None, None).
        """
        with self.lock:
            for conn, info in self.players_by_conn.items():
                if info["id"] == target_id:
                    return conn, info
            return None, None

    def _update_activity(self, conn):
        """Refreshes the last_activity timestamp for a connection."""
        with self.lock:
            if conn in self.players_by_conn:
                self.players_by_conn[conn]["last_activity"] = time.time()

    def _set_status(self, conn, status: str):
        """Updates just the status string for a given client."""
        with self.lock:
            if conn in self.players_by_conn:
                self.players_by_conn[conn]["status"] = status

    def _get_inactive_conns(self, timeout_seconds: float = 10.0) -> list:
        """Returns a list of all connections that have missed the timeout."""
        with self.lock:
            now = time.time()
            inactive = []
            for conn, info in self.players_by_conn.items():
                if (
                    info["status"] == "ingame"
                    and info["opponent"] not in self.players_by_conn
                ):
                    # Opponent is disconnected, allow more time for both
                    if now - info["last_activity"] > timeout_seconds * 2:
                        inactive.append(conn)
                else:
                    if now - info["last_activity"] > timeout_seconds:
                        inactive.append(conn)
            return inactive

    def _get_players_list(
        self, target_id: str = None, invitations: dict = None
    ) -> str:
        """Returns string representation of connected players.

        Also can return detailed info for a specific player.
        """
        with self.lock:
            if target_id:
                found_id, info, pool = self._find_info_by_id(target_id)
                if pool != "active":
                    return "ERROR " + _(
                        "Player {target_id} not found or not active."
                    ).format(target_id=target_id)

                stats = self.scoreboard.get(
                    info["id"], {"wins": 0, "losses": 0, "played": 0}
                )
                return _(
                    "--- Player Info: {id} ---\n"
                    "Status: {status}\n"
                    "Score: {wins} Wins, {losses} Losses "
                    "({played} Played)"
                ).format(
                    id=info["id"],
                    status=info["status"],
                    wins=stats["wins"],
                    losses=stats["losses"],
                    played=stats["played"],
                )

            if not self.players_by_conn:
                return _("No players connected.")

            lines = [_("Connected Players:")]
            if invitations is None:
                invitations = (
                    getattr(
                        self.server, "game_router", None
                    ).pending_invitations
                    if hasattr(self, "server")
                    and hasattr(self.server, "game_router")
                    else {}
                )

            for conn, info in self.players_by_conn.items():
                p_id = info["id"]
                status = info["status"]
                detail = ""
                if status == "waitgame" and invitations:
                    # Look for details
                    if conn in invitations:
                        req_conn = invitations[conn]["requester"]
                        req_info = self.players_by_conn.get(req_conn)
                        if req_info:
                            detail = _(" (challenged by {req_id})").format(
                                req_id=req_info["id"]
                            )
                    else:
                        for t_conn, inv in invitations.items():
                            if inv["requester"] == conn:
                                t_info = self.players_by_conn.get(t_conn)
                                t_id = t_info["id"] if t_info else "Unknown"
                                detail = _(" (waiting for {t_id})").format(
                                    t_id=t_id
                                )
                                break

                lines.append(f"- {p_id} [{status}]{detail}")
            return "\n".join(lines)

    def _get_scoreboard(self) -> str:
        """Returns string representation of scoreboard."""
        with self.lock:
            if not self.scoreboard:
                return _("No stats available.")

            lines = [_("--- Scoreboard ---")]
            for p_id, stats in self.scoreboard.items():
                w, l, p = stats["wins"], stats["losses"], stats["played"]
                lines.append(
                    _("{p_id}: {w} Wins, {l} Losses ({p} Played)").format(
                        p_id=p_id, w=w, l=l, p=p
                    )
                )
            return "\n".join(lines)

    def _update_score(self, player_id: str, won: bool):
        """Updates the game results counting for a specific player ID."""
        with self.lock:
            if player_id in self.scoreboard:
                self.scoreboard[player_id]["played"] += 1
                if won:
                    self.scoreboard[player_id]["wins"] += 1
                else:
                    self.scoreboard[player_id]["losses"] += 1

    def _update_player_id(self, conn, new_id: str) -> tuple[bool, str]:
        """Updates the player's ID to a new one.

        Ensures uniqueness (case-insensitive) and moves scoreboard data.

        :param conn: The socket connection linking the player.
        :param new_id: The desired new player ID.
        :return: A tuple of (Success: bool, ErrorMessage_or_NewID: str).
        """
        if not new_id:
            return False, ("Pseudo cannot be empty.")

        with self.lock:
            if conn not in self.players_by_conn:
                return False, ("Player not found.")

            current_info = self.players_by_conn[conn]
            old_id = current_info["id"]

            if old_id == new_id:
                return True, new_id

            found_id, _info, pool = self._find_info_by_id(new_id)
            if pool == "active":
                return (
                    False,
                    _("This name is already taken by a connected player."),
                )
            if pool == "disconnected":
                return False, _(
                    "This name is reserved by a disconnected player."
                )

            # recup la valeur associé avec pop pour la merge apres
            old_stats = self.scoreboard.pop(
                old_id, {"wins": 0, "losses": 0, "played": 0}
            )

            # merges old and new ids together
            if new_id in self.scoreboard:
                existing_stats = self.scoreboard[new_id]
                self.scoreboard[new_id] = {
                    "wins": existing_stats["wins"] + old_stats["wins"],
                    "losses": (existing_stats["losses"] + old_stats["losses"]),
                    "played": (existing_stats["played"] + old_stats["played"]),
                }
            else:
                self.scoreboard[new_id] = old_stats

            # Update connection info
            current_info["id"] = new_id
            return True, new_id
