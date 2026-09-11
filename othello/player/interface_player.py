"""Interface Player."""

from abc import ABC
from abc import abstractmethod


class Player(ABC):
    """Abstract interface representing a Player in the Othello game.

    A player could be a real human interacting via CLI/GUI or
    an Artificial Intelligence.

    """

    def __init__(self, color: str):
        """Initialize the player with their assigned color.

        :param color: 'X' for Black, 'O' for White.

        """
        self.color = color

    @abstractmethod
    def get_move(self, game_state, view=None) -> str:
        """Get the next move for the player.

        :param game_state: The current state of the game.
        :param view: The interface view (useful for prompting a real player).
        :return: A string representing the player's move or command.

        """
