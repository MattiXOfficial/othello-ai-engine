import pytest

from othello.game_engine.game_rules import GameRules
from othello.orchestrator.bitboard_ops import BitboardOps


@pytest.fixture(autouse=True)
def setup_standard_board():
    """Force la taille du plateau à 8x8 avant chaque test de ce fichier.

    Cela garantit que les index 'en dur' (0-63) des tests ci-dessous
    restent valides.

    """
    BitboardOps.set_board_size(8)


def test_move_parser_valid():
    assert GameRules.move_parser("X A1") == ("X", 0)
    assert GameRules.move_parser("O H1") == ("O", 7)
    assert GameRules.move_parser("x a2") == ("X", 8)
    assert GameRules.move_parser("o H8") == ("O", 63)
    assert GameRules.move_parser("X d4") == ("X", 27)


def test_move_parser_invalid():
    with pytest.raises(ValueError, match="Invalid move format"):
        GameRules.move_parser("")  # Empty string
    with pytest.raises(ValueError, match="Invalid move format"):
        GameRules.move_parser("A1")  # Manque la couleur
    with pytest.raises(ValueError, match="Invalid move format"):
        GameRules.move_parser("X A 1")  # Too many parts
    with pytest.raises(ValueError, match=r"Invalid color \(expected X or O\)"):
        GameRules.move_parser("Z A1")
    with pytest.raises(ValueError, match="Invalid move format"):
        GameRules.move_parser("X")
    with pytest.raises(ValueError, match="Invalid coordinate"):
        GameRules.move_parser("X 1")  # Too short
    with pytest.raises(ValueError, match="Invalid coordinate"):
        GameRules.move_parser("X 1A")  # Digit start
    with pytest.raises(ValueError, match="Move out of bounds"):
        GameRules.move_parser("X I1")
    with pytest.raises(ValueError, match="Move out of bounds"):
        GameRules.move_parser("X A9")


def test_is_game_over_full():
    # Simulation: Noir occupe tout le plateau, Blanc n'a rien.
    # L'union des deux donne un masque plein.
    full_black = 0xFFFFFFFFFFFFFFFF
    empty_white = 0
    assert GameRules.is_game_over(full_black, empty_white) is True


def test_is_game_over_not_full():
    """Test que la partie continue si des coups sont possibles.

    Vérifie que le jeu ne s'arrête pas même si le plateau n'est pas plein.
    """
    # Cas 1 : Configuration type "Début de partie"
    # Noir en D4(27), E5(36). Blanc en E4(28), D5(35).
    # Des coups sont possibles pour les deux joueurs.
    black_bb = (1 << 27) | (1 << 36)
    white_bb = (1 << 28) | (1 << 35)

    assert GameRules.is_game_over(black_bb, white_bb) is False

    # Cas 2 : Configuration simple "Sandwich possible"
    # Noir en A1, Blanc en B1. Noir peut jouer en C1.
    black_bb = 1 << 0
    white_bb = 1 << 1

    assert GameRules.is_game_over(black_bb, white_bb) is False


def test_horizontal_flip():
    # Player starts at A1 (0,0) -> index = 0
    # Opponent pieces at B1 (1,0) and C1 (2,0) -> indices 1, 2
    # Player plays at D1 (3,0) -> index 3

    player_bb = 1 << 0
    opponent_bb = (1 << 1) | (1 << 2)

    # Expected flip: B1 (1<<1) and C1 (1<<2) -> mask = 6
    expected_flip = (1 << 1) | (1 << 2)

    flip_mask = GameRules.compute_flips(player_bb, opponent_bb, 3, 0)
    assert flip_mask == expected_flip


def test_vertical_flip():
    # Player starts at A1 (0,0) -> index 0
    # Opponent pieces at A2 (0,1) -> index 8
    # Player plays at A3 (0,2) -> index 16

    player_bb = 1 << 0
    opponent_bb = 1 << 8

    # Expected flip: A2 (1<<8)
    expected_flip = 1 << 8

    flip_mask = GameRules.compute_flips(player_bb, opponent_bb, 0, 2)
    assert flip_mask == expected_flip


def test_diagonal_flip():
    # Player at A1 (0,0)
    # Opponent at B2 (1,1) -> index 9
    # Plays at C3 (2,2) -> index 18

    player_bb = 1 << 0
    opponent_bb = 1 << 9

    expected_flip = 1 << 9

    flip_mask = GameRules.compute_flips(player_bb, opponent_bb, 2, 2)
    assert flip_mask == expected_flip


def test_multi_direction_flip():
    # Tested configuration:
    # Player has pieces at A1 (0,0) and A3 (0,2).
    # Opponent has pieces at B1 (1,0) and B2 (1,1).
    # Player plays at C1 (2,0).

    # Visualization:
    #   A B C
    # 1 P O X  (X = Move played at C1)
    # 2 . O .
    # 3 P . .

    # Direction analysis:
    # - West (Left): C1 -> B1(O) -> A1(P): Valid sandwich, flips B1.
    # - South-West (Diagonal): C1 -> B2(O) -> A3(P):
    # Valid sandwich, flips B2.

    # A1(0,0) and A3(0,2) -> Indices 0 and 16
    player_bb = (1 << 0) | (1 << (2 * 8 + 0))
    # B1(1,0) and B2(1,1) -> Indices 1 and 9
    opponent_bb = (1 << 1) | (1 << (1 * 8 + 1))

    expected_flip = (1 << 1) | (1 << 9)

    flip_mask = GameRules.compute_flips(player_bb, opponent_bb, 2, 0)
    assert flip_mask == expected_flip


def test_no_flip_empty_adjacent():
    # Player at A1
    # Empty at B1
    # Plays at C1
    player_bb = 1 << 0
    opponent_bb = 0
    flip_mask = GameRules.compute_flips(player_bb, opponent_bb, 2, 0)
    assert flip_mask == 0


def test_no_flip_same_color_adjacent():
    # Player at A1
    # Player at B1
    # Plays at C1 -> No flip
    player_bb = (1 << 0) | (1 << 1)
    opponent_bb = 0
    flip_mask = GameRules.compute_flips(player_bb, opponent_bb, 2, 0)
    assert flip_mask == 0


def test_sandwich_open_end():
    # Player at A1
    # Opponent at B1
    # C1 is empty
    # Plays at D1? Too far, but check from D1: C1 empty -> stop.

    player_bb = 1 << 0
    opponent_bb = 1 << 1

    # Plays at C1: sees B1(O), A1(P) -> Flips!
    # Wait, "Open end" usually means P O _
    # If I play at _, I capture.

    # Scenario: P O O (Board edge or empty)
    # Player at A1, Opponent at B1, C1.
    # D1 is empty.
    # Plays at E1 (4,0).
    # Check left: D1 empty -> stop.

    player_bb = 1 << 0
    opponent_bb = (1 << 1) | (1 << 2)
    flip_mask = GameRules.compute_flips(player_bb, opponent_bb, 4, 0)
    assert flip_mask == 0


def test_is_valid_move_basic():
    # Simple situation: P at A1, O at B1. P plays at C1 -> Valid.
    player_bb = 1 << 0
    opponent_bb = 1 << 1
    # C1 is index 2.
    assert GameRules.is_valid_move(player_bb, opponent_bb, 2, 0) is True


def test_is_valid_move_occupied_by_self():
    # P at A1. P plays at A1 -> Invalid.
    player_bb = 1 << 0
    opponent_bb = 0
    assert GameRules.is_valid_move(player_bb, opponent_bb, 0, 0) is False


def test_is_valid_move_occupied_by_opponent():
    # O at A1. P plays at A1 -> Invalid.
    player_bb = 0
    opponent_bb = 1 << 0
    assert GameRules.is_valid_move(player_bb, opponent_bb, 0, 0) is False


def test_is_valid_move_no_flip():
    # P at A1. Cell B1 empty. P plays at B1 -> Invalid (no capture).
    player_bb = 1 << 0
    opponent_bb = 0
    assert GameRules.is_valid_move(player_bb, opponent_bb, 1, 0) is False


def test_is_valid_move_out_of_bounds():
    # Out of bounds
    player_bb = 0
    opponent_bb = 0
    assert GameRules.is_valid_move(player_bb, opponent_bb, -1, 0) is False
    assert GameRules.is_valid_move(player_bb, opponent_bb, 0, 8) is False
    assert GameRules.is_valid_move(player_bb, opponent_bb, 8, 8) is False


def test_get_legal_moves_empty_board():
    # No pieces -> No legal moves (need sandwich)
    assert GameRules.get_legal_moves(0, 0) == 0


def test_get_legal_moves_simple():
    # Standard Othello Start (simplified)
    # P at D4 (27), E5 (36)
    # O at E4 (28), D5 (35)
    # P to play.
    # Legal moves for P (Black):
    # - E3 (20) -> Flips E4 (O) -> E5 (P) Sandwich vertical
    # - F4 (29) -> Flips E4 (O) -> D4 (P) Sandwich horizontal
    # - C5 (34) -> Flips D5 (O) -> E5 (P) Sandwich horizontal
    # - D6 (43) -> Flips D5 (O) -> D4 (P) Sandwich vertical

    player_bb = (1 << 27) | (1 << 36)
    opponent_bb = (1 << 28) | (1 << 35)

    legal = GameRules.get_legal_moves(player_bb, opponent_bb)

    expected = (1 << 20) | (1 << 29) | (1 << 34) | (1 << 43)
    assert legal == expected


def test_get_legal_moves_no_moves():
    # Player completely surrounded or no opponent adjacent
    player_bb = 1 << 0  # A1
    opponent_bb = 0
    assert GameRules.get_legal_moves(player_bb, opponent_bb) == 0


def test_compute_flips_break_conditions():
    # Test specific break conditions in the loop
    # Opponent piece then empty -> break (no sandwich)
    player_bb = 1 << 0  # A1
    opponent_bb = 1 << 1  # B1
    # C1 empty
    # Compute from C1 check direction West
    # It sees B1 (opp), then A1 (player) -> Valid

    # Now logic: P O _ P
    # Play at _ (C1)
    # West: O P -> Valid
    # East: P -> Invalid

    player_bb = (1 << 0) | (1 << 3)  # A1, D1
    opponent_bb = 1 << 1  # B1
    # Play C1 (2)
    # West check: B1(O), A1(P) -> Flip B1
    # East check: D1(P) -> Immedite break (same color)

    flips = GameRules.compute_flips(player_bb, opponent_bb, 2, 0)
    assert flips == (1 << 1)


@pytest.mark.parametrize("size", [6, 8, 10, 12])
def test_initial_moves_count_universal(size):
    """Vérifie le nombre de coups initiaux.

    S'assure que peu importe la taille, la position de départ offre toujours
    4 coups légaux pour les Noirs.
    """
    # 1. Configurer la taille
    BitboardOps.set_board_size(size)

    # 2. Reconstruire le plateau de départ mathématiquement
    mid = size // 2
    # Indices : Top-Left, Top-Right, Bottom-Left, Bottom-Right
    tl = (mid - 1) * size + (mid - 1)
    tr = (mid - 1) * size + mid
    bl = mid * size + (mid - 1)
    br = mid * size + mid

    # Position standard : Noir en TL/BR, Blanc en TR/BL
    black_bb = (1 << tl) | (1 << br)
    white_bb = (1 << tr) | (1 << bl)

    # 3. Demander les coups légaux
    legal_moves_mask = GameRules.get_legal_moves(black_bb, white_bb)

    # 4. Vérifier qu'il y a exactement 4 possibilités
    assert BitboardOps.popcount(legal_moves_mask) == 4


def test_calculate_score():
    """Test du calcul de score."""
    # Cas 1: Plateau vide
    assert GameRules.calculate_score(0, 0) == {"X": 0, "O": 0}

    # Cas 2: Quelques pions
    # Noir (X): 2 pions (indices 0, 1)
    # Blanc (O): 3 pions (indices 2, 3, 4)
    black_bb = (1 << 0) | (1 << 1)
    white_bb = (1 << 2) | (1 << 3) | (1 << 4)

    scores = GameRules.calculate_score(black_bb, white_bb)
    assert scores == {"X": 2, "O": 3}


def test_determine_winner():
    """Test de la détermination du vainqueur."""
    # Cas 1: Noir gagne
    black_bb = (1 << 0) | (1 << 1)  # 2 pions
    white_bb = 1 << 2  # 1 pion
    assert GameRules.determine_winner(black_bb, white_bb) == "X"

    # Cas 2: Blanc gagne
    black_bb = 1 << 0  # 1 pion
    white_bb = (1 << 1) | (1 << 2)  # 2 pions
    assert GameRules.determine_winner(black_bb, white_bb) == "O"

    # Cas 3: Match nul
    black_bb = 1 << 0  # 1 pion
    white_bb = 1 << 1  # 1 pion
    assert GameRules.determine_winner(black_bb, white_bb) == "DRAW"


def test_is_game_over_prints_winner(capsys):
    """Vérifie que is_game_over détecte la fin de partie.

    Affiche le vainqueur et les scores.
    """
    # 1. Simuler un plateau plein (Fin de partie)
    # X occupe tout sauf la dernière case (63 pions)
    # O occupe la dernière case (1 pion)
    black_bb = BitboardOps.FULL_MASK ^ 1  # 111...110
    white_bb = 1  # 000...001

    # 2. Appel de la fonction
    is_over = GameRules.is_game_over(black_bb, white_bb)

    # 3. Vérifications
    assert is_over is True

    # Récupérer ce qui a été print() dans la console
    captured = capsys.readouterr()

    # Vérifier le contenu du message
    assert "Game over! Winner: X\n" in captured.out
    assert "Final score - Black (X): 63, White (O): 1\n" in captured.out
