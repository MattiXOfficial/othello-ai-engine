"""
Model trainer module
Generates datasets of Othello games for machine learning.
"""

import csv
import random
import argparse
import os
from typing import List, Tuple

from othello.game_engine.game_rules import GameRules
from othello.orchestrator.bitboard_ops import BitboardOps


class ModelTrainer:
    """
    Class responsible for generating training data by playing random games.
    The generated data will be used to train AI models to play Othello.
    """

    def __init__(self, size: int = 8, depth: int = 2):
        """
        Initialize the ModelTrainer with a specific
        board size and minimax depth.
        Othello is usually played on an 8x8 board,
        but our engine supports variable sizes.

        :param size: The dimension of the board (e.g., 8 for an 8x8 board).
        :param depth: The depth of the minimax search.
        """
        self.size = size
        self.depth = depth
        # We must tell the BitboardOps class
        # what the board size is so it can generate
        # the correct collision masks and directions for token shifting.
        BitboardOps.set_board_size(size)

    def _get_initial_board(self) -> Tuple[int, int]:
        """
        Set up the default initial board (for any size).

        Returns a tuple of (black_board, white_board).
        """
        black_board = 0
        white_board = 0

        # Calculate the middle indexes based on the board's size
        mid = self.size // 2

        # The 4 center cells indexes:
        # Top-Left, Top-Right, Bottom-Left, Bottom-Right
        tl_index = (mid - 1) * self.size + (mid - 1)
        tr_index = (mid - 1) * self.size + mid
        bl_index = mid * self.size + (mid - 1)
        br_index = mid * self.size + mid

        # Place the pieces by setting the specific bits to 1
        # Black pieces are placed Top-Left and Bottom-Right
        black_board = BitboardOps.set_token(black_board, tl_index)
        black_board = BitboardOps.set_token(black_board, br_index)

        # White pieces are placed Top-Right and Bottom-Left
        white_board = BitboardOps.set_token(white_board, tr_index)
        white_board = BitboardOps.set_token(white_board, bl_index)

        return black_board, white_board

    def _get_random_move(self, legal_moves_bb: int) -> int:
        """
        Select a random move from the legal moves bitboard.

        :param legal_moves_bb: A single integer where
        each bit set to 1 means it's a valid move.
        (e.g., if bit 12 is 1, playing on cell 12 is legal).
        :return: The index of the randomly chosen move cell.
        """
        moves = []
        # We iterate over every cell on the board (self.size * self.size)
        for i in range(self.size * self.size):
            if (legal_moves_bb >> i) & 1:
                moves.append(i)

        if not moves:
            return -1

        return random.choice(moves)

    def _capture_state(self, black_board: int, white_board: int) -> List[int]:
        state = []
        for i in range(self.size * self.size):
            if (black_board >> i) & 1:
                state.append(1)
            elif (white_board >> i) & 1:
                state.append(-1)
            else:
                state.append(0)
        return state

    def _apply_move(
        self,
        current_player: int,
        col: int,
        row: int,
        black_board: int,
        white_board: int,
    ) -> Tuple[int, int]:
        move = row * self.size + col
        if current_player == 1:
            flips = GameRules.compute_flips(black_board, white_board, col, row)
            black_board |= 1 << move
            black_board |= flips
            white_board &= ~flips
        else:
            flips = GameRules.compute_flips(white_board, black_board, col, row)
            white_board |= 1 << move
            white_board |= flips
            black_board &= ~flips
        return black_board, white_board

    def _negamax(
        self,
        black_board: int,
        white_board: int,
        current_player: int,
        depth: int,
        alpha: float,
        beta: float,
    ) -> Tuple[float, int]:
        if depth == 0:
            b_count = BitboardOps.popcount(black_board)
            w_count = BitboardOps.popcount(white_board)
            score = (
                (b_count - w_count)
                if current_player == 1
                else (w_count - b_count)
            )
            return score + random.uniform(-0.1, 0.1), -1

        black_moves = GameRules.get_legal_moves(black_board, white_board)
        white_moves = GameRules.get_legal_moves(white_board, black_board)
        legal_moves = black_moves if current_player == 1 else white_moves

        if not legal_moves:
            if not black_moves and not white_moves:
                b_count = BitboardOps.popcount(black_board)
                w_count = BitboardOps.popcount(white_board)
                score = (
                    (b_count - w_count)
                    if current_player == 1
                    else (w_count - b_count)
                )
                if score > 0:
                    return 1000 + score, -1
                elif score < 0:
                    return -1000 + score, -1
                return 0, -1

            score, _ = self._negamax(
                black_board, white_board, -current_player, depth, -beta, -alpha
            )
            return -score, -1

        moves = []
        for i in range(self.size * self.size):
            if (legal_moves >> i) & 1:
                moves.append(i)

        best_score = float("-inf")
        best_move = -1
        random.shuffle(moves)

        for move in moves:
            col, row = move % self.size, move // self.size
            nbb, nwb = self._apply_move(
                current_player, col, row, black_board, white_board
            )

            next_black_moves = GameRules.get_legal_moves(nbb, nwb)
            next_white_moves = GameRules.get_legal_moves(nwb, nbb)

            if current_player == 1:
                next_player = -1 if next_white_moves else 1
            else:
                next_player = 1 if next_black_moves else -1

            if next_player == current_player:
                score, _ = self._negamax(
                    nbb, nwb, next_player, depth - 1, alpha, beta
                )
            else:
                score, _ = self._negamax(
                    nbb, nwb, next_player, depth - 1, -beta, -alpha
                )
                score = -score

            if score > best_score:
                best_score = score
                best_move = move

            alpha = max(alpha, best_score)
            if alpha >= beta:
                break

        return best_score, best_move

    def _apply_random_move(
        self,
        current_player: int,
        legal_moves: int,
        black_board: int,
        white_board: int,
    ) -> Tuple[int, int]:
        move = self._get_random_move(legal_moves)
        col, row = move % self.size, move // self.size
        return self._apply_move(
            current_player, col, row, black_board, white_board
        )

    def _apply_minimax_move(
        self,
        current_player: int,
        legal_moves: int,
        black_board: int,
        white_board: int,
    ) -> Tuple[int, int]:
        _, best_move = self._negamax(
            black_board,
            white_board,
            current_player,
            self.depth,
            float("-inf"),
            float("inf"),
        )
        if best_move == -1:
            return self._apply_random_move(
                current_player, legal_moves, black_board, white_board
            )
        col, row = best_move % self.size, best_move // self.size
        return self._apply_move(
            current_player, col, row, black_board, white_board
        )

    def play_game(self) -> Tuple[List[List[int]], int]:
        """
        Simulate a full game using Minimax Alpha Beta from start to finish.
        This is the core method for generating data.

        Returns a tuple containing:
        - A list of states (each state is the flattened view of the board
        during a turn)
        (where 1 means a Black piece, -1 means a White piece, and 0 means
        Empty)
        - The winner (1 for Black, -1 for White, 0 for Draw)
        """
        black_board, white_board = self._get_initial_board()
        current_player = 1
        states = []

        while True:
            board_is_full = (
                (black_board | white_board) & BitboardOps.FULL_MASK
            ) == BitboardOps.FULL_MASK
            black_moves = GameRules.get_legal_moves(black_board, white_board)
            white_moves = GameRules.get_legal_moves(white_board, black_board)

            if board_is_full or (not black_moves and not white_moves):
                break

            current_pieces = BitboardOps.popcount(
                black_board
            ) + BitboardOps.popcount(white_board)
            if current_pieces <= int(self.size * self.size * 50 / 64):
                states.append(self._capture_state(black_board, white_board))

            legal_moves = black_moves if current_player == 1 else white_moves

            if legal_moves:
                black_board, white_board = self._apply_minimax_move(
                    current_player, legal_moves, black_board, white_board
                )

            current_player = -current_player

        b_count = BitboardOps.popcount(black_board)
        w_count = BitboardOps.popcount(white_board)

        winner = 0
        if b_count > w_count:
            winner = 1
        elif w_count > b_count:
            winner = -1

        return states, winner

    def play_game_from_moves(
        self, moves_str: str
    ) -> Tuple[List[List[int]], int]:
        black_board, white_board = self._get_initial_board()
        current_player = 1
        states = []
        move_idx = 0

        while True:
            board_is_full = (
                (black_board | white_board) & BitboardOps.FULL_MASK
            ) == BitboardOps.FULL_MASK
            black_moves = GameRules.get_legal_moves(black_board, white_board)
            white_moves = GameRules.get_legal_moves(white_board, black_board)

            if board_is_full or (not black_moves and not white_moves):
                break

            current_pieces = BitboardOps.popcount(
                black_board
            ) + BitboardOps.popcount(white_board)
            if current_pieces <= int(self.size * self.size * 50 / 64):
                states.append(self._capture_state(black_board, white_board))

            legal_moves = black_moves if current_player == 1 else white_moves

            if legal_moves:
                if move_idx < len(moves_str):
                    col_str = moves_str[move_idx]
                    row_str = moves_str[move_idx + 1]
                    col = ord(col_str) - ord("a")
                    row = int(row_str) - 1
                    move = row * self.size + col
                    move_idx += 2

                    if (legal_moves >> move) & 1:
                        black_board, white_board = self._apply_move(
                            current_player, col, row, black_board, white_board
                        )
                    else:
                        black_board, white_board = self._apply_random_move(
                            current_player,
                            legal_moves,
                            black_board,
                            white_board,
                        )
                else:
                    black_board, white_board = self._apply_random_move(
                        current_player, legal_moves, black_board, white_board
                    )

            current_player = -current_player

        b_count = BitboardOps.popcount(black_board)
        w_count = BitboardOps.popcount(white_board)

        winner = 0
        if b_count > w_count:
            winner = 1
        elif w_count > b_count:
            winner = -1

        return states, winner

    def _write_states(
        self, writer, states, winner, size, max_cells, output_format
    ):
        for state in states:
            if output_format == "flat":
                padded_state = state + [0] * (max_cells - len(state))
                row = padded_state + [size, winner]
            else:
                grid = [[0 for _ in range(12)] for _ in range(12)]
                for y in range(size):
                    for x in range(size):
                        idx = y * size + x
                        grid[y][x] = state[idx]
                row = [str(grid), size, winner]
            writer.writerow(row)

    def generate_dataset(
        self,
        total_games: int,
        filepath: str,
        output_format: str = "flat",
        input_filepath: str = None,
    ):
        """
        Generate a dataset. If input_filepath is provided, it reads the moves
        from it and reformats it, then generates the remainder as random games.
        Draws are explicitly filtered out to improve
        binary classification training.

        :param total_games: Expected total number
        of full random games to simulate.
        :param filepath: Path to save the resulting CSV file.
        :param output_format: "flat" (1D array) or "2d" (2D grid array).
        :param input_filepath: Path to the original dataset
        with moves string to reformat.
        """
        max_cells = 144

        with open(filepath, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)

            if output_format == "flat":
                header = [f"cell_{i}" for i in range(max_cells)] + [
                    "board_size",
                    "winner",
                ]
            else:
                header = ["board_grid", "board_size", "winner"]
            writer.writerow(header)

            if input_filepath and os.path.exists(input_filepath):
                print(f"Reformatting games from {input_filepath}...")
                self.size = 8
                BitboardOps.set_board_size(8)
                with open(input_filepath, "r", encoding="utf-8") as in_csv:
                    reader = csv.reader(in_csv)
                    next(reader)  # Skip header
                    count = 0
                    for row in reader:
                        if len(row) < 3:
                            continue
                        moves_str = row[2]
                        states, original_winner = self.play_game_from_moves(
                            moves_str
                        )

                        # Drop draws
                        if original_winner == 0:
                            continue

                        self._write_states(
                            writer,
                            states,
                            original_winner,
                            8,
                            max_cells,
                            output_format,
                        )
                        count += 1
                        if count % 1000 == 0:
                            print(f"  Reformatted 8x8 games: {count}")
                print(
                    f"Finished reformatting {count} decisive games "
                    f"from {input_filepath}."
                )

                # Generate new games for the sizes 6x6, 10x10, 12x12
                games_per_size = max(1, total_games // 3)
                batches = [
                    (10, games_per_size),
                    (12, games_per_size),
                    (6, games_per_size),
                ]
            else:
                games_6x6 = int(total_games * 0.25)
                games_8x8 = int(total_games * 0.25)
                games_10x10 = int(total_games * 0.25)
                games_12x12 = int(total_games * 0.25)
                batches = [
                    (8, games_8x8),
                    (10, games_10x10),
                    (12, games_12x12),
                    (6, games_6x6),
                ]

            for size, count in batches:
                print(
                    f"Generating {count} decisive games for {size}x{size} "
                    f"board (format: {output_format})..."
                )
                self.size = size
                BitboardOps.set_board_size(size)

                # Use 'while' to ensure we get the required
                # number of games despite skipping draws
                valid_games_generated = 0
                while valid_games_generated < count:
                    states, winner = self.play_game()

                    # Save only if there's an actual winner
                    if winner != 0:
                        self._write_states(
                            writer,
                            states,
                            winner,
                            size,
                            max_cells,
                            output_format,
                        )
                        valid_games_generated += 1

                        if valid_games_generated % 100 == 0:
                            print(
                                f"{size}x{size} Progress: "
                                f"{valid_games_generated} / {count} games"
                            )


# This block is only triggered if you run this script directly in a terminal.
# (e.g., python3 model_trainer.py)
if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Generate dataset of Othello games."
    )
    parser.add_argument(
        "-n",
        "--num_games",
        type=int,
        default=3000,
        help="Total number of NEW games to simulate (default: 3000)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="othello_dataset_formatted.csv",
        help="Path to the output CSV file",
    )
    parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["flat", "2d"],
        default="flat",
        help=(
            "Output format: 'flat' for 1D array or '2d'"
            "for a matrix suitable for CNNs"
        ),
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default=None,
        help="Path to the original dataset to reformat.",
    )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=2,
        help="Depth of the minimax alpha-beta search (default: 2)",
    )

    # Extract the passed arguments
    args = parser.parse_args()

    # Initialize our generator and execute it
    trainer = ModelTrainer(depth=args.depth)
    trainer.generate_dataset(
        args.num_games, args.output, args.format, args.input
    )
    print(f"\nDataset successfully generated at '{args.output}'.")
