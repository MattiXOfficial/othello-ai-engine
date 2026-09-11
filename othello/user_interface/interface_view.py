"""View Interface."""

from abc import ABC
from abc import abstractmethod


class InterfaceView(ABC):
    """Abstract class defining the contract for any user interface.

    This can be a CLI or GUI.
    """

    @abstractmethod
    def start(self):
        """Initialize the view (e.g. welcome message, graphical setup)."""

    @abstractmethod
    def render(
        self,
        board_str: str,
        legal_moves: int = 0,
        current_player: str = "X",
        unsaved_changes: bool = False,
    ):
        """Display the current state of the board.

        :param board_str: The string representing the current board.
        :param legal_moves: Bitboard of legal moves for the current player.
        :param current_player: The player whose turn it is.
        :param unsaved_changes: Whether there are unsaved changes.

        """

    @abstractmethod
    def get_input(self, prompt: str = "") -> str:
        """Get the user action/command.

        :param prompt: Optional message to display to the user.
        :return: The string entered by the user.

        """

    @abstractmethod
    def display_message(self, message: str):
        """Display a simple information message.

        :param message: The text to display.

        """

    @abstractmethod
    def display_error(self, message: str):
        """Display an error message.

        :param message: The error text to display.

        """

    @abstractmethod
    def quit(self):
        """Terminate the view."""
