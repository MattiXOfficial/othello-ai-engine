from unittest.mock import patch

from othello.game_engine.game_rules import GameRules
from othello.game_engine.game_state import GameState
from othello.orchestrator.bitboard_ops import BitboardOps
from othello.player.ai_player import AIPlayer

"""
!!!!!!!!!!!!!!!!!!!!!!
THIS FILE IS NOT A TEST, IT'S A SCRIPT TO TEST THE DIFFERENT AI'S PERFORMANCES
!!!!!!!!!!!!!!!!!!!!!!
"""


def evaluate_ais(
    algo1: str,
    algo2: str,
    max_time: float,
    num_games: int,
    heur1: str = "function2",
    heur2: str = "function2",
    size: int = 8,
):
    """Évalue deux algorithmes IA.

    Joue un certain nombre de parties l'un contre l'autre.
    Utilise unittest.mock pour éviter de charger toute la config de base.
    """
    algo_configs = {
        "minmax": {
            "ai_mode": "minimax",
            "ai_time": max_time,
            "ai_minimax_depth": None,
        },
        "iterative deepening": {
            "ai_mode": "iterative",
            "ai_time": max_time,
            "ai_minimax_depth": None,
        },
        "mcts DL": {
            "ai_mode": "mcts",
            "ai_time": max_time,
            "ai_mcts_selection": "DL",
        },
        "mcts ML": {
            "ai_mode": "mcts",
            "ai_time": max_time,
            "ai_mcts_selection": "ML",
        },
        "mcts UCB": {
            "ai_mode": "mcts",
            "ai_time": max_time,
            "ai_mcts_selection": "UCB",
        },
        "random": {"ai_mode": "random", "ai_time": max_time},
    }

    if algo1 not in algo_configs or algo2 not in algo_configs:
        print(
            "Algorithmes non reconnus. Choix valides :",
            list(algo_configs.keys()),
        )
        return

    config1 = algo_configs[algo1].copy()
    config2 = algo_configs[algo2].copy()

    if config1["ai_mode"] in ["minimax", "iterative"]:
        config1["ai_minimax_scoring"] = heur1
    if config2["ai_mode"] in ["minimax", "iterative"]:
        config2["ai_minimax_scoring"] = heur2

    algo1_display = (
        f"{algo1} ({heur1})"
        if config1["ai_mode"] in ["minimax", "iterative"]
        else algo1
    )
    algo2_display = (
        f"{algo2} ({heur2})"
        if config2["ai_mode"] in ["minimax", "iterative"]
        else algo2
    )

    wins_algo1 = 0
    wins_algo2 = 0
    draws = 0

    print(
        f"évaluation: {algo1_display} vs {algo2_display} "
        f"({num_games} parties, temps: {max_time}s, taille: {size}x{size})"
    )

    BitboardOps.set_board_size(size)

    with patch("othello.player.ai_player.ConfigManager"):
        p_algo1 = AIPlayer("X")
        p_algo1.setup_algo_parameters(config1)
        p_algo1.debug = False

        p_algo2 = AIPlayer("O")
        p_algo2.setup_algo_parameters(config2)
        p_algo2.debug = False

        for i in range(num_games):
            if i % 2 == 0:
                player_x_name = algo1_display
                player_o_name = algo2_display
                p_x = p_algo1
                p_x.color = "X"
                p_o = p_algo2
                p_o.color = "O"
            else:
                player_x_name = algo2_display
                player_o_name = algo1_display
                p_x = p_algo2
                p_x.color = "X"
                p_o = p_algo1
                p_o.color = "O"

            state = GameState()
            state.initialize_default()
            current_player = "X"

            while not GameRules.is_terminal_state(
                state.black_board, state.white_board
            ):
                moves = state.get_legal_moves_indices(current_player)
                if not moves:
                    current_player = "O" if current_player == "X" else "X"
                    continue

                if current_player == "X":
                    move_str = p_x.get_move(state)
                else:
                    move_str = p_o.get_move(state)

                if move_str is None:
                    move_str = AIPlayer.random_move(
                        (state.white_board, state.black_board), current_player
                    )

                _, move_idx = GameRules.move_parser(move_str)
                state, current_player = state.apply_move(
                    current_player, move_idx
                )

            winner = GameRules.determine_winner(
                state.black_board, state.white_board
            )
            if winner == "DRAW":
                draws += 1
            elif winner == "X":
                if player_x_name == algo1_display:
                    wins_algo1 += 1
                else:
                    wins_algo2 += 1
            elif winner == "O":
                if player_o_name == algo1_display:
                    wins_algo1 += 1
                else:
                    wins_algo2 += 1

            print(f"Partie {i+1}/{num_games} terminée. Win {winner}")

    total_wins = wins_algo1 + wins_algo2
    if total_wins > 0:
        winrate1 = (wins_algo1 / total_wins) * 100
    else:
        winrate1 = 0.0

    if wins_algo1 > wins_algo2:
        print(f"Vainqueur : {algo1_display} {winrate1:.0f}%")
    elif wins_algo2 > wins_algo1:
        winrate2 = (wins_algo2 / total_wins) * 100 if total_wins > 0 else 0.0
        print(f"Vainqueur : {algo2_display} {winrate2:.0f}%")
    else:
        print("Vainqueur : Égalité 50%")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Évaluer deux algorithmes d'IA sur plusieurs parties."
    )
    parser.add_argument(
        "--algo1",
        type=str,
        required=True,
        help="1er algo: minmax, iterative deepening, mcts DL, "
        "mcts ML, mcts UCB, random",
    )
    parser.add_argument(
        "--algo2", type=str, required=True, help="Nom du second algorithme"
    )
    parser.add_argument(
        "--time",
        type=float,
        default=1.0,
        help="Temps max de réflexion par coup (secondes)",
    )
    parser.add_argument(
        "--games", type=int, default=10, help="Nombre de parties à jouer"
    )
    parser.add_argument(
        "--heur1",
        type=str,
        choices=["function1", "function2", "function3"],
        default="function2",
        help="Heuristique pour le premier algorithme si minmax/iterative",
    )
    parser.add_argument(
        "--heur2",
        type=str,
        choices=["function1", "function2", "function3"],
        default="function2",
        help="Heuristique pour le second algorithme si minmax/iterative",
    )
    parser.add_argument(
        "--size",
        type=int,
        choices=[6, 8, 10, 12],
        default=8,
        help="Taille du plateau (6, 8, 10, 12)",
    )

    args = parser.parse_args()
    evaluate_ais(
        args.algo1,
        args.algo2,
        args.time,
        args.games,
        args.heur1,
        args.heur2,
        args.size,
    )
