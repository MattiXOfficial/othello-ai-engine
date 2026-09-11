"""Selection functions and heuristics for the AI."""

from othello.game_engine.game_rules import GameRules
from othello.orchestrator.bitboard_ops import BitboardOps


def evaluate_board(state, current_player, scoring_func_name):
    """Evaluate the board from the perspective of the current_player."""
    if scoring_func_name == "function1":
        return positional_eval(state, current_player)
    elif scoring_func_name == "function2":
        return default_scoring(state, current_player)
    elif scoring_func_name == "function3":
        return dynamic_eval(state, current_player)

    return default_scoring(state, current_player)


def default_scoring(state, current_player):
    """Default evaluation function based on piece difference.

    :param state: Current game state containing `black_board` and `white_board`
      bitboards.
    :type state: GameState
    :param current_player: Current player's color ('X' for black,
        'O' for white).
    :type current_player: str
    :return: Heuristic score relative to the current player; positive favors
        the player, negative favors the opponent.
    :rtype: int

    """
    scores = GameRules.calculate_score(state.black_board, state.white_board)
    opponent = "O" if current_player == "X" else "X"
    return scores[current_player] - scores[opponent]


def positional_eval(state, current_player):
    """Evaluate the board using a positional heuristic.

    Weights strategic squares (corners, edges, and center) to estimate
    the player's advantage over the opponent.

    :param state: Current game state containing `black_board` and
        `white_board` bitboards.
    :type state: GameState
    :param current_player: Current player's color ('X' for black,
        'O' for white).
    :type current_player: str
    :return: Heuristic score relative to the current player; positive favors
        the player, negative favors the opponent.
    :rtype: int

    """
    size = BitboardOps.SIZE
    active_masks = BitboardOps.POSITIONAL_HEURISTIC_MASKS.get(size, [])

    my_bb = state.black_board if current_player == "X" else state.white_board
    opp_bb = state.white_board if current_player == "X" else state.black_board

    score = 0
    for weight, mask in active_masks:
        score += weight * (
            (my_bb & mask).bit_count() - (opp_bb & mask).bit_count()
        )

    return score


def count_stable_discs(player_bb: int, opponent_bb: int) -> int:
    """Count the number of stable discs for a given bitboard.

    A disc is considered stable if, for all 4 axes, it is connected to the
    edge by discs of the same color, or if the axis is completely full.

    """
    size = BitboardOps.SIZE
    occupied = player_bb | opponent_bb
    stable = 0

    for index in range(size * size):
        mask = 1 << index

        if not (player_bb & mask):
            continue

        col = index % size
        row = index // size

        axes = [
            ((1, 0), (-1, 0)),  # Horizontal
            ((0, 1), (0, -1)),  # Vertical
            ((1, 1), (-1, -1)),  # Diagonale 1
            ((1, -1), (-1, 1)),  # Diagonale 2
        ]

        is_stable = True

        # Un pion doit être stable sur les 4 axes pour être
        # globalement stable.
        for (d_c1, d_r1), (d_c2, d_r2) in axes:
            # Fonction utilitaire pour explorer une ligne
            # dans une direction donnée
            def check_side(d_col, d_row):
                c, r = col + d_col, row + d_row
                solid = True  # Vrai si la ligne n'est faite que de MES pions
                # Vrai s'il n'y a AUCUNE case vide vers le bord (ligne bloquée)
                no_empty = True

                while 0 <= c < size and 0 <= r < size:
                    idx = r * size + c
                    m = 1 << idx

                    # Si on rencontre une case vide,
                    # la ligne n'est ni pleine ni solide
                    if not (occupied & m):
                        no_empty = False
                        solid = False
                        break

                    # Si on rencontre un pion adverse,
                    # la ligne n'est pas solide pour le joueur
                    if not (player_bb & m):
                        solid = False

                    c += d_col
                    r += d_row

                return solid, no_empty

            # Vérifie les deux côtés opposés de l'axe courant
            solid1, no_empty1 = check_side(d_c1, d_r1)
            solid2, no_empty2 = check_side(d_c2, d_r2)

            # Un pion est stable sur un axe si :
            # 1. Il est connecté continuellement à un bord
            # par ses propres pions
            # OU 2. L'axe complet n'a plus de cases vides, impossible de jouer
            if not (solid1 or solid2 or (no_empty1 and no_empty2)):
                is_stable = False
                # Pas la peine de vérifier les autres axes si instable
                break

        # Si le pion est stable sur TOUS les 4 axes, on le compte
        if is_stable:
            stable += 1

    return stable


def stability_eval(state, current_player):
    """Evaluate the board using a stability heuristic."""
    my_bb = state.black_board if current_player == "X" else state.white_board
    opp_bb = state.white_board if current_player == "X" else state.black_board

    my_stable = count_stable_discs(my_bb, opp_bb)
    opp_stable = count_stable_discs(opp_bb, my_bb)

    return my_stable - opp_stable


def dynamic_eval(state, current_player):
    """Evaluate the board using a dynamic heuristic that adapts the strategy.

    :param state: Current game state containing `black_board` and
        `white_board` bitboards.
    :type state: GameState
    :param current_player: Current player's color ('X' for black,
        'O' for white).
    :type current_player: str
    :return: Heuristic score relative to the current player; positive favors
        the player, negative favors the opponent.
    :rtype: int

    """
    size = BitboardOps.SIZE
    total_slots = size * size
    total_pieces = (
        state.black_board.bit_count() + state.white_board.bit_count()
    )
    progress = total_pieces / total_slots

    if progress < 0.35:
        return default_scoring(state, current_player)
    elif progress < 0.75:
        return positional_eval(state, current_player)
    else:
        return stability_eval(state, current_player)
