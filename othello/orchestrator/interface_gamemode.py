"""Gamemode Interface."""

from abc import ABC
from abc import abstractmethod


class GameMode(ABC):
    """Interface for gamemodes (Blitz, Contest)."""

    @abstractmethod
    def start(self):
        """Init & start the gamemode."""

    @abstractmethod
    def handle_turn(self, player: str, move: str):
        """Handle the specific logic of the mode during the player's turn.

        :param player: The player whose turn it is.
        :param move: Move of the current player.

        """

    @abstractmethod
    def check_end_condition(self):
        """Check if end conditions of the mode are okay."""
