"""Game state Module."""

from othello.game_engine.game_rules import GameRules
from othello.orchestrator.bitboard_ops import BitboardOps


class GameState:
    """Game State Class."""

    def __init__(self):
        """Initialize an empty game state."""
        self.white_board = 0
        self.black_board = 0

    def get_board(self) -> tuple[int, int]:
        """Return the board state as (white_board, black_board).

        :return: A tuple containing the two bitboards (white, black).

        """
        return self.white_board, self.black_board

    def get_board_as_string(self) -> str:
        """Convert board into a string with '/' as row separator.

        :return: The string of the board's conversion.

        """
        size = BitboardOps.SIZE
        rows = []

        for row in range(size):
            row_str = ""
            for col in range(size):
                index = row * size + col
                if BitboardOps.get_token(self.black_board, index):
                    row_str += "X"
                elif BitboardOps.get_token(self.white_board, index):
                    row_str += "O"
                else:
                    row_str += "_"
            rows.append(row_str)

        return "/".join(rows)

    def apply_move(
        self, current_player: str, move_index: int
    ) -> tuple["GameState", str]:
        """Apply a move and return a NEW game state along with the next player.

        Handles piece placement, flipping, and turn skipping.

        :param current_player: The player making the move ('X' or 'O').
        :param move_index: The linear bitboard index of the move.
        :return: A tuple of (new_game_state, next_player).

        """
        new_state = GameState()
        new_state.black_board = self.black_board
        new_state.white_board = self.white_board

        if current_player == "X":
            player_bb = new_state.black_board
            opponent_bb = new_state.white_board
        else:
            player_bb = new_state.white_board
            opponent_bb = new_state.black_board

        col = move_index % BitboardOps.SIZE
        row = move_index // BitboardOps.SIZE

        flips = GameRules.compute_flips(player_bb, opponent_bb, col, row)

        player_bb |= 1 << move_index
        player_bb |= flips
        opponent_bb &= ~flips

        if current_player == "X":
            new_state.black_board = player_bb
            new_state.white_board = opponent_bb
            next_player = "O"
            if (
                GameRules.get_legal_moves(
                    new_state.white_board, new_state.black_board
                )
                == 0
            ):
                next_player = "X"
        else:
            new_state.white_board = player_bb
            new_state.black_board = opponent_bb
            next_player = "X"
            if (
                GameRules.get_legal_moves(
                    new_state.black_board, new_state.white_board
                )
                == 0
            ):
                next_player = "O"

        return new_state, next_player

    def get_legal_moves_indices(self, current_player: str) -> list[int]:
        """Return a list of linear bitboard indices representing legal moves.

        :param current_player: The current player ('X' or 'O').
        :return: A list of integers representing valid move indices.

        """
        if current_player == "X":
            legal_moves = GameRules.get_legal_moves(
                self.black_board, self.white_board
            )
        else:
            legal_moves = GameRules.get_legal_moves(
                self.white_board, self.black_board
            )

        moves = []
        for i in range(BitboardOps.SIZE * BitboardOps.SIZE):
            if legal_moves & (1 << i):
                moves.append(i)
        return moves

    def initialize_default(self):
        """Sets up the standard 8x8 Othello starting position."""
        size = BitboardOps.SIZE
        mid = size // 2

        tl_index = (mid - 1) * size + (mid - 1)
        tr_index = (mid - 1) * size + mid
        bl_index = mid * size + (mid - 1)
        br_index = mid * size + mid

        self.black_board = 0
        self.white_board = 0

        # Blacks and Whites setup
        self.black_board = BitboardOps.set_token(self.black_board, tl_index)
        self.black_board = BitboardOps.set_token(self.black_board, br_index)
        self.white_board = BitboardOps.set_token(self.white_board, tr_index)
        self.white_board = BitboardOps.set_token(self.white_board, bl_index)

    def get_bitboards(self, color: str) -> tuple[int, int]:
        """Returns (player_board, opponent_board) based on the color."""
        if color == "X":
            return self.black_board, self.white_board
        return self.white_board, self.black_board
