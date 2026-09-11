"""Network Player Module."""

import queue
import select
import sys

from othello.common.i18n_manager import I18nManager
from othello.player.interface_player import Player


def _(message):
    return I18nManager().gettext(message)


class NetworkPlayer(Player):
    """Network Player implementation of the Player interface.

    Represents an opponent interacting through a GameClient socket.

    """

    def __init__(self, color: str, message_queue: queue.Queue):
        super().__init__(color)
        self.message_queue = message_queue

    def get_move(self, game_state, view=None) -> str:
        """Retrieves the next move by listening to the client message queue.

        Blocks until the remote server sends a MOVE.

        """
        if view:
            view.display_message(
                _("Waiting for remote player ({color}) to move...").format(
                    color=self.color
                )
            )
        while True:
            try:
                # check from remote server
                msg = self.message_queue.get(timeout=0.1)

                if msg.startswith("OPPONENT_MOVE "):
                    move_str = msg[14:].strip()
                    if view:
                        view.display_message(
                            _("Remote player chose: {move}").format(
                                move=move_str
                            )
                        )
                    return move_str
                elif msg == "QUIT" or msg.startswith("ERROR"):
                    if view:
                        view.display_error(
                            _("Network error/quit: {msg}").format(msg=msg)
                        )
                    return "quit"
                elif "win by forfeit" in msg:
                    if view:
                        view.display_message(msg)
                    if getattr(self, "game_session", None):
                        self.game_session.reset_game({})
                    return "show history"  # innocuous command to continue loop
                else:
                    # messages goes trhought the handle in game session
                    if self.game_session:
                        self.game_session.handle_network_message(msg)
                    elif view:
                        view.display_message(msg)

            except queue.Empty:
                pass
            except KeyboardInterrupt:
                return "quit"

            # check if there is any local command
            local_input = None

            # check input_queue for the gui
            if hasattr(view, "input_queue"):
                try:
                    local_input = view.input_queue.get_nowait()
                except queue.Empty:
                    pass
            # check stdin using select for the cli
            elif sys.stdin.isatty():
                r, x, y = select.select([sys.stdin], [], [], 0.0)
                if r:
                    local_input = sys.stdin.readline().strip()

            if local_input:
                # anti bypass: don't allow typing a move for the remote player
                parts = local_input.strip().split()
                if len(parts) >= 2:
                    color_candidate = parts[0].upper()
                    if color_candidate == self.color:
                        if view:
                            view.display_error(
                                _(
                                    "Cannot play for remote player ({color})!"
                                ).format(color=self.color)
                            )
                        continue
                    if color_candidate in ("X", "O"):
                        if view:
                            view.display_error(_("It is not your turn."))
                        continue

                return local_input
