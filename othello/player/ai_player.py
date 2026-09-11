"""AI Player Module."""

import math
import os
import random
import sys
import threading
import warnings

import joblib
import numpy as np

from othello.artificial_intelligence.selection_functions import evaluate_board
from othello.common.config_manager import ConfigManager
from othello.common.i18n_manager import I18nManager
from othello.game_engine.game_rules import GameRules
from othello.orchestrator.bitboard_ops import BitboardOps
from othello.player.interface_player import Player
from othello.player.search_runner import SearchRunner


def _(message):
    return I18nManager().gettext(message)


def ucb1(node):
    """UCB1 selection function."""
    if node.visits == 0:
        return float("inf")  # denominator is 0 : term is infinite

    # sqrt(2) = good theorical tradeoff between exploration/exploitation
    exploration_weight = 1.414

    average_value = node.value / node.visits
    parent_visits_log = math.log(node.parent.visits)
    exploration_term = exploration_weight * math.sqrt(
        parent_visits_log / node.visits
    )

    return average_value + exploration_term


class MCTSNode:
    """Node for the Monte Carlo Tree Search."""

    def __init__(self, state, current_player, parent=None, move=None):
        self.state = state  # GameState object
        self.current_player = current_player  # 'X' or 'O'
        self.parent = parent
        self.move = move
        self.children = []
        self.visits = 0
        self.value = 0.0
        self.untried_moves = self.state.get_legal_moves_indices(current_player)


class AIPlayer(Player):
    """AI Player implementation of the Player interface."""

    def __init__(self, color: str):
        super().__init__(color)
        self.ai_mode = None
        self.config = ConfigManager().config_parser["defaults"]
        if self.config.get("debug") == "true":
            self.debug = True
        else:
            self.debug = False
        self.shared_best_move = None
        self.move_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.setup_algo_parameters(self.config)

    def setup_algo_parameters(self, config):
        """Setup the parameters for the AI algorithm based on configuration."""
        self.ai_mode = config.get("ai_mode", "minimax")
        self.mcts_selection = config.get("ai_mcts_selection", "UCT")

        self.ai_minimax_depth = config.get("ai_minimax_depth", None)
        if self.ai_minimax_depth is not None:
            self.ai_minimax_depth = int(self.ai_minimax_depth)

        self.ai_time = config.get("ai_time", None)
        if self.ai_time is not None:
            self.ai_time = float(self.ai_time)

        self.ai_minimax_scoring = config.get(
            "ai_minimax_scoring", "default_scoring"
        )

        if self.mcts_selection == "DL":
            from keras.models import load_model

            model_path = os.path.join(
                os.path.dirname(__file__),
                "../artificial_intelligence/models/cnn_model.keras",
            )
            self.model = load_model(model_path)
            self.is_cnn = True
            print(
                _("Loaded Deep Learning (CNN) model {path}").format(
                    path=model_path
                )
            )

        elif self.mcts_selection == "ML":
            try:
                model_path = os.path.join(
                    os.path.dirname(__file__),
                    "../artificial_intelligence/models/"
                    "random_forest_model.pkl",
                )
                self.model = joblib.load(model_path)
                self.is_cnn = False
                print(
                    _("Loaded Machine Learning (RF) model {path}").format(
                        path=model_path
                    )
                )
            except Exception as e:
                print(
                    _("Error loading Machine Learning model: {error}").format(
                        error=e
                    )
                )
                self.model = None

    def predict_depth(self, game_state, current_player, time_limit):
        """Estimate the feasible minimax depth within a given time limit."""
        if time_limit is None or time_limit <= 0:
            return 5

        moves = game_state.get_legal_moves_indices(current_player)
        branching_factor = max(1, len(moves))

        # empirical constants from benchmark
        base_time = 0.0002
        growth = 3.08

        depth = 1 + math.log(time_limit / base_time) / math.log(growth)

        # mild correction for branching factor (reference ≈6 moves)
        depth -= math.log(branching_factor / 6) / math.log(growth)
        if self.debug:
            print(
                _("[DEBUG] number of moves : {moves}").format(
                    moves=branching_factor
                )
            )
            print(_("[DEBUG] depth: {depth}").format(depth=depth))
        return max(1, int(depth) - 1)

    def get_move(self, game_state, view=None) -> str:
        """Uses an AI algorithm to calculate and return the best move."""
        timeout = self.ai_time if self.ai_time is not None else 5.0

        runner = SearchRunner(self, game_state)
        return runner.run(timeout)

    def negamax(
        self,
        state,
        current_player,
        depth,
        alpha,
        beta,
        scoring_func_name,
    ):
        """Internal recursive Negamax algorithm with alpha-beta pruning."""
        if getattr(self, "stop_event", None) and self.stop_event.is_set():
            return float("-inf"), None

        if depth == 0 or GameRules.is_terminal_state(
            state.black_board, state.white_board
        ):
            return (
                evaluate_board(state, current_player, scoring_func_name),
                None,
            )

        best_score = float("-inf")
        best_move = None
        moves = state.get_legal_moves_indices(current_player)

        if not moves:
            next_player = "O" if current_player == "X" else "X"
            score, _ = self.negamax(
                state, next_player, depth, -beta, -alpha, scoring_func_name
            )
            score = -score
            return score, None

        for move in moves:
            next_state, next_player = state.apply_move(current_player, move)

            if next_player == current_player:
                score, _ = self.negamax(
                    next_state,
                    next_player,
                    depth - 1,
                    alpha,
                    beta,
                    scoring_func_name,
                )
            else:
                score, _ = self.negamax(
                    next_state,
                    next_player,
                    depth - 1,
                    -beta,
                    -alpha,
                    scoring_func_name,
                )
                score = -score

            if score > best_score:
                best_score = score
                best_move = move

            alpha = max(alpha, best_score)
            if alpha >= beta:
                break

        return best_score, best_move

    def minimax(
        self,
        state,
        current_player,
        depth,
        alpha,
        beta,
        scoring_func_name,
        debug=False,
    ):
        """Minimax algorithm with alpha-beta pruning using Negamax approach."""
        best_score = float("-inf")
        best_move = None
        moves = state.get_legal_moves_indices(current_player)

        if not moves:
            return None

        for move in moves:
            next_state, next_player = state.apply_move(current_player, move)

            if next_player == current_player:
                score, _ = self.negamax(
                    next_state,
                    next_player,
                    depth - 1,
                    alpha,
                    beta,
                    scoring_func_name,
                )
            else:
                score, _ = self.negamax(
                    next_state,
                    next_player,
                    depth - 1,
                    -beta,
                    -alpha,
                    scoring_func_name,
                )
                score = -score

            if score > best_score:
                best_score = score
                best_move = move

                col = best_move % BitboardOps.SIZE
                row = best_move // BitboardOps.SIZE
                move_str = f"{current_player} {chr(ord('a') + col)}{row + 1}"
                with self.move_lock:
                    self.shared_best_move = move_str

            alpha = max(alpha, best_score)
            if alpha >= beta:
                break

        if best_move is not None:
            col = best_move % BitboardOps.SIZE
            row = best_move // BitboardOps.SIZE
            return f"{current_player} {chr(ord('a') + col)}{row + 1}"
        return None

    def it_deepening(
        self,
        state,
        current_player,
        depth,
        alpha,
        beta,
        scoring_func_name,
        debug=False,
    ):
        """Iterative deepening search algorithm."""
        current_depth = 1
        best_move = None

        limit_depth = (
            depth if depth is not None and depth > 1 else float("inf")
        )

        while current_depth <= limit_depth:
            if self.stop_event.is_set():
                break

            score, move = self.negamax(
                state,
                current_player,
                current_depth,
                alpha,
                beta,
                scoring_func_name,
            )

            if move is not None:
                best_move = move
                col = best_move % BitboardOps.SIZE
                row = best_move // BitboardOps.SIZE
                move_str = f"{current_player} {chr(ord('a') + col)}{row + 1}"
                with self.move_lock:
                    self.shared_best_move = move_str

            current_depth += 1

        if best_move is None:
            return None

        col = best_move % BitboardOps.SIZE
        row = best_move // BitboardOps.SIZE
        return f"{current_player} {chr(ord('a') + col)}{row + 1}"

    def ml_dl_selection(self, node):
        """Custom MCTS Selection using ML/DL model prediction."""
        if node.visits == 0:
            return float("inf")

        size = BitboardOps.SIZE
        black_board = node.state.black_board
        white_board = node.state.white_board

        ml_score = 0.0
        if hasattr(self, "model") and self.model is not None:
            if self.stop_event.is_set():
                return 0.0

            if getattr(self, "is_cnn", False):
                # CNN inference [batch, height, width, channels]
                grid = [[0 for _ in range(12)] for _ in range(12)]
                for y in range(size):
                    for x in range(size):
                        idx = y * size + x
                        if (black_board >> idx) & 1:
                            grid[y][x] = 1
                        elif (white_board >> idx) & 1:
                            grid[y][x] = -1
                ml_input = np.array(grid).reshape(1, 12, 12, 1)
                proba = self.model.predict(ml_input, verbose=0)[0][0]

                ml_score = (proba * 2) - 1

            else:
                # Random Forest Inference
                flat_array = []
                for k in range(size * size):
                    if (black_board >> k) & 1:
                        flat_array.append(1)
                    elif (white_board >> k) & 1:
                        flat_array.append(-1)
                    else:
                        flat_array.append(0)

                # Expand array to reach 144 max cells
                flat_array += [0] * (144 - len(flat_array))

                ml_input = np.array(flat_array).reshape(1, -1)

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    if hasattr(self.model, "predict_proba"):
                        proba = self.model.predict_proba(ml_input)[0]
                        ml_score = (proba[1] * 2) - 1
                    else:
                        pred = self.model.predict(ml_input)[0]
                        ml_score = 1 if pred > 0 else -1

            node_player = 1 if node.parent.current_player == "X" else -1
            ml_score = ml_score if node_player == 1 else -ml_score

        return ml_score

    def mcts(
        self,
        game_state,
        current_player,
        n_iter,
        selection_function=None,
        debug=False,
    ):
        """Monte Carlo Tree Search algorithm."""
        if selection_function is None:
            if self.mcts_selection in ["ML", "DL"]:
                selection_function = self.ml_dl_selection
            else:
                selection_function = ucb1

        if debug:
            print(
                _(
                    "\n--- MCTS starting for player "
                    "{player} with {n} iterations ---"
                ).format(player=current_player, n=n_iter)
            )

        root = MCTSNode(game_state, current_player)

        i = 0
        try:
            while True:
                if self.stop_event.is_set():
                    if debug:
                        print(
                            _("Soft stop triggered at iteration {i}.").format(
                                i=i
                            )
                        )
                    break

                if n_iter is not None and i >= n_iter:
                    if debug:
                        print(_("Stopped at iteration {i}.").format(i=i))
                    break

                if root.children:
                    best_c = max(root.children, key=lambda c: c.visits)
                    c_col = best_c.move % BitboardOps.SIZE
                    c_row = best_c.move // BitboardOps.SIZE
                    move_str = (
                        f"{current_player} {chr(ord('a') + c_col)}{c_row + 1}"
                    )
                    with self.move_lock:
                        self.shared_best_move = move_str

                i += 1
                node = root
                depth = 0

                while not node.untried_moves and node.children:
                    if self.stop_event.is_set():
                        break
                    node = max(node.children, key=selection_function)
                    depth += 1

                if debug and i == 0:
                    print(
                        _(" - Selection reached depth {depth}").format(
                            depth=depth
                        )
                    )

                if node.untried_moves:
                    move = random.choice(node.untried_moves)
                    node.untried_moves.remove(move)
                    next_state, next_player = node.state.apply_move(
                        node.current_player, move
                    )
                    child = MCTSNode(
                        next_state, next_player, parent=node, move=move
                    )
                    node.children.append(child)
                    node = child
                    if debug and i == 0:
                        col = move % BitboardOps.SIZE
                        row = move // BitboardOps.SIZE
                        print(
                            _(" - Expansion: added move {char}{row}").format(
                                char=chr(ord("A") + col), row=row + 1
                            )
                        )

                sim_state = node.state
                sim_player = node.current_player

                while not GameRules.is_terminal_state(
                    sim_state.black_board, sim_state.white_board
                ):
                    if self.stop_event.is_set():
                        break
                    moves = sim_state.get_legal_moves_indices(sim_player)
                    if not moves:
                        sim_player = "O" if sim_player == "X" else "X"
                        continue
                    move = random.choice(moves)
                    sim_state, sim_player = sim_state.apply_move(
                        sim_player, move
                    )

                winner = GameRules.determine_winner(
                    sim_state.black_board, sim_state.white_board
                )
                if winner == "DRAW":
                    winner = "DRAW"
                elif winner == "X":
                    winner = 1
                elif winner == "O":
                    winner = -1
                else:
                    winner = winner

                if debug and i == 0:
                    print(
                        _(
                            " - Simulation (Rollout): "
                            "outcome winner = {winner}"
                        ).format(winner=winner)
                    )

                temp_node = node
                while temp_node is not None:
                    temp_node.visits += 1
                    if temp_node.parent is not None:
                        node_player = (
                            1 if temp_node.parent.current_player == "X" else -1
                        )
                        if winner == node_player:
                            temp_node.value += 1.0
                        elif winner == "DRAW":
                            temp_node.value += 0.5
                    temp_node = temp_node.parent
        finally:
            if debug:
                status = (
                    _("Finished")
                    if (n_iter is not None and i >= n_iter)
                    else _("Interrupted by timeout")
                )
                print(
                    _(
                        "--- MCTS Completed ({status} at iteration {i}) ---"
                    ).format(status=status, i=i)
                )
                for c in root.children:
                    col = c.move % BitboardOps.SIZE
                    row = c.move // BitboardOps.SIZE
                    move_str = f"{chr(ord('A') + col)}{row + 1}"
                    print(
                        _(
                            " Move {move}: {visits} visits, {wins:.1f} wins"
                        ).format(move=move_str, visits=c.visits, wins=c.value)
                    )

                if root.children:
                    best_child = max(root.children, key=lambda c: c.visits)
                    col = best_child.move % BitboardOps.SIZE
                    row = best_child.move // BitboardOps.SIZE
                    move_str = f"{chr(ord('A') + col)}{row + 1}"
                    print(
                        _(
                            " Selected Move: {move} with {visits} visits\n"
                        ).format(move=move_str, visits=best_child.visits)
                    )

        if not root.children:
            if debug:
                print(_(" No legal moves found, using fallback random move."))
            board = (game_state.white_board, game_state.black_board)
            return AIPlayer.random_move(board, current_player)

        best_child = max(root.children, key=lambda c: c.visits)
        col = best_child.move % BitboardOps.SIZE
        row = best_child.move // BitboardOps.SIZE
        move_str = f"{chr(ord('A') + col)}{row + 1}"
        return f"{current_player} {move_str.lower()}"

    @staticmethod
    def random_move(board, current_player):
        """Return a random valid move for the current player."""
        white_bb, black_bb = board

        if current_player == "X":  # black
            moves = GameRules.get_moves_as_strings(black_bb, white_bb)
        elif current_player == "O":  # white
            moves = GameRules.get_moves_as_strings(white_bb, black_bb)
        else:
            raise ValueError("Invalid player color")

        if not moves:
            print(
                _(
                    "bug : prompted to choose a move when no legal moves "
                    "are possible (that should not happen!) -> should check "
                    "for possible moves before prompting "
                )
            )
            sys.exit(1)

        # Prepend the current player color to each move : e4 becomes X e4
        moves_with_color = [
            f"{current_player} {move.lower()}" for move in moves
        ]

        return random.choice(moves_with_color)
