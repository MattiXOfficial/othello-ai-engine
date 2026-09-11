"""Game rules Module.

Handle the move's validation, the flips and the game's end."""

from othello.common.i18n_manager import I18nManager
from othello.orchestrator.bitboard_ops import BitboardOps


def _(message):
    return I18nManager().gettext(message)


class GameRules:
    """Game rules class."""

    @staticmethod
    def is_valid_move(
        player_bb: int, opponent_bb: int, col: int, row: int
    ) -> bool:
        """Check if a move is valid."""
        size = BitboardOps.SIZE
        # 1. Vérification des bornes
        if not (0 <= col < size and 0 <= row < size):
            # Debug/Error logging
            print(_("Out of bounds move."))
            return False

        # 2. Vérification case vide
        index = (row * size) + col
        mask = 1 << index
        if (player_bb | opponent_bb) & mask:
            # Debug/Error logging
            print(_("Cell is not empty."))
            return False

        # 3. Vérification des prises (doit retourner au moins 1 pion)
        return GameRules.compute_flips(player_bb, opponent_bb, col, row) > 0

    @staticmethod
    def get_legal_moves(player_bb: int, opponent_bb: int) -> int:
        """Calculate all legal moves for the current player."""
        legal_moves = 0
        empty_slots = ~(player_bb | opponent_bb) & BitboardOps.FULL_MASK

        for direction in BitboardOps.DIRECTIONS:
            candidates = (
                BitboardOps.shift_direction(player_bb, direction) & opponent_bb
            )
            for _ in range(5):
                candidates |= (
                    BitboardOps.shift_direction(candidates, direction)
                    & opponent_bb
                )
            valid_moves_with_dir = (
                BitboardOps.shift_direction(candidates, direction)
                & empty_slots
            )
            legal_moves |= valid_moves_with_dir

        return legal_moves

    @staticmethod
    def compute_flips(
        player_bb: int, opponent_bb: int, col: int, row: int
    ) -> int:
        """Calculate the opponent pieces that would be flipped by a move."""
        size = BitboardOps.SIZE
        flip_mask_total = 0
        directions = [
            (0, -1),
            (0, 1),
            (-1, 0),
            (1, 0),
            (-1, -1),
            (1, -1),
            (-1, 1),
            (1, 1),
        ]

        for d_col, d_row in directions:
            cur_col = col + d_col
            cur_row = row + d_row
            potential_flips = 0

            for _ in range(size):
                if not (0 <= cur_col < size and 0 <= cur_row < size):
                    break
                index_bit = (cur_row * size) + cur_col
                masque_position = 1 << index_bit

                if opponent_bb & masque_position:
                    potential_flips |= masque_position
                    cur_col += d_col
                    cur_row += d_row
                elif player_bb & masque_position:
                    flip_mask_total |= potential_flips
                    break
                else:
                    break

        return flip_mask_total

    @staticmethod
    def move_parser(move: str) -> tuple[str, int]:
        """Convert a move string 'Color Coordinate' into a tuple."""
        size = BitboardOps.SIZE
        if not move:
            raise ValueError(_("Invalid move format"))

        parts = move.strip().split()
        if len(parts) != 2:
            raise ValueError(_("Invalid move format"))

        color = parts[0].upper()
        coord = parts[1].upper()

        if color not in ("X", "O"):
            raise ValueError(_("Invalid color (expected X or O)"))

        if len(coord) < 2:
            raise ValueError(_("Invalid coordinate"))

        col_char = coord[0]
        row_str = coord[1:]

        if not col_char.isalpha() or not row_str.isdigit():
            raise ValueError(_("Invalid coordinate"))

        col = ord(col_char) - ord("A")
        row = int(row_str) - 1

        if not (0 <= col < size and 0 <= row < size):
            raise ValueError(_("Move out of bounds"))

        return color, row * size + col

    @staticmethod
    def is_terminal_state(black_bb: int, white_bb: int) -> bool:
        """Check if the current state is terminal (game over)."""
        # end the game in one round
        # if BitboardOps.popcount(black_bb | white_bb) >= 5:
        #    return True

        board_is_full = (
            (black_bb | white_bb) & BitboardOps.FULL_MASK
        ) == BitboardOps.FULL_MASK

        if board_is_full:
            return True

        black_can_play = GameRules.get_legal_moves(black_bb, white_bb)
        white_can_play = GameRules.get_legal_moves(white_bb, black_bb)
        return (not black_can_play) and (not white_can_play)

    @staticmethod
    def is_game_over(
        black_bb: int, white_bb: int, quiet: bool = False
    ) -> bool:
        """Check if the game is over and print the winner."""
        if GameRules.is_terminal_state(black_bb, white_bb):
            winner = GameRules.determine_winner(black_bb, white_bb)
            scores = GameRules.calculate_score(black_bb, white_bb)
            if not quiet:
                print(_("Game over! Winner: {winner}").format(winner=winner))
                print(
                    _(
                        "Final score - Black (X): {black}, White (O): {white}"
                    ).format(black=scores["X"], white=scores["O"])
                )
            return True

        return False

    @staticmethod
    def calculate_score(black_bb: int, white_bb: int) -> dict[str, int]:
        """Calculate the current score based on the number of pieces."""
        return {
            "X": BitboardOps.popcount(black_bb),
            "O": BitboardOps.popcount(white_bb),
        }

    @staticmethod
    def determine_winner(black_bb: int, white_bb: int) -> str:
        """Determine the winner of the game based on the current scores."""
        scores = GameRules.calculate_score(black_bb, white_bb)
        black_score = scores["X"]
        white_score = scores["O"]

        if black_score > white_score:
            return "X"
        if white_score > black_score:
            return "O"
        return "DRAW"

    @staticmethod
    def get_moves_as_strings(player_bb: int, opponent_bb: int) -> list[str]:
        """Convert the bitboard of legal moves into a list."""
        size = BitboardOps.SIZE
        legal_bb = GameRules.get_legal_moves(player_bb, opponent_bb)
        moves = []

        for index in range(size * size):
            if legal_bb & (1 << index):
                row = index // size
                col = index % size
                move_str = f"{chr(ord('A') + col)}{row + 1}"
                moves.append(move_str)
        return moves
