"""GUI App module — main entry point.

This module groups and re-exports all GUI classes so that tests
can import everything from `othello.user_interface.gui_app`.

"""

import os
import queue
import sys

import gi

if "sphinx" not in sys.modules:
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gio", "2.0")

import cairo

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from othello.common.config_manager import ConfigManager

# --- Re-exports of GUI classes (necessary for tests and patches) ---
from othello.user_interface.dialogs.config_dialog import ConfigDialog
from othello.user_interface.dialogs.save_dialog import SaveDialog
from othello.user_interface.dialogs.server_dialogs import HostServerDialog
from othello.user_interface.dialogs.server_dialogs import JoinServerDialog
from othello.user_interface.dialogs.server_dialogs import LobbyDialog
from othello.user_interface.interface_view import InterfaceView
from othello.user_interface.othello_window import OthelloWindow

__all__ = [
    "GUIApp",
    "OthelloWindow",
    "ConfigDialog",
    "SaveDialog",
    "HostServerDialog",
    "JoinServerDialog",
    "LobbyDialog",
    "Gtk",
    "GLib",
    "Gdk",
    "cairo",
]


class GUIApp(InterfaceView):
    """GUIApp class."""

    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.app = Gtk.Application(
            application_id="org.example.othello",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.app.connect("activate", self.on_activate)

    def on_activate(self, app):
        """Handle app activation.

        Args:
            app (Gtk.Application): The GTK application instance.

        """
        win = OthelloWindow(app, self.output_queue, self.input_queue)
        win.show_all()

    def start(self):
        """Start the GUI application."""
        is_verbose = self.config_manager.config_parser["defaults"].getboolean(
            "verbose", False
        )

        original_stderr_fd = -1
        original_stdout_fd = -1

        if not is_verbose:
            # Redirect stderr and stdout to /dev/null to hide GDK messages
            original_stderr_fd = os.dup(sys.stderr.fileno())
            original_stdout_fd = os.dup(sys.stdout.fileno())
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull_fd, sys.stderr.fileno())
            os.dup2(devnull_fd, sys.stdout.fileno())
            os.close(devnull_fd)

        try:
            # We pass only the program name to Gtk.Application.run()
            # to prevent it from parsing our application's arguments.
            sys.exit(self.app.run([sys.argv[0]]))
        finally:
            if not is_verbose:
                # Restore original stdout and stderr
                os.dup2(original_stdout_fd, sys.stdout.fileno())
                os.dup2(original_stderr_fd, sys.stderr.fileno())
                os.close(original_stdout_fd)
                os.close(original_stderr_fd)

    def render(
        self,
        board_str: str,
        legal_moves: int = 0,
        current_player: str = "X",
        unsaved_changes: bool = False,
    ):
        """Queue board rendering.

        Args:
            board_str (str): String representation of the board.
            legal_moves (int): Bitboard of legal moves.
            current_player (str): The current player ('X' or 'O').
            unsaved_changes (bool): Whether there are unsaved changes.
        """
        self.output_queue.put(
            (
                "render",
                (board_str, legal_moves, current_player, unsaved_changes),
            )
        )

    def get_input(self, prompt: str = "") -> str:
        """Get input from the GUI.

        Args:
            prompt (str): The prompt to show to the user.

        Returns:
            str: The user input.

        """
        if ("Player" in prompt or "Joueur" in prompt) and not getattr(
            self, "_board_synced", False
        ):
            self._board_synced = True
            return "show board"
        self._board_synced = False

        try:
            return self.input_queue.get_nowait()
        except queue.Empty:
            self.output_queue.put(("get_input", prompt))
            return self.input_queue.get()

    def display_message(self, message: str):
        """Queue message display.

        Args:
            message (str): The message to display.

        """
        self.output_queue.put(("display_message", message))

    def display_error(self, message: str):
        """Queue error display.

        Args:
            message (str): The error message to display.

        """
        self.output_queue.put(("display_error", message))

    def quit(self):
        """Quit the Gtk application."""
        self.output_queue.put(("quit", None))

    def game_over(self, winner: str, scores: dict[str, int]) -> str:
        """Handle game over state.

        Args:
            winner (str): The winner of the game ('X', 'O', or 'DRAW').
            scores (dict): A dictionary with the final scores for 'X' and 'O'.

        Returns:
            str: The action chosen by the user ('restart' or 'quit').

        """
        # Clear the residual command queue
        while not self.input_queue.empty():
            try:
                self.input_queue.get_nowait()
            except queue.Empty:
                break

        # Display game over popup
        self.output_queue.put(("game_over", (winner, scores)))

        # Wait for restart/quit response
        while True:
            action = self.input_queue.get()
            if action in ["restart", "quit", "lobby"]:
                return action

    def set_thinking_indicator(self, is_thinking: bool):
        """Queue the thinking indicator state change.

        Args:
            is_thinking (bool): True if the AI is thinking, False otherwise.

        """
        self.output_queue.put(("set_thinking", is_thinking))
