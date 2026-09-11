"""CLI MODULE."""

import atexit
import os
import readline
import sys

from othello.common.i18n_manager import I18nManager
from othello.user_interface.interface_view import InterfaceView
from pathlib import Path


def _(message):
    return I18nManager().gettext(message)


class CLIShell(InterfaceView):
    """Console implementation of the view."""

    def __init__(self, commands):
        """Initialize the CLIShell with a list of commands for completion.

        :param commands: List of strings representing the commands to complete.

        """
        # self.config = ConfigManager().config_parser["defaults"]
        # # get the configuration

        self.commands = sorted(commands)
        self.hist_file = Path.home() / ".othello_history"
        try:
            readline.read_history_file(str(self.hist_file))
            readline.set_history_length(1000)
        except OSError:
            pass
        readline.set_completer(self.complete)
        if "libedit" in readline.__doc__:
            # Syntaxe pour macOS
            readline.parse_and_bind("bind ^I rl_complete")
            readline.parse_and_bind("bind + em-inc-search-prev")
        else:
            # Syntaxe pour Linux
            readline.parse_and_bind("tab: complete")
            readline.parse_and_bind('"+": reverse-search-history')
        atexit.register(readline.write_history_file, str(self.hist_file))

        # Ensure that ambiguous matches ring bell (or flash) first, then list
        # on second tab
        # This is usually the default behavior for GNU readline,
        # but setting 'show-all-if-ambiguous' to 'off' enforces the
        # "second tab" requirement.
        readline.parse_and_bind("set show-all-if-ambiguous off")

    def start(self):
        """Start the CLI interface.

        Clears the terminal and shows a welcome message.
        """
        # self.clear_terminal()
        print(_("=== Othello CLI Started ==="))

    def clear_terminal(self):
        """Clear the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def render(
        self,
        board_str: str,
        legal_moves: int = 0,
        current_player: str = "X",
        unsaved_changes: bool = False,
    ):
        """Display the current state of the board.

        :param board_str: The string representing the current board.
        :param legal_moves: Bitboard of legal moves.
        :param current_player: The current player.
        :param unsaved_changes: Whether there are unsaved changes.

        """
        rows = board_str.split("/")
        size = len(rows)  # On déduit la taille dynamiquement grâce à la string

        unsaved_indicator = " *" if unsaved_changes else ""
        headers = " ".join([chr(ord("a") + i) for i in range(size)])
        print(f"   {headers}{unsaved_indicator}")

        for i, row in enumerate(rows):
            formatted_row = " ".join(list(row))
            print(f"{i + 1:2} {formatted_row}")

    def get_input(self, prompt: str = "") -> str:
        """Get user input using the standard input() function.

        Enhanced by readline.

        :param prompt: The prompt to show to the user.
        :return: The user input string.

        """
        return input(prompt)

    def display_message(self, message: str):
        """Print a standard message to stdout.

        :param message: The message to print.

        """
        print(message)

    def display_error(self, message: str):
        """Print an error message to stderr.

        :param message: The error message.

        """
        print(_("Error : {message}").format(message=message), file=sys.stderr)

    def game_over(self, winner: str, scores: dict[str, int]):
        """Display game over message.

        :param winner: The winner of the game.
        :param scores: The final scores.
        """
        print("\n" + "=" * 30)
        print(_("       GAME OVER       "))
        print("=" * 30)
        if winner == "DRAW":
            print(_("Result: Draw!"))
        else:
            print(_("Winner: Player {winner}").format(winner=winner))

        print("-" * 30)
        print(_("Final Scores:"))
        print(_("Black (X): {score}").format(score=scores.get("X", 0)))
        print(_("White (O): {score}").format(score=scores.get("O", 0)))
        print("=" * 30 + "\n")

    def quit(self):
        """Quit the interface.

        For CLI, the loop is managed by GameSession,
        so nothing to do here.
        """

    def complete(self, text, state):
        """Completion function for readline.

        :param text: The current word being typed.
        :type text: String.
        :param state: The index of the suggestion to return.
        :type state: Int.
        :return: The suggestion string or None.

        """
        # Find matches that start with the input text
        text = text.lower()
        options = [c for c in self.commands if c.startswith(text)]
        if state < len(options):
            return options[state]
        return None
