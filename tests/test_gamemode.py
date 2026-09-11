import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from othello.orchestrator.blitz_controller import BlitzMode
from othello.orchestrator.contest_controller import ContestMode


class TestBlitzMode(unittest.TestCase):
    def setUp(self):
        self.mock_callback = MagicMock()
        self.mode = BlitzMode(5, self.mock_callback)

    def test_init(self):
        self.assertEqual(self.mode.time_limit, 300.0)
        self.assertEqual(self.mode.remaining_time["X"], 300.0)
        self.assertEqual(self.mode.remaining_time["O"], 300.0)
        self.assertEqual(self.mode.current_player, "X")

    @patch("builtins.print")
    def test_start(self, mock_print):
        with patch.object(self.mode._thread, "start") as mock_thread_start:
            self.mode.start()
            mock_print.assert_called_once()
            mock_thread_start.assert_called_once()

    def test_handle_turn_switches_player(self):
        self.mode.handle_turn("X", "a1")
        self.assertEqual(self.mode.current_player, "O")

        self.mode.handle_turn("O", "c4")
        self.assertEqual(self.mode.current_player, "X")

    def test_handle_turn_ignores_special_commands(self):
        # Vérifie que le tour ne change pas si c'est une commande spéciale
        self.mode.current_player = "X"
        for cmd in ["save", "help", "show"]:
            self.mode.handle_turn("X", cmd)
            self.assertEqual(self.mode.current_player, "X")

    def test_check_end_condition(self):
        self.mode.remaining_time["X"] = 0
        self.assertTrue(self.mode.check_end_condition())

        self.mode.remaining_time["X"] = 10
        self.mode.remaining_time["O"] = -1
        self.assertTrue(self.mode.check_end_condition())

        self.mode.remaining_time["X"] = 10
        self.mode.remaining_time["O"] = 10
        self.assertFalse(self.mode.check_end_condition())

    @patch("builtins.print")
    def test_pause_and_resume(self, mock_print):
        self.mode.pause()
        self.assertTrue(self.mode.is_paused)

        self.mode.pause()
        self.assertFalse(self.mode.is_paused)

    def test_stop_sets_event(self):
        self.mode.stop()
        self.assertTrue(self.mode._stop_event.is_set())

    @patch("time.sleep", return_value=None)
    @patch("time.time", side_effect=[100.0, 100.1])  # last_time, now
    def test_timer_loop_decrements_time(self, mock_time, mock_sleep):
        # On force la boucle à s'arrêter après 1 itération
        with patch.object(
            self.mode._stop_event, "is_set", side_effect=[False, True]
        ):
            self.mode._timer_loop()

        # 300 - 0.1 écoulé
        self.assertAlmostEqual(self.mode.remaining_time["X"], 299.9)

    @patch("time.sleep", return_value=None)
    @patch("time.time", side_effect=[100.0, 400.0])  # 300 secondes d'un coup
    def test_timer_loop_triggers_timeout(self, mock_time, mock_sleep):
        # Le temps s'écoule d'un coup,
        # on doit tomber à 0 et appeler le callback
        with patch.object(
            self.mode._stop_event, "is_set", side_effect=[False, True]
        ):
            self.mode._timer_loop()

        self.assertEqual(self.mode.remaining_time["X"], 0)
        self.mock_callback.assert_called_once_with("X")

    @patch("time.sleep", return_value=None)
    @patch("time.time", side_effect=[100.0, 100.1])
    def test_timer_loop_paused(self, mock_time, mock_sleep):
        # Si le jeu est en pause, le temps ne doit pas descendre
        self.mode.is_paused = True
        with patch.object(
            self.mode._stop_event, "is_set", side_effect=[False, True]
        ):
            self.mode._timer_loop()

        self.assertEqual(self.mode.remaining_time["X"], 300.0)


class TestContestMode(unittest.TestCase):
    def setUp(self):
        self.session_mock = MagicMock()

    # Ajout du side_effect=SystemExit pour simuler l'arrêt du programme
    @patch("sys.exit", side_effect=SystemExit)
    @patch("builtins.print")
    def test_start_without_file_exits_with_error(self, mock_print, mock_exit):
        self.session_mock.settings.get.return_value = None
        mode = ContestMode(self.session_mock)

        # Capture l'exception générée par le mock de sys.exit
        with self.assertRaises(SystemExit):
            mode.start()

        mock_exit.assert_called_once_with(1)

    @patch("sys.exit", side_effect=SystemExit)
    @patch("builtins.print")
    @patch("othello.orchestrator.contest_controller.AIPlayer")
    def test_start_with_file_prints_move_and_exits(
        self, mock_ai_player, mock_print, mock_exit
    ):
        self.session_mock.settings.get.return_value = "game_save.txt"
        self.session_mock.current_player = "X"

        mock_ai_instance = mock_ai_player.return_value
        mock_ai_instance.get_move.return_value = "X a1"

        mode = ContestMode(self.session_mock)

        with self.assertRaises(SystemExit):
            mode.start()

        mock_print.assert_any_call("X a1")
        mock_exit.assert_called_once_with(0)

    @patch("sys.exit", side_effect=SystemExit)
    @patch("builtins.print")
    @patch("othello.orchestrator.contest_controller.AIPlayer")
    def test_start_raises_exception_exits_with_error(
        self, mock_ai_player, mock_print, mock_exit
    ):
        self.session_mock.settings.get.return_value = "game_save.txt"
        self.session_mock.current_player = "X"

        # Simule une erreur lors du calcul de l'IA
        mock_ai_instance = mock_ai_player.return_value
        mock_ai_instance.get_move.side_effect = Exception("AI crash")

        mode = ContestMode(self.session_mock)

        with self.assertRaises(SystemExit):
            mode.start()

        mock_exit.assert_called_once_with(1)

    def test_unused_methods(self):
        mode = ContestMode(self.session_mock)
        # Vérifie juste que ça ne plante pas et que ça retourne False
        mode.handle_turn("X", "a1")
        self.assertFalse(mode.check_end_condition("X"))
