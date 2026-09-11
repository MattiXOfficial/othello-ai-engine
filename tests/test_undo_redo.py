import unittest
from unittest.mock import MagicMock

from othello.common.command import CommandParser
from othello.common.command import CommandType
from othello.common.command import RedoCommand
from othello.common.command import ShowCommand
from othello.common.command import UndoCommand
from othello.orchestrator.game_session import GameSession


class TestUndoRedoHistory(unittest.TestCase):
    def setUp(self):
        """Initialisation avant chaque test."""
        self.view = MagicMock()
        self.session = GameSession(self.view)
        # On s'assure que le jeu est propre
        self.session.history = []
        self.session.undo_stack = []
        self.session.redo_stack = []

    def test_register_move(self):
        """Vérifie que register_move sauvegarde bien l'état."""
        initial_black = self.session.game_state.black_board

        # 1. On joue un coup (simulation)
        move_str = "e4"
        self.session.register_move(move_str)

        # Simulation d'un changement de plateau après le register
        self.session.game_state.black_board = 99999

        # Vérifications
        self.assertEqual(len(self.session.history), 1)
        self.assertEqual(self.session.history[0], "e4")
        self.assertEqual(len(self.session.undo_stack), 1)
        # L'état sauvegardé dans la stack doit être l'original
        saved_state, _ = self.session.undo_stack[0]
        self.assertEqual(saved_state.black_board, initial_black)

    def test_simple_undo(self):
        """Vérifie l'annulation simple d'un coup."""
        # Etat initial (0)
        self.session.game_state.black_board = 10

        # Coup 1
        self.session.register_move("move1")
        self.session.game_state.black_board = 20  # État après coup 1

        # Undo
        success = self.session.undo_move(1)

        self.assertTrue(success)
        # Retour état 0
        self.assertEqual(self.session.game_state.black_board, 10)
        # Historique vide
        self.assertEqual(len(self.session.history), 0)
        # Redo contient le futur
        self.assertEqual(len(self.session.redo_stack), 1)

    def test_simple_redo(self):
        """Vérifie le rétablissement d'un coup annulé."""
        # Etat 0
        self.session.game_state.black_board = 10

        # Coup 1
        self.session.register_move("move1")
        self.session.game_state.black_board = 20

        # Undo -> Retour à 10
        self.session.undo_move(1)

        # Redo -> Retour à 20
        success = self.session.redo_move(1)

        self.assertTrue(success)
        self.assertEqual(self.session.game_state.black_board, 20)
        self.assertEqual(len(self.session.history), 1)
        self.assertEqual(self.session.history[0], "move1")
        self.assertEqual(len(self.session.redo_stack), 0)

    def test_redo_cleared_on_new_move(self):
        """Vérifie que jouer un nouveau coup efface le futur (Redo)."""
        # Coup 1
        self.session.register_move("move1")
        self.session.game_state.black_board = 20

        # Undo
        self.session.undo_move(1)
        self.assertTrue(len(self.session.redo_stack) > 0)  # Il y a un futur

        # Nouveau Coup (Bifurcation temporelle)
        self.session.register_move("move2_alternative")

        # Le Redo doit être vide
        # (on ne peut plus "redo" move1 car on a joué move2)
        self.assertEqual(len(self.session.redo_stack), 0)
        self.assertEqual(self.session.history[0], "move2_alternative")

    def test_undo_multiple(self):
        """Vérifie l'annulation de plusieurs coups d'un coup (undo 2)."""
        self.session.game_state.black_board = 0

        # Coup 1
        self.session.register_move("1")
        self.session.game_state.black_board = 1

        # Coup 2
        self.session.register_move("2")
        self.session.game_state.black_board = 2

        # Undo 2
        self.session.undo_move(2)

        self.assertEqual(self.session.game_state.black_board, 0)
        self.assertEqual(len(self.session.history), 0)

    def test_parser_undo_redo(self):
        # Test Undo simple
        cmd = CommandParser.parse("undo")
        self.assertIsInstance(cmd, UndoCommand)
        self.assertEqual(cmd.n_moves, 1)  # Défaut
        self.assertEqual(cmd.get_type(), CommandType.UNDO)

        # Test Undo avec argument
        cmd = CommandParser.parse("undo 3")
        self.assertIsInstance(cmd, UndoCommand)
        self.assertEqual(cmd.n_moves, 3)

        # Test Redo
        cmd = CommandParser.parse("redo 2")
        self.assertIsInstance(cmd, RedoCommand)
        self.assertEqual(cmd.n_moves, 2)

        # Test History
        cmd = CommandParser.parse("show history")
        self.assertIsInstance(cmd, ShowCommand)

        # Test Board
        # Test History
        cmd = CommandParser.parse("show board")
        self.assertIsInstance(cmd, ShowCommand)

    def test_undo_command_full_coverage(self):
        cmd = UndoCommand("2")

        # Getters
        self.assertEqual(cmd.get_type(), CommandType.UNDO)
        self.assertEqual(cmd.get_data(), {"n_moves": 2})

        # Execute success
        cmd.execute(self.session)
        self.view.display_message.assert_called()

    def test_redo_command_full_coverage(self):
        cmd = RedoCommand("3")

        # Getters
        self.assertEqual(cmd.get_type(), CommandType.REDO)
        self.assertEqual(cmd.get_data(), {"n_moves": 3})

        # Execute success
        cmd.execute(self.session)
        self.view.display_message.assert_called()

    def test_history_command_full_coverage(self):
        cmd = ShowCommand("history")

        self.assertEqual(cmd.get_type(), CommandType.SHOW)
        self.assertEqual(cmd.get_data(), {"target": "history"})

        # Historique vide
        self.session.history = []
        cmd.execute(self.session)
        self.view.display_message.assert_called_with("History empty.")

        self.view.display_message.reset_mock()
        # Historique plein
        self.session.history = ["1", "2", "3", "4", "5", "6"]
        cmd.execute(self.session)
        self.assertEqual(self.view.display_message.call_count, 1)


if __name__ == "__main__":
    unittest.main()
