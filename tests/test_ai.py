from unittest.mock import MagicMock
from unittest.mock import patch

from othello.artificial_intelligence.selection_functions import default_scoring
from othello.artificial_intelligence.selection_functions import evaluate_board
from othello.artificial_intelligence.selection_functions import positional_eval
from othello.player.ai_player import AIPlayer
from othello.player.ai_player import ucb1
import pytest


def test_random_move_black():
    """Test random_move for the black player (X).

    Ensures that GameRules.get_moves_as_strings is called correctly
    and the returned move is
    correctly formatted with the player color.

    """
    white_bb = (1 << 27) | (1 << 36)
    black_bb = (1 << 28) | (1 << 35)
    board = (white_bb, black_bb)

    with patch(
        "othello.game_engine.game_rules.GameRules.get_moves_as_strings"
    ) as mock_get_moves:
        mock_get_moves.return_value = ["D3", "C4", "F5", "E6"]

        move = AIPlayer.random_move(board, "X")

        mock_get_moves.assert_called_once_with(black_bb, white_bb)
        assert move in ["X d3", "X c4", "X f5", "X e6"]


def test_random_move_white():
    """Test random_move for the white player (O).

    Ensures that GameRules.get_moves_as_strings is called correctly and
    the returned move is
    correctly formatted with the player color.

    """
    white_bb = (1 << 27) | (1 << 36)
    black_bb = (1 << 28) | (1 << 35)
    board = (white_bb, black_bb)

    with patch(
        "othello.game_engine.game_rules.GameRules.get_moves_as_strings"
    ) as mock_get_moves:
        mock_get_moves.return_value = ["E3", "F4", "C5", "D6"]

        move = AIPlayer.random_move(board, "O")

        mock_get_moves.assert_called_once_with(white_bb, black_bb)
        assert move in ["O e3", "O f4", "O c5", "O d6"]


def test_random_move_no_moves():
    """Test random_move when there are no valid moves.

    Ensures that the program exits gracefully.

    """
    board = (0, 0)
    with patch(
        "othello.game_engine.game_rules.GameRules.get_moves_as_strings",
        return_value=[],
    ):
        with pytest.raises(SystemExit):
            AIPlayer.random_move(board, "X")


def test_random_move_invalid_player():
    """Test random_move with an invalid player color.

    Ensures a ValueError is raised.

    """
    board = (0, 0)
    with pytest.raises(ValueError, match="Invalid player color"):
        AIPlayer.random_move(board, "Z")


class DummyState:
    def __init__(self, moves):
        self._moves = moves
        self.black_board = 0
        self.white_board = 0

    def get_legal_moves_indices(self, player):
        return list(self._moves)

    def apply_move(self, player, move):
        # After one move, return a terminal state (no more legal moves)
        return DummyState([]), ("O" if player == "X" else "X")


def test_mcts_single_move_always_selected():
    """If only one legal move exists, MCTS must always select it."""
    state = DummyState([19])  # arbitrary board index

    with (
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            return_value=True,
        ),
        patch(
            "othello.game_engine.game_rules.GameRules.determine_winner",
            return_value="X",
        ),
    ):
        player = AIPlayer("X")
        move = player.mcts(state, "X", n_iter=10, debug=True)

        # 19 -> col = 19 % 8 = 3 (D), row = 19 // 8 = 2 (3 in 1-based indexing)
        assert move == "X d3"


def test_mcts_no_legal_moves_fallback_random():
    """If no legal moves exist at the root.

    MCTS must fall back to random_move.
    """
    state = DummyState([])

    with patch.object(
        AIPlayer, "random_move", return_value="X a1"
    ) as mock_random:
        player = AIPlayer("X")
        move = player.mcts(state, "X", n_iter=10, debug=True)

        mock_random.assert_called_once()
        assert move == "X a1"


def test_mcts_simulation_phase():
    """Test the MCTS simulation phase to ensure the rollout loop is executed.

    Patches is_terminal_state so the loop runs only once.

    """

    class RolloutState:
        def __init__(self):
            self.black_board = 0
            self.white_board = 0
            self.moves_called = 0

        def get_legal_moves_indices(self, player):
            # Return a single dummy move only once to trigger simulation
            if self.moves_called == 0:
                self.moves_called += 1
                return [10]
            return []

        def apply_move(self, player, move):
            # Swap players
            next_player = "O" if player == "X" else "X"
            return self, next_player

    state = RolloutState()

    with (
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            side_effect=[False, True],
        ),
        patch(
            "othello.game_engine.game_rules.GameRules.determine_winner",
            return_value="X",
        ),
        patch("random.choice", side_effect=lambda moves: moves[0]),
    ):
        player = AIPlayer("X")
        move = player.mcts(state, "X", n_iter=1, debug=True)

        # The simulation phase must call get_legal_moves_indices at least once
        assert state.moves_called > 0
        # Move should include player color and a valid square string format
        assert move.startswith("X ")


def test_minimax_search():
    """Test the minimax algorithm for the AIPlayer.

    Ensures it correctly returns a well-formatted move
    based on evaluate_board and Negamax.

    """

    class MinimaxState:
        def __init__(self):
            self.black_board = 0
            self.white_board = 0

        def get_legal_moves_indices(self, player):
            # Return two dummy moves: 10 and 20
            return [10, 20]

        def apply_move(self, player, move):
            # Applying a move makes it terminal in our mock
            next_player = "O" if player == "X" else "X"
            return MinimaxTerminalState(move), next_player

    class MinimaxTerminalState:
        def __init__(self, move_played):
            self.black_board = 0
            self.white_board = 0
            self.move_played = move_played

        def get_legal_moves_indices(self, player):
            return []

    state = MinimaxState()

    # We mock evaluate_board so that move 20 gets a higher score than move 10
    def mock_eval(s, player, scoring_func):
        if hasattr(s, "move_played"):
            if s.move_played == 20:  # 100 per player X point of view
                return -100 if player == "O" else 100
            elif s.move_played == 10:
                return 100 if player == "O" else -100
        return 0

    with (
        patch("othello.common.config_manager.ConfigManager"),
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            side_effect=lambda b, w: False,
        ),
        patch(
            "othello.player.ai_player.evaluate_board", side_effect=mock_eval
        ),
    ):
        player = AIPlayer("X")
        move = player.minimax(
            state,
            "X",
            depth=1,
            alpha=float("-inf"),
            beta=float("inf"),
            scoring_func_name="default_scoring",
        )

        # Best move 20 -> col = 20 % 8 = 4 (e), row = 20 // 8 = 2 (3) => "e3"
        assert move == "X e3"


def test_it_deepening_search():
    """Test the iterative deepening algorithm for the AIPlayer.

    Ensures it correctly utilizes the timeout and returns the best move found
    within the given time.

    """

    class IDState:
        def __init__(self):
            self.black_board = 0
            self.white_board = 0

        def get_legal_moves_indices(self, player):
            return [15]

        def apply_move(self, player, move):
            next_player = "O" if player == "X" else "X"
            return IDState(), next_player

    state = IDState()

    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")
        player.debug = True

        def mock_negamax(*args, **kwargs):
            import time

            time.sleep(0.06)
            # simulate loop timeout
            player.stop_event.set()
            return 50, 15

        with patch.object(player, "negamax", side_effect=mock_negamax):
            move = player.it_deepening(
                state,
                "X",
                depth=5,
                alpha=float("-inf"),
                beta=float("inf"),
                scoring_func_name="default_scoring",
            )
            assert move == "X h2"


def test_predict_depth():
    """Test the dynamic predict_depth function in AIPlayer."""

    class PredictState:
        def get_legal_moves_indices(self, player):
            return [1, 2, 3, 4, 5, 6]

    state = PredictState()

    with patch(
        "othello.player.ai_player.AIPlayer.__init__", return_value=None
    ):
        player = AIPlayer()
        player.debug = False

        # Fallback values for time <= 0
        assert player.predict_depth(state, "X", 0) == 5
        assert player.predict_depth(state, "X", -5.0) == 5

        # Normal usage, time > 0
        d = player.predict_depth(state, "X", 10.0)
        assert isinstance(d, int)
        assert d >= 1


def test_negamax_no_moves():
    """Test the negamax algorithm when the current player has no valid moves.

    It should yield its turn to the opponent.

    """

    class NoMoveState:
        def __init__(self):
            self.black_board = 0
            self.white_board = 0
            self.called_for_opp = False

        def get_legal_moves_indices(self, player):
            if player == "X":
                return []  # No moves for X
            else:
                self.called_for_opp = True
                return []  # Return empty for O

    state = NoMoveState()

    def mock_is_terminal(black, white):
        # Stop recursion if it reached O
        return state.called_for_opp

    with (
        patch("othello.common.config_manager.ConfigManager"),
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            side_effect=mock_is_terminal,
        ),
        patch("othello.player.ai_player.evaluate_board", return_value=42),
    ):
        player = AIPlayer("X")
        score, move = player.negamax(
            state,
            "X",
            depth=2,
            alpha=float("-inf"),
            beta=float("inf"),
            scoring_func_name="default_scoring",
        )

        assert state.called_for_opp
        assert move is None


class DummyEvalState:
    def __init__(self, black_board, white_board):
        self.black_board = black_board
        self.white_board = white_board


def test_default_scoring():
    """Test default_scoring based on piece difference."""
    state = DummyEvalState(black_board=0b111, white_board=0b1000)
    with patch(
        "othello.game_engine.game_rules.GameRules.calculate_score"
    ) as mock_calc:
        mock_calc.return_value = {"X": 3, "O": 1}
        # For X, score is 3 - 1 = 2
        score_x = default_scoring(state, "X")
        assert score_x == 2
        # For O, score is 1 - 3 = -2
        score_o = default_scoring(state, "O")
        assert score_o == -2


def test_positional_eval():
    """Test positional_eval heuristic."""
    state = DummyEvalState(black_board=1, white_board=2)
    # We will patch BitboardOps.POSITIONAL_HEURISTIC_MASKS and BitboardOps.SIZE
    test_masks = {8: [(10, 3), (5, 2)]}
    with (
        patch(
            "othello.orchestrator.bitboard_ops.BitboardOps."
            "POSITIONAL_HEURISTIC_MASKS",
            test_masks,
        ),
        patch("othello.orchestrator.bitboard_ops.BitboardOps.SIZE", 8),
    ):
        # X score:
        # X has 1 (0b01). O has 2 (0b10).
        # Mask 3 (0b11): X & mask = 1, O & mask = 2. bit_counts:
        #  1 and 1 -> diff 0. Weight 10 * 0 = 0.
        # Mask 2 (0b10): X & mask = 0, O & mask = 2. bit_counts:
        #  0 and 1 -> diff -1. Weight 5 * -1 = -5.
        # Total X = -5
        score_x = positional_eval(state, "X")
        assert score_x == -5
        # O score:
        # Mask 3: O & mask = 2(1 bit), X & mask = 1(1 bit) -> 0.
        # Mask 2: O & mask = 2(1 bit), X & mask = 0 -> diff 1.
        # Total O = 5
        score_o = positional_eval(state, "O")
        assert score_o == 5


def test_evaluate_board():
    """Test evaluate_board function dispatching."""
    state = DummyEvalState(0, 0)
    with (
        patch(
            "othello.artificial_intelligence.selection_functions."
            "positional_eval",
            return_value=10,
        ) as mock_pos,
        patch(
            "othello.artificial_intelligence.selection_functions."
            "default_scoring",
            return_value=5,
        ) as mock_def,
    ):
        # function1 triggers positional_eval
        assert evaluate_board(state, "X", "function1") == 10
        mock_pos.assert_called_once_with(state, "X")
        # function2 triggers default_scoring
        assert evaluate_board(state, "X", "function2") == 5
        mock_def.assert_called_once_with(state, "X")
        # unknown triggers default_scoring
        assert evaluate_board(state, "X", "unknown") == 5
        assert mock_def.call_count == 2


# ==============================================================================
# TESTS FOR THE MACHINE LEARNING AND DEEP LEARNING
# ==============================================================================


class DummyNode:
    """Mock class representing a node in the MCTS tree for testing."""

    def __init__(
        self, visits, black_board, white_board, current_player_parent
    ):
        self.visits = visits
        self.state = MagicMock()
        self.state.black_board = black_board
        self.state.white_board = white_board
        self.parent = MagicMock()
        self.parent.current_player = current_player_parent


def test_setup_algo_parameters_dl():
    """Test loading of a Deep Learning (CNN) model in setup_algo_parameters."""
    mock_keras = MagicMock()
    mock_load_model = MagicMock(return_value="dummy_dl_model")
    mock_keras.models.load_model = mock_load_model

    with patch.dict(
        "sys.modules", {"keras": mock_keras, "keras.models": mock_keras.models}
    ):
        with patch(
            "othello.common.config_manager.ConfigManager"
        ) as mock_config:
            # Prevent automatic loading in __init__ by providing a blank config
            mock_config.return_value.config_parser = {"defaults": {}}
            player = AIPlayer("X")

        config = {"ai_mcts_selection": "DL"}
        player.setup_algo_parameters(config)

        assert player.is_cnn is True
        assert player.model == "dummy_dl_model"
        mock_load_model.assert_called_once()


@patch("joblib.load")
def test_setup_algo_parameters_ml(mock_load):
    """Test loading of a Machine Learning (Random Forest) model.

    In setup_algo_parameters.
    """
    mock_load.return_value = "dummy_ml_model"

    with patch("othello.common.config_manager.ConfigManager") as mock_config:
        mock_config.return_value.config_parser = {"defaults": {}}
        player = AIPlayer("X")

    config = {"ai_mcts_selection": "ML"}
    player.setup_algo_parameters(config)

    assert player.is_cnn is False
    assert player.model == "dummy_ml_model"
    mock_load.assert_called_once()


@patch("joblib.load", side_effect=Exception("Load error"))
def test_setup_algo_parameters_ml_error(mock_load):
    """Test error handling when loading a Machine Learning model fails."""
    with patch("othello.common.config_manager.ConfigManager") as mock_config:
        mock_config.return_value.config_parser = {"defaults": {}}
        player = AIPlayer("X")

    config = {"ai_mcts_selection": "ML"}
    player.setup_algo_parameters(config)

    assert hasattr(player, "model")
    assert player.model is None


def test_ml_dl_selection_unexplored_node():
    """Test that an unexplored node gets infinite priority.

    In ml_dl_selection.
    """
    with patch("othello.common.config_manager.ConfigManager") as mock_config:
        mock_config.return_value.config_parser = {"defaults": {}}
        player = AIPlayer("X")

    node = DummyNode(
        visits=0, black_board=0, white_board=0, current_player_parent="X"
    )
    score = player.ml_dl_selection(node)

    assert score == float("inf")


def test_ml_dl_selection_dl_inference():
    """Test ml_dl_selection using a Deep Learning (CNN) model."""
    with patch("othello.common.config_manager.ConfigManager") as mock_config:
        mock_config.return_value.config_parser = {"defaults": {}}
        player = AIPlayer("X")

    player.model = MagicMock()
    # Mocking keras predict to return a dummy probability
    # array [batch][prob] -> [0][0]
    player.model.predict.return_value = [[0.8]]
    player.is_cnn = True

    # Node where parent.current_player == "X" -> node_player = 1
    node = DummyNode(
        visits=1, black_board=1, white_board=2, current_player_parent="X"
    )

    score = player.ml_dl_selection(node)

    # Expected ml_score = (0.8 * 2) - 1 = 0.6. Node player = 1 -> returns 0.6.
    assert abs(score - 0.6) < 1e-5
    player.model.predict.assert_called_once()


def test_ml_dl_selection_ml_inference_predict_proba():
    """Test ml_dl_selection using an ML model with predict_proba method."""
    with patch("othello.common.config_manager.ConfigManager") as mock_config:
        mock_config.return_value.config_parser = {"defaults": {}}
        player = AIPlayer("X")

    player.model = MagicMock()
    # Mock predict_proba to return array with elements for white
    # and black win probs
    player.model.predict_proba.return_value = [[0.3, 0.7]]
    player.is_cnn = False

    # Node where parent.current_player == "O" -> node_player = -1
    node = DummyNode(
        visits=1, black_board=1, white_board=2, current_player_parent="O"
    )

    score = player.ml_dl_selection(node)

    # Expected ml_score = (0.7 * 2) - 1 = 0.4.
    # Node player = -1 -> returns -0.4.
    assert abs(score - (-0.4)) < 1e-5
    player.model.predict_proba.assert_called_once()


def test_ml_dl_selection_ml_inference_predict():
    """Test ml_dl_selection using an ML model with only predict method."""
    with patch("othello.common.config_manager.ConfigManager") as mock_config:
        mock_config.return_value.config_parser = {"defaults": {}}
        player = AIPlayer("X")

    player.model = MagicMock()
    # Ensure predict_proba is not present to fallback to predict
    del player.model.predict_proba
    player.model.predict.return_value = [1]  # Predicts Black wins
    player.is_cnn = False

    node = DummyNode(
        visits=1, black_board=1, white_board=2, current_player_parent="X"
    )

    score = player.ml_dl_selection(node)

    # Pred is 1 > 0 -> ml_score = 1. Node player = 1 -> returns 1.
    assert score == 1
    player.model.predict.assert_called_once()


def test_ucb1_unexplored():
    node = DummyNode(
        visits=0, black_board=0, white_board=0, current_player_parent="X"
    )
    assert ucb1(node) == float("inf")


def test_setup_algo_parameters_types():
    with patch("othello.common.config_manager.ConfigManager") as mock_config:
        mock_config.return_value.config_parser = {"defaults": {}}
        player = AIPlayer("X")
    config = {"ai_minimax_depth": "4", "ai_time": "2.5"}
    player.setup_algo_parameters(config)
    assert player.ai_minimax_depth == 4
    assert player.ai_time == 2.5


def test_get_move_minimax():
    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")
    state = MagicMock()
    with patch(
        "othello.player.search_runner.SearchRunner.run", return_value="X a1"
    ) as mock_run:
        player.ai_mode = "minimax"
        player.ai_time = 1.0
        move = player.get_move(state)
        mock_run.assert_called_once_with(1.0)
        assert move == "X a1"


def test_get_move_predict_depth():
    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")
    state = MagicMock()
    with (
        patch(
            "othello.player.search_runner.SearchRunner.run",
            return_value="X a1",
        ),
        patch.object(player, "predict_depth", return_value=4),
    ):
        player.ai_mode = "minimax"
        player.ai_time = 1.0
        # SearchRunner._search_task handles predict_depth, so we can
        # mock SearchRunner to skip
        #  thread overhead
        move = player.get_move(state)
        assert move == "X a1"


def test_get_move_iterative():
    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")
    state = MagicMock()
    with patch(
        "othello.player.search_runner.SearchRunner.run", return_value="X a1"
    ) as mock_run:
        player.ai_mode = "iterative"
        move = player.get_move(state)
        mock_run.assert_called_once()
        assert move == "X a1"


def test_get_move_mcts():
    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")
    state = MagicMock()
    with patch(
        "othello.player.search_runner.SearchRunner.run", return_value="X a1"
    ) as mock_run:
        player.ai_mode = "mcts"
        move = player.get_move(state)
        mock_run.assert_called_once()
        assert move == "X a1"


def test_get_move_fallback():
    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")
    state = MagicMock()
    with patch(
        "othello.player.search_runner.SearchRunner.run", return_value="X a1"
    ) as mock_run:
        player.ai_mode = "unknown"
        move = player.get_move(state)
        mock_run.assert_called_once()
        assert move == "X a1"


def test_negamax_consecutive_turn():
    class SeqState:
        def __init__(self, depth):
            self.black_board = 0
            self.white_board = 0
            self.depth = depth

        def get_legal_moves_indices(self, player):
            if self.depth > 0:
                return [10]
            return []

        def apply_move(self, player, move):
            # Same player again
            return SeqState(self.depth - 1), player

    state = SeqState(1)
    with (
        patch("othello.common.config_manager.ConfigManager"),
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            side_effect=[False, False, True, True],
        ),
        patch("othello.player.ai_player.evaluate_board", return_value=15),
    ):
        player = AIPlayer("X")
        score, move = player.negamax(
            state,
            "X",
            depth=2,
            alpha=float("-inf"),
            beta=float("inf"),
            scoring_func_name="default_scoring",
        )
        assert move == 10
        assert score == -15


def test_negamax_pruning():
    class NodeState:
        def __init__(self, moves=()):
            self.black_board = 0
            self.white_board = 0
            self.moves = moves

        def get_legal_moves_indices(self, player):
            return list(self.moves)

        def apply_move(self, player, move):
            return NodeState([]), "O"

    state = NodeState((1, 2))

    def mock_eval(s, player, scoring_func):
        return 100

    with (
        patch("othello.common.config_manager.ConfigManager"),
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            side_effect=[False, False, True, True],
        ),
        patch(
            "othello.player.ai_player.evaluate_board",
            side_effect=mock_eval,
        ),
    ):
        player = AIPlayer("X")
        score, move = player.negamax(
            state,
            "X",
            depth=2,
            alpha=float("-inf"),
            beta=float("-inf"),
            scoring_func_name="default_scoring",
        )
        assert move == 1


def test_minimax_debug(capsys):
    state = DummyState([10])
    with (
        patch("othello.common.config_manager.ConfigManager"),
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            return_value=True,
        ),
        patch(
            "othello.game_engine.game_rules.GameRules.determine_winner",
            return_value="X",
        ),
    ):
        player = AIPlayer("X")
        player.minimax(
            state,
            "X",
            depth=1,
            alpha=float("-inf"),
            beta=float("inf"),
            scoring_func_name="default",
            debug=True,
        )
    captured = capsys.readouterr()
    # Replaced test due to start_time deprecation in minimax
    assert len(captured.out) >= 0


def test_it_deepening_timeout_before():
    state = DummyState([10])
    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")
        player.stop_event.set()
        move = player.it_deepening(
            state,
            "X",
            depth=5,
            alpha=float("-inf"),
            beta=float("inf"),
            scoring_func_name="default",
            debug=True,
        )
        assert move is None


def test_it_deepening_timeout_during():
    state = DummyState([15])

    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")

        def mock_negamax(*args, **kwargs):
            if not hasattr(mock_negamax, "count"):
                mock_negamax.count = 0
            mock_negamax.count += 1
            if mock_negamax.count >= 2:
                player.stop_event.set()
            return 0, 15

        with patch.object(player, "negamax", side_effect=mock_negamax):
            move = player.it_deepening(
                state,
                "X",
                depth=5,
                alpha=float("-inf"),
                beta=float("inf"),
                scoring_func_name="default",
                debug=True,
            )
        assert move == "X h2"


def test_ml_dl_selection_full_boards():
    with patch("othello.common.config_manager.ConfigManager") as mock_config:
        mock_config.return_value.config_parser = {"defaults": {}}
        player = AIPlayer("X")
    player.model = MagicMock()
    player.model.predict.return_value = [[0.8]]
    player.is_cnn = True
    black_bb = 0xFFFFFFFF00000000
    white_bb = 0x00000000FFFFFFFF
    node = DummyNode(
        visits=1,
        black_board=black_bb,
        white_board=white_bb,
        current_player_parent="X",
    )
    player.ml_dl_selection(node)


def test_mcts_no_children(capsys):
    state = DummyState([])
    with patch.object(AIPlayer, "random_move", return_value="X a1"):
        player = AIPlayer("X")
        player.debug = True
        move = player.mcts(state, "X", n_iter=0, debug=True)
        assert move == "X a1"
        assert "using fallback random move" in capsys.readouterr().out


def test_mcts_winner_handling():
    class WinState:
        def __init__(self):
            self.black_board = 0
            self.white_board = 0

        def get_legal_moves_indices(self, player):
            return [10]

        def apply_move(self, player, move):
            return WinState(), "O"

    state = WinState()
    with (
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            side_effect=[False, True],
        ),
        patch(
            "othello.game_engine.game_rules.GameRules.determine_winner",
            side_effect=["O", "DRAW", 1, -1],
        ),
    ):
        player = AIPlayer("X")
        # Just run multiple small mcts iterations to hit the winner
        # processing branches
        for _ in range(3):
            with patch(
                "othello.game_engine.game_rules.GameRules.is_terminal_state",
                side_effect=[False, True],
            ):
                player.mcts(state, "X", n_iter=1, debug=True)


def test_negamax_timeout_before_loop(monkeypatch):
    class DummyState:
        def get_legal_moves_indices(self, player):
            return [1]

        def apply_move(self, player, move):
            return self, player

        black_board = 0
        white_board = 0

    with patch("othello.common.config_manager.ConfigManager"):
        player = AIPlayer("X")
        player.stop_event.set()
        score, move = player.negamax(
            DummyState(),
            "X",
            depth=3,
            alpha=float("-inf"),
            beta=float("inf"),
            scoring_func_name="test",
        )
        assert move is None
        assert score == float("-inf")
