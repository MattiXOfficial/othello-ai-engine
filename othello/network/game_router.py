"""Game Router Module (Refactored)."""

from typing import TYPE_CHECKING

import threading
import time
import uuid

from othello.common.i18n_manager import I18nManager
from othello.game_engine.game_rules import GameRules
from othello.game_engine.game_state import GameState
from othello.orchestrator.bitboard_ops import BitboardOps

if TYPE_CHECKING:
    from othello.network.game_server import GameServer


def _(message):
    return I18nManager().gettext(message)


class GameRouter:
    """Middle-layer networking logic mapping app actions to network messages.

    Handles matchmaking, game state persistence, and move validation.

    """

    def __init__(self, game_server: "GameServer"):
        self.server = game_server
        self.lock = threading.Lock()

        # Games dictionary: game_id -> dict
        # { 'state': GameState, 'X': conn, 'O': conn,
        # 'current_player': 'X' }
        self.games = {}

        # Invitations: invited_id -> { 'requester': conn,
        # 'expires': timestamp }
        self.pending_invitations = {}

    def handle_new_game_request(self, requester_conn, target_id: str):
        """Processes a request to start a new match.

        Matches the requester to the specified target.

        :param requester_conn: The socket connection of the challenging player.
        :param target_id: The ID of the opponent being challenged.
        """
        (
            target_conn,
            target_info,
        ) = self.server.player_manager._get_player_by_id(target_id)
        requester_info = self.server.player_manager._get_player(requester_conn)

        if not requester_info:
            return

        if requester_info.get("id") == target_id:
            self.server._send(
                requester_conn, "ERROR You are challenging yourself."
            )
            return

        if not target_info:
            self.server._send(
                requester_conn, f"ERROR Player {target_id} not found."
            )
            return

        if target_info["status"] != "idle":
            self.server._send(
                requester_conn,
                f"ERROR Player {target_id} is {target_info['status']}.",
            )
            return

        if requester_info["status"] != "idle":
            self.server._send(requester_conn, "ERROR You are not idle.")
            return

        with self.lock:
            expires = time.time() + 300  # 5 minutes
            self.pending_invitations[target_conn] = {
                "requester": requester_conn,
                "expires": expires,
            }

        with self.server.player_manager.lock:
            requester_info["status"] = "waitgame"
            target_info["status"] = "waitgame"

        self.server._send(
            requester_conn, f"INVITATION_SENT PLAYER={target_id} TIMEOUT=300s"
        )
        self.server._send(
            target_conn,
            f"INVITATION_RECEIVED FROM={requester_info['id']} EXPIRES=300s",
        )
        self.server._log(
            _("Invitation: {req} challenged {target}").format(
                req=requester_info["id"], target=target_id
            )
        )

    def handle_accept_request(self, target_conn):
        """Processes an acceptance from the invited player.

        :param target_conn: The socket connection of the invited player.
        """
        target_info = self.server.player_manager._get_player(target_conn)
        if not target_info or target_info["status"] != "waitgame":
            self.server._send(
                target_conn, "ERROR You have no pending invitation."
            )
            return

        invitation = None
        with self.lock:
            invitation = self.pending_invitations.pop(target_conn, None)

        if not invitation:
            self.server._send(
                target_conn, "ERROR Invitation expired or not found."
            )
            target_info["status"] = "idle"
            return

        requester_conn = invitation["requester"]
        requester_info = self.server.player_manager._get_player(requester_conn)

        if not requester_info:
            self.server._send(target_conn, "ERROR Requester disconnected.")
            target_info["status"] = "idle"
            return

        # Start the game
        game_id = str(uuid.uuid4())
        new_state = GameState()
        new_state.initialize_default()

        with self.lock:
            self.games[game_id] = {
                "state": new_state,
                "X": requester_conn,
                "O": target_conn,
                "current_player": "X",
            }

        with self.server.player_manager.lock:
            requester_info["status"] = "ingame"
            requester_info["opponent"] = target_conn
            requester_info["game_id"] = game_id
            requester_info["color"] = "X"

            target_info["status"] = "ingame"
            target_info["opponent"] = requester_conn
            target_info["game_id"] = game_id
            target_info["color"] = "O"

        self.server._send(requester_conn, "INVITATION_ACCEPTED")
        self.server._send(requester_conn, "STARTING_GAME")
        self.server._send(target_conn, "GAME_START")
        self.server._send(target_conn, f"OPPONENT={requester_info['id']}")

        # Backwards compatibility/standard starts
        self.server._send(requester_conn, "START X")
        self.server._send(target_conn, "START O")

    def handle_decline_request(self, target_conn):
        """Processes a refusal from the invited player.

        :param target_conn: The socket connection of the invited player.
        """
        target_info = self.server.player_manager._get_player(target_conn)
        if not target_info or target_info["status"] != "waitgame":
            self.server._send(target_conn, "ERROR No invitation to decline.")
            return

        target_id = target_info["id"]
        invitation = None
        with self.lock:
            invitation = self.pending_invitations.pop(target_conn, None)

        if invitation:
            requester_conn = invitation["requester"]
            requester_info = self.server.player_manager._get_player(
                requester_conn
            )
            if requester_info:
                self._reset_player_status(
                    requester_conn,
                    _("{target_id} declined your invitation.").format(
                        target_id=target_id
                    ),
                )

        self._reset_player_status(target_conn, _("Invitation declined."))

    def handle_cancel_request(self, requester_conn):
        """Processes a cancellation from the requester.

        :param requester_conn: The socket connection of the requester.
        """
        requester_info = self.server.player_manager._get_player(requester_conn)
        if not requester_info or requester_info["status"] != "waitgame":
            self.server._send(requester_conn, "ERROR No invitation to cancel.")
            return

        requester_id = requester_info["id"]
        target_conn = None
        with self.lock:
            for t_conn, inv in list(self.pending_invitations.items()):
                if inv["requester"] == requester_conn:
                    target_conn = t_conn
                    del self.pending_invitations[t_conn]
                    break

        if target_conn:
            self._reset_player_status(
                target_conn,
                _("{requester_id} cancelled the invitation.").format(
                    requester_id=requester_id
                ),
            )

        self._reset_player_status(requester_conn, _("Invitation cancelled."))

    def check_invitation_timeouts(self):
        """Periodic cleanup of expired invitations."""
        now = time.time()
        expired_invitations = []
        with self.lock:
            for t_conn, inv in list(self.pending_invitations.items()):
                if now > inv["expires"]:
                    expired_invitations.append((t_conn, inv["requester"]))
                    del self.pending_invitations[t_conn]

        for target_conn, requester_conn in expired_invitations:
            self._reset_player_status(target_conn, _("Invitation expired."))
            self._reset_player_status(
                requester_conn, _("Your invitation expired.")
            )

    def _reset_player_status(self, conn, message: str = None):
        """Internal helper to reset a player's status to idle and send it.

        :param conn: The socket connection of the player.
        :param message: Optional message to send.
        """
        info = self.server.player_manager._get_player(conn)
        if info:
            with self.server.player_manager.lock:
                info["status"] = "idle"
            if message:
                self.server._send(conn, f"INFO {message}")

    def get_wait_status(self, conn) -> str:
        """Returns details about the current wait state for a connection.

        :param conn: The socket connection to evaluate.
        :return: A formatted string for the INFO message.
        """
        info = self.server.player_manager._get_player(conn)
        if not info:
            return "ERROR Not connected."

        if info["status"] != "waitgame":
            return "INFO You are not currently waiting for a game."

        now = time.time()

        # Are we the invited? (conn is key in pending_invitations)
        with self.lock:
            if conn in self.pending_invitations:
                inv = self.pending_invitations[conn]
                req_conn = inv["requester"]
                req_info = self.server.player_manager.players_by_conn.get(
                    req_conn
                )
                req_id = req_info["id"] if req_info else "Unknown"
                remain = max(0, int(inv["expires"] - now))
                return (
                    f"INFO Challenged by {req_id}. "
                    f"Type 'accept' or 'decline'. "
                    f"Expires in {remain}s."
                )

            # Are we the requester? (conn is requester in any value)
            for t_conn, inv in self.pending_invitations.items():
                if inv["requester"] == conn:
                    remain = max(0, int(inv["expires"] - now))
                    t_info = self.server.player_manager.players_by_conn.get(
                        t_conn
                    )
                    t_id = t_info["id"] if t_info else "Unknown"
                    return (
                        f"INFO Waiting for {t_id} to respond. "
                        f"Expires in {remain}s."
                    )

        return (
            "INFO Your status is set to waitgame, "
            "but no active invitation was found."
        )

    def process_move(self, conn, move_str: str, client_info: dict):
        """Validates and processes an incoming move string.

        :param conn: The socket connection sending the move.
        :param move_str: The move string (e.g., 'X e4').
        :param client_info: The dictionary containing the user's metadata.
        """
        game_id = client_info.get("game_id")
        color = client_info.get("color")

        if not game_id:
            self.server._send(conn, "ERROR You are not in a game.")
            return

        with self.lock:
            game = self.games.get(game_id)
            if not game:
                self.server._send(conn, "ERROR Game not found.")
                return

            # Check turn integrity
            if game["current_player"] != color:
                self.server._send(conn, "ERROR It is not your turn.")
                return

            try:
                parsed_color, move_index = GameRules.move_parser(move_str)
            except ValueError as e:
                self.server._send(conn, f"ERROR Invalid move: {e}")
                return

            if parsed_color != color:
                self.server._send(
                    conn, f"ERROR You cannot play for {parsed_color}."
                )
                return

            state = game["state"]
            col = move_index % BitboardOps.SIZE
            row = move_index // BitboardOps.SIZE

            p_bb, o_bb = state.get_bitboards(color)

            if not GameRules.is_valid_move(p_bb, o_bb, col, row):
                self.server._send(
                    conn,
                    f"ERROR Move rejected by server (illegal): {move_str}",
                )
                return

            new_state, next_player = state.apply_move(color, move_index)
            game["state"] = new_state
            game["current_player"] = next_player

            is_over = GameRules.is_terminal_state(
                new_state.black_board, new_state.white_board
            )

        opponent_conn = client_info.get("opponent")
        if opponent_conn:
            self.server._send(opponent_conn, f"OPPONENT_MOVE {move_str}")

        if is_over:
            winner = GameRules.determine_winner(
                new_state.black_board, new_state.white_board
            )

            with self.lock:
                if game_id in self.games:
                    del self.games[game_id]

            my_id = client_info.get("id")

            if opponent_conn:
                opp_info = self.server.player_manager.players_by_conn.get(
                    opponent_conn
                )
                if opp_info:
                    opp_id = opp_info.get("id")
                    opp_color = opp_info.get("color")
                    if winner == color:
                        self.server.player_manager._update_score(
                            my_id, won=True
                        )
                        self.server.player_manager._update_score(
                            opp_id, won=False
                        )
                    elif winner == opp_color:
                        self.server.player_manager._update_score(
                            my_id, won=False
                        )
                        self.server.player_manager._update_score(
                            opp_id, won=True
                        )

                    with self.server.player_manager.lock:
                        opp_info["status"] = "idle"
                        opp_info["opponent"] = None
                        opp_info["game_id"] = None
                        opp_info["color"] = None

            with self.server.player_manager.lock:
                client_info["status"] = "idle"
                client_info["opponent"] = None
                client_info["game_id"] = None
                client_info["color"] = None

            if winner in ("X", "O"):
                msg = f"INFO Game over! Winner is {winner}."
            else:
                msg = "INFO Game over! It's a DRAW."

            self.server._send(conn, msg)
            if opponent_conn:
                self.server._send(opponent_conn, msg)

    def handle_sudden_disconnect(self, client_info: dict, conn=None):
        """Called when active player disconnects unexpectedly.

        Waits for 60s.

        :param client_info: The disconnected user's metadata.
        :param conn: The connection of the disconnected player (optional).
        """
        status = client_info.get("status")
        if status == "waitgame" and conn:
            self.handle_waitgame_disconnect(conn)
            return

        game_id = client_info.get("game_id")
        if game_id:
            opponent_conn = client_info.get("opponent")
            if opponent_conn:
                self.server._send(
                    opponent_conn,
                    "--- Opponent disconnected unexpectedly. "
                    "Waiting 60s for reconnection... ---",
                )

    def handle_waitgame_disconnect(self, conn):
        """Called when a player in 'waitgame' status disconnects.

        Cleans up any pending invitations and notifies the remaining player.
        """
        other_conn = None
        with self.lock:
            if conn in self.pending_invitations:
                inv = self.pending_invitations.pop(conn)
                other_conn = inv["requester"]
            else:
                for target_conn, inv in list(self.pending_invitations.items()):
                    if inv["requester"] == conn:
                        other_conn = target_conn
                        del self.pending_invitations[target_conn]
                        break

        if other_conn:
            self._reset_player_status(
                other_conn,
                _("The other player disconnected. Invitation cancelled."),
            )

    def handle_disconnect_timeout(self, client_info: dict):
        """Called when the 60s reconnection window expires.

        :param client_info: The metadata of the failed reconnecting user.
        """
        game_id = client_info.get("game_id")
        loser_id = client_info.get("id")
        if game_id:
            opponent_conn = client_info.get("opponent")
            self._cleanup_game(
                game_id,
                loser_id,
                opponent_conn,
                "Opponent failed to reconnect. You win by forfeit.",
            )

    def handle_abandon_request(self, conn):
        """Handles a player explicitly abandoning a match.

        :param conn: The socket connection executing the abandon.
        """
        client_info = self.server.player_manager._get_player(conn)
        if not client_info or client_info.get("status") != "ingame":
            self.server._send(conn, "ERROR You are not in a game.")
            return

        game_id = client_info.get("game_id")
        loser_id = client_info.get("id")
        opponent_conn = client_info.get("opponent")

        if game_id:
            self._cleanup_game(
                game_id,
                loser_id,
                opponent_conn,
                "Opponent abandoned the game. You win by forfeit.",
            )

        # Reset the abandoning player's status
        with self.server.player_manager.lock:
            client_info["status"] = "idle"
            client_info["opponent"] = None
            client_info["game_id"] = None
            client_info["color"] = None

    def _cleanup_game(
        self, game_id: str, loser_id: str, opponent_conn, message: str
    ):
        """Internal helper to finalize a game and update stats.

        :param game_id: The ID of the game to remove.
        :param loser_id: The ID of the player who lost (or left).
        :param opponent_conn: The connection of the remaining player.
        :param message: The message to send to the opponent.
        """
        with self.lock:
            if game_id in self.games:
                del self.games[game_id]

        if opponent_conn:
            opponent_info = self.server.player_manager._get_player(
                opponent_conn
            )
            if opponent_info:
                winner_id = opponent_info.get("id")
                self.server.player_manager._update_score(winner_id, won=True)
                self.server.player_manager._update_score(loser_id, won=False)
                with self.server.player_manager.lock:
                    opponent_info["status"] = "idle"
                    opponent_info["opponent"] = None
                    opponent_info["game_id"] = None
                    opponent_info["color"] = None
                self.server._send(opponent_conn, f"INFO {message}")

    def handle_reconnect(self, conn, client_info: dict):
        """Restores the game state for a reconnected player.

        :param conn: The new socket connection representing the player.
        :param client_info: The user's restored metadata dictionary.
        """
        game_id = client_info.get("game_id")
        color = client_info.get("color")

        if not game_id or not color:
            self.server._send(
                conn, "ERROR Incomplete game state for reconnection."
            )
            return

        with self.lock:
            game = self.games.get(game_id)
            if not game:
                self.server._send(
                    conn, "ERROR The game no longer exists (aborted)."
                )
                # Reset player status if game is lost
                with self.server.player_manager.lock:
                    client_info["status"] = "idle"
                    client_info["opponent"] = None
                    client_info["game_id"] = None
                    client_info["color"] = None
                return

            # Update the game dictionary with the new connection socket
            game[color] = conn

        # Update opponent's info with the new connection socket
        opponent_conn = client_info.get("opponent")
        if opponent_conn:
            opponent_info = self.server.player_manager._get_player(
                opponent_conn
            )
            if opponent_info:
                with self.server.player_manager.lock:
                    opponent_info["opponent"] = conn
                # Alert opponent that the player is back
                self.server._send(
                    opponent_conn,
                    "--- Opponent reconnected! Resuming game... ---",
                )

        # Tell the reconnecting client to start again
        self.server._send(conn, f"START {color}")

        # We need to send the current board state to the reconnecting client
        # We'll send a SYNC_BOARD command with the current player & bitboards
        state = game["state"]
        curr_player = game["current_player"]
        bb_black = state.black_board
        bb_white = state.white_board

        self.server._send(
            conn, f"SYNC_BOARD {curr_player} {bb_black} {bb_white}"
        )
