import pytest

from othello.orchestrator.bitboard_ops import BitboardOps


# On applique ce décorateur pour que CHAQUE test tourne sur les 4 tailles
@pytest.mark.parametrize("size", [6, 8, 10, 12])
class TestBitboardDynamic:
    def setup_method(self, method):
        """Avant chaque test, on configure la bonne taille."""
        pass

    def test_set_board_size_integrity(self, size):
        """Vérifie que la reconfiguration recalcule bien les masques.

        Et directions.
        """
        BitboardOps.set_board_size(size)

        # 1. Vérif Taille
        assert BitboardOps.SIZE == size

        # 2. Vérif Masque Plein (Tous les bits à 1 pour la taille donnée)
        expected_full_mask = (1 << (size * size)) - 1
        assert BitboardOps.FULL_MASK == expected_full_mask

        # 3. Vérif Directions (Nord/Sud doivent valoir +/- size)
        assert BitboardOps.DIRECTIONS["SOUTH"][0] == size
        assert BitboardOps.DIRECTIONS["NORTH"][0] == -size

        # 4. Vérif Masques Colonnes (Anti-Pacman)
        # MASK_NOT_A ne doit PAS avoir le bit 0 (A1)
        assert (BitboardOps.MASK_NOT_A & 1) == 0
        # MASK_NOT_H ne doit PAS avoir le bit size-1 (Dernière col, 1ère ligne)
        assert (BitboardOps.MASK_NOT_H & (1 << (size - 1))) == 0

    def test_set_token(self, size):
        BitboardOps.set_board_size(size)
        board = 0
        # Place en A1 (index 0)
        board = BitboardOps.set_token(board, 0)
        assert board == 1

        # Place en B1 (index 1)
        board = BitboardOps.set_token(board, 1)
        assert board == 3  # 1 + 2

    def test_get_token(self, size):
        BitboardOps.set_board_size(size)
        # Plateau avec A1(0) et C1(2)
        board = 5  # 101 en binaire

        assert BitboardOps.get_token(board, 0) == 1
        assert BitboardOps.get_token(board, 2) == 1
        assert BitboardOps.get_token(board, 1) == 0

        # Vérifie une case loin (Dernière case du plateau)
        last_index = (size * size) - 1
        assert BitboardOps.get_token(board, last_index) == 0

    def test_popcount(self, size):
        BitboardOps.set_board_size(size)
        # Vide
        assert BitboardOps.popcount(0) == 0

        # Plein (doit être égal au nombre de cases total)
        assert BitboardOps.popcount(BitboardOps.FULL_MASK) == size * size

        # Quelques pions (11 = 1011 bin -> 3 pions)
        assert BitboardOps.popcount(11) == 3

    def test_shift_basic_cardinal(self, size):
        """Test des mouvements depuis B2 (Case interne)."""
        BitboardOps.set_board_size(size)

        # B2 se trouve à la ligne 1, col 1.
        # Index = 1 * size + 1
        index_b2 = size + 1
        start_pos = 1 << index_b2

        # EAST (+1) -> C2 (index + 1)
        expected = 1 << (index_b2 + 1)
        assert BitboardOps.shift_direction(start_pos, "EAST") == expected

        # WEST (-1) -> A2 (index - 1)
        expected = 1 << (index_b2 - 1)
        assert BitboardOps.shift_direction(start_pos, "WEST") == expected

        # SOUTH (+size) -> B3 (index + size)
        expected = 1 << (index_b2 + size)
        assert BitboardOps.shift_direction(start_pos, "SOUTH") == expected

        # NORTH (-size) -> B1 (index - size)
        expected = 1 << (index_b2 - size)
        assert BitboardOps.shift_direction(start_pos, "NORTH") == expected

    def test_shift_prevent_wrapping_east(self, size):
        """ANTI-PACMAN: Vérifie que le bord droit ne saute pas à gauche."""
        BitboardOps.set_board_size(size)

        # Pion sur le bord droit de la ligne 1. Index = size - 1.
        # Ex: H1 (7) en 8x8, F1 (5) en 6x6.
        edge_index = size - 1
        pawn_edge = 1 << edge_index

        # EAST doit donner 0 (tombé du plateau) et pas l'index suivant (size)
        assert BitboardOps.shift_direction(pawn_edge, "EAST") == 0

        # Idem pour diag NE
        assert BitboardOps.shift_direction(pawn_edge, "NORTH_EAST") == 0

    def test_shift_prevent_wrapping_west(self, size):
        """ANTI-PACMAN: Vérifie que le bord gauche ne saute pas à droite."""
        BitboardOps.set_board_size(size)

        # Pion sur le bord gauche de la ligne 2. Index = size.
        # Ex: A2 (8) en 8x8.
        edge_index = size
        pawn_edge = 1 << edge_index

        # WEST doit donner 0
        assert BitboardOps.shift_direction(pawn_edge, "WEST") == 0

    def test_shift_overflow_limit(self, size):
        """Vérifie que les pions disparaissent s'ils sortent verticalement."""
        BitboardOps.set_board_size(size)

        # Dernier pion du plateau (Bas-Droite)
        last_index = (size * size) - 1
        pawn_last = 1 << last_index

        # SOUTH -> Disparition
        assert BitboardOps.shift_direction(pawn_last, "SOUTH") == 0

        # Premier pion (A1)
        pawn_first = 1
        # NORTH -> Disparition
        assert BitboardOps.shift_direction(pawn_first, "NORTH") == 0
