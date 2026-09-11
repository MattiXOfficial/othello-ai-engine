from unittest.mock import MagicMock
from unittest.mock import patch


from othello.artificial_intelligence.selection_functions import (
    count_stable_discs
)
from othello.artificial_intelligence.selection_functions import default_scoring
from othello.artificial_intelligence.selection_functions import dynamic_eval
from othello.artificial_intelligence.selection_functions import evaluate_board
from othello.artificial_intelligence.selection_functions import positional_eval
from othello.artificial_intelligence.selection_functions import stability_eval


class DummyEvalState:
    def __init__(self, black_board, white_board):
        self.black_board = black_board
        self.white_board = white_board


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
        patch(
            "othello.artificial_intelligence.selection_functions."
            "dynamic_eval",
            return_value=15,
        ) as mock_dyn,
    ):
        # function1 triggers positional_eval
        assert evaluate_board(state, "X", "function1") == 10
        mock_pos.assert_called_once_with(state, "X")

        # function2 triggers default_scoring
        assert evaluate_board(state, "X", "function2") == 5
        assert mock_def.call_count == 1
        mock_def.assert_called_with(state, "X")

        # function3 triggers dynamic_eval
        assert evaluate_board(state, "X", "function3") == 15
        mock_dyn.assert_called_once_with(state, "X")

        # unknown triggers default_scoring
        assert evaluate_board(state, "X", "unknown") == 5
        assert mock_def.call_count == 2


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
    # Patching POSITIONAL_HEURISTIC_MASKS and SIZE
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


def test_count_stable_discs():
    """Test counting stable discs logic."""
    with patch(
        "othello.artificial_intelligence.selection_functions.BitboardOps.SIZE",
        4,
    ):
        # A 4x4 board for simpler testing
        # 0b0000_0000_0000_0000
        assert count_stable_discs(0, 0) == 0

        # A single piece not in a corner or full edge is generally not stable
        assert count_stable_discs(1 << 5, 0) == 0

        # Corner piece is always stable (intersects all 4 edges
        # or out-of-bounds directly)
        assert count_stable_discs(1, 0) == 1

        # Board fully filled with 1s = 16 stable pieces
        assert count_stable_discs(0xFFFF, 0) == 16

        # Mixed full row (row 0: X O X O -> 0b1010 for player,
        # 0b0101 for opponent)
        # Because the row is full, no_empty will be true
        # for the horizontal axis.
        # Thus, pieces in a full row on the edge are stable even if mixed!
        player_bb = 0b0000_0000_0000_1010
        opponent_bb = 0b0000_0000_0000_0101
        assert (
            count_stable_discs(player_bb, opponent_bb) == 2
        )  # 2 player pieces
        assert (
            count_stable_discs(opponent_bb, player_bb) == 2
        )  # 2 opponent pieces

        # Test a line block with empty spaces (solid=False, no_empty=False)
        # player has piece at index 1 (0b0010), opponent at index 0 (0b0001)
        assert count_stable_discs(0b0010, 0b0001) == 0


def test_stability_eval():
    """Test stability_eval."""
    state = DummyEvalState(black_board=0b1, white_board=0b10)
    with patch(
        "othello.artificial_intelligence.selection_functions."
        "count_stable_discs"
    ) as mock_count:
        # my_bb is 1, opp_bb is 2 for 'X'
        mock_count.side_effect = [
            5,
            2,
        ]  # first call for my_bb, second for opp_bb
        score = stability_eval(state, "X")
        assert score == 3  # 5 - 2
        mock_count.assert_any_call(1, 2)
        mock_count.assert_any_call(2, 1)


def test_dynamic_eval():
    """Test dynamic_eval changes strategy based on progress."""
    state = DummyEvalState(black_board=1, white_board=2)
    state.black_board = MagicMock()
    state.black_board.bit_count.return_value = 10
    state.white_board = MagicMock()
    state.white_board.bit_count.return_value = 10

    with (
        patch("othello.orchestrator.bitboard_ops.BitboardOps.SIZE", 8),
        patch(
            "othello.artificial_intelligence.selection_functions."
            "default_scoring",
            return_value=1,
        ) as mock_def,
        patch(
            "othello.artificial_intelligence.selection_functions."
            "positional_eval",
            return_value=2,
        ) as mock_pos,
        patch(
            "othello.artificial_intelligence.selection_functions."
            "stability_eval",
            return_value=3,
        ) as mock_stab,
    ):
        # 20 pieces / 64 slots = 0.3125 (< 0.35) -> default_scoring
        assert dynamic_eval(state, "X") == 1
        assert mock_def.called

        # Update pieces to 30 / 64 = 0.46875 (< 0.75) -> positional_eval
        state.black_board.bit_count.return_value = 15
        state.white_board.bit_count.return_value = 15
        assert dynamic_eval(state, "X") == 2
        assert mock_pos.called

        # Update pieces to 50 / 64 = 0.78125 (> 0.75) -> stability_eval
        state.black_board.bit_count.return_value = 25
        state.white_board.bit_count.return_value = 25
        assert dynamic_eval(state, "X") == 3
        assert mock_stab.called
