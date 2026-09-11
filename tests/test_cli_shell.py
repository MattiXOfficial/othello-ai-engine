from io import StringIO
from unittest.mock import patch

from othello.game_engine.game_state import GameState
from othello.user_interface.cli_shell import CLIShell
import unittest


class TestCLIShell(unittest.TestCase):
    def setUp(self):
        self.commands = ["help", "quit", "save", "load"]

        self.patcher_readline = patch(
            "othello.user_interface.cli_shell.readline"
        )
        self.mock_readline = self.patcher_readline.start()

        self.patcher_atexit = patch("othello.user_interface.cli_shell.atexit")
        self.mock_atexit = self.patcher_atexit.start()

        self.patcher_os = patch("othello.user_interface.cli_shell.os")
        self.mock_os = self.patcher_os.start()
        self.mock_os.path.expanduser.return_value = "/tmp"
        self.mock_os.path.join.side_effect = lambda *args: "/".join(args)

        self.shell = CLIShell(self.commands)

    def tearDown(self):
        # On arrête les patchs après chaque test
        self.patcher_readline.stop()
        self.patcher_atexit.stop()
        self.patcher_os.stop()

    def test_init_history(self):
        """Test the initiation of the history and bindings."""
        # Vérifie qu'on essaie de lire l'historique
        self.mock_readline.read_history_file.assert_called()
        # Vérifie qu'on a bien enregistré la sauvegarde automatique
        self.mock_atexit.register.assert_called()
        # Vérifie que le binding de la touche '+' est fait
        self.mock_readline.parse_and_bind.assert_any_call(
            '"+": reverse-search-history'
        )

    def test_completion_logic(self):
        """Test the complete method logic.

        For unique and non-existent matches.
        """
        # Test unique 'h' -> 'help'
        self.assertEqual(self.shell.complete("h", 0), "help")
        self.assertIsNone(self.shell.complete("h", 1))

        # Test 'l' -> 'load'
        self.assertEqual(self.shell.complete("l", 0), "load")

        # Test nothing matches 'z'
        self.assertIsNone(self.shell.complete("z", 0))

    def test_ambiguous_completion(self):
        """Test completion with ambiguous commands."""
        # Create a new shell instance with ambiguous commands
        commands = ["save", "save_as"]
        shell = CLIShell(commands)

        # 's' matches both 'save' and 'save_as'
        # state 0 -> 'save' (sorted first)
        self.assertEqual(shell.complete("s", 0), "save")
        # state 1 -> 'save_as'
        self.assertEqual(shell.complete("s", 1), "save_as")
        # state 2 -> None
        self.assertIsNone(shell.complete("s", 2))

    def test_completion_sorting(self):
        """Test that completion options are sorted."""
        commands = ["b_command", "a_command"]
        shell = CLIShell(commands)

        self.assertEqual(shell.commands, ["a_command", "b_command"])

    @patch("builtins.input", return_value="test_command")
    def test_read_input(self, mock_input):
        """Test read_input wrapper calls input correctly."""
        result = self.shell.get_input("prompt>")
        self.assertEqual(result, "test_command")
        mock_input.assert_called_with("prompt>")

    def test_render_board(self):
        """Test rendering the board."""
        game_state = GameState()
        # Place one black piece at A1 (index 0)
        # Place one white piece at B1 (index 1)
        game_state.black_board = 1 << 0
        game_state.white_board = 1 << 1
        board_str = game_state.get_board_as_string()
        with patch("sys.stdout", new=StringIO()) as fake:
            self.shell.render(board_str)
            output = fake.getvalue()

        # Check header
        self.assertIn("a b c d e f g h", output)
        # Check row 1
        # Expected: "1 X O _ _ _ _ _ _ "
        self.assertIn(" 1 X O _ _ _ _ _ _", output)
        # Check empty row 8
        self.assertIn(" 8 _ _ _ _ _ _ _ _", output)


if __name__ == "__main__":
    unittest.main()
