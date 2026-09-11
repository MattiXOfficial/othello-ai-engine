"""Contest Controller Module."""

import sys

from othello.common.i18n_manager import I18nManager
from othello.orchestrator.interface_gamemode import GameMode
from othello.player.ai_player import AIPlayer


def _(message):
    return I18nManager().gettext(message)


class ContestMode(GameMode):
    """Contest Mode Class.

    Read a state, compute the best move, display & quit.
    """

    def __init__(self, session):
        self.session = session

    def start(self):
        """Evaluate the board, display the move on stdout & quit."""
        # On vérifie qu'un fichier a bien été passé et chargé
        if not self.session.settings.get("input_file"):
            print(
                _("Error : Contest mode needs a file in arg."),
                file=sys.stderr,
            )
            sys.exit(1)
        ai = AIPlayer(self.session.current_player)

        try:
            move = ai.get_move(self.session.game_state, self.session.view)
            print(move)
            sys.exit(0)
        except Exception as e:
            print(
                _("Error while computing contest move : {error}").format(
                    error=e
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    def handle_turn(self, player, move):
        """Not used in contest mode."""

    def check_end_condition(self, current_player):
        """Not used in contest mode."""
        return False
