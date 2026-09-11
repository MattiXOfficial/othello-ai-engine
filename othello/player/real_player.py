"""Real Player Module."""

from othello.common.i18n_manager import I18nManager
from othello.player.interface_player import Player


# Initialisation du manager et assignation de la fonction à '_'
def _(message):
    return I18nManager().gettext(message)


class RealPlayer(Player):
    """Real Player implementation of the Player interface.

    Represents a human interacting via CLI or GUI.
    """

    def __init__(self, color: str):
        super().__init__(color)

    def get_move(self, game_state, view=None) -> str:
        """Prompts the real player to enter their next move or command.

        :param game_state: The current state of the game.
        :param view: The view for displaying prompts and receiving input.
        :return: A string representing the player's move or command.
        """
        prompt = _(
            "Player {player}, enter your move (e.g. {player} e4) or 'help':"
        ).format(player=self.color)
        if view:
            # Here we expect the interactive input loop from view
            input_str = view.get_input(prompt)
            return input_str
        return ""
