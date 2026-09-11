"""BitBoards Operations Module."""


class BitboardOps:
    """BitboardOps Class."""

    """
Plateau 6x6 avec poids pour l'heuristique :.

    15   3   3   3   3  15
    3   3   3   3   3   3
    3   3   3   3   3   3
    3   3   3   3   3   3
    3   3   3   3   3   3
    15   3   3   3   3  15
"""

    """
Plateau 8x8 avec poids pour l'heuristique :.

    120 -20  20   5   5  20 -20 120
    -20 -40  -5  -5  -5  -5 -40 -20
     20  -5  15   3   3  15  -5  20
      5  -5   3   3   3   3  -5   5
      5  -5   3   3   3   3  -5   5
     20  -5  15   3   3  15  -5  20
    -20 -40  -5  -5  -5  -5 -40 -20
    120 -20  20   5   5  20 -20 120
"""

    """
Plateau 10x10 avec poids pour l'heuristique :.

    120  -40   20    5    5    5    5   20  -40  120
    -40  -40   -5   -5   -5   -5   -5  -5  -40  -40
    20   -5   15    3    3    3    3   15   -5   20
    5   -5    3    3    3    3    3    3   -5    5
    5   -5    3    3    3    3    3    3   -5    5
    5   -5    3    3    3    3    3    3   -5    5
    5   -5    3    3    3    3    3    3   -5    5
    20   -5   15    3    3    3    3   15   -5   20
    -40  -40   -5   -5   -5   -5   -5  -5  -40  -40
    120  -40   20    5    5    5    5   20  -40  120
"""

    """
12x12.

       120  -40   20    5    5    5    5   20  -40 120   5    5
       -40  -40   -5   -5   -5   -5   -5  -5  -40 -40  -5   -5
       20   -5   15    3    3    3    3   15   -5  20   3    3
       5   -5    3    3    3    3    3    3   -5   5    3    3
       5   -5    3    3    3    3    3    3   -5   5    3    3
       5   -5    3    3    3    3    3    3   -5   5    3    3
       5   -5    3    3    3    3    3    3   -5   5    3    3
       20   -5   15    3    3    3    3   15   -5  20   3    3
       -40  -40   -5   -5   -5   -5   -5  -5  -40 -40  -5   -5
       120  -40   20    5    5    5    5   20  -40 120   5    5
       -5    -5    3    3    3    3    3    3   -5  -5    3    3
       -5    -5    3    3    3    3    3    3   -5  -5    3    3
"""
    POSITIONAL_HEURISTIC_MASKS = {
        6: [
            (15, 0x84000000021),
            (3, 0x7BDEF7BDE),
        ],
        8: [
            (120, 0x8100000000000081),
            (-20, 0x4281000000008142),
            (20, 0x2400810000810024),
            (15, 0x0000240000240000),
            (5, 0x1800008181000018),
            (3, 0x0000182424180000),
            (-5, 0x0042004242004200),
            (-40, 0x0000000042000042),
        ],
        10: [
            (
                120,
                int(
                    "20100000000000000000000000000000"
                    "00000000000000000000000000000004",
                    16,
                ),
            ),
            (
                -40,
                int(
                    "00080000000000000000000000000000"
                    "00000000000000000000000000000010",
                    16,
                ),
            ),
            (
                -20,
                int(
                    "10420000000000000000000000000000"
                    "00000000000000000000000000000842",
                    16,
                ),
            ),
            (
                20,
                int(
                    "08400000000000000000000000000000"
                    "00000000000000000000000000000210",
                    16,
                ),
            ),
            (
                15,
                int(
                    "00010800000000000000000000000000"
                    "00000000000000000000000000010800",
                    16,
                ),
            ),
            (
                5,
                int(
                    "00200000000000000000000000000000"
                    "00000000000000000000000000000400",
                    16,
                ),
            ),
            (
                3,
                int(
                    "00001800000000000000000000000000"
                    "00000000000000000000000000018000",
                    16,
                ),
            ),
            (
                -5,
                int(
                    "00042000000000000000000000000000"
                    "00000000000000000000000000042000",
                    16,
                ),
            ),
        ],
        12: [
            (
                120,
                int(
                    "80000000000000000000000000000000"
                    "00000000000000000000000000000001",
                    16,
                ),
            ),
            (
                -40,
                int(
                    "04000000000000000000000000000000"
                    "00000000000000000000000000000020",
                    16,
                ),
            ),
            (
                -20,
                int(
                    "82000000000000000000000000000000"
                    "00000000000000000000000000000041",
                    16,
                ),
            ),
            (
                20,
                int(
                    "41000000000000000000000000000000"
                    "00000000000000000000000000000082",
                    16,
                ),
            ),
            (
                15,
                int(
                    "00210000000000000000000000000000"
                    "0000000000000000000000000210000",
                    16,
                ),
            ),
            (
                5,
                int(
                    "00084000000000000000000000000000"
                    "0000000000000000000000000008400",
                    16,
                ),
            ),
            (
                3,
                int(
                    "00001800000000000000000000000000"
                    "0000000000000000000000000001800",
                    16,
                ),
            ),
            (
                -5,
                int(
                    "00042000000000000000000000000000"
                    "0000000000000000000000000004200",
                    16,
                ),
            ),
        ],
    }

    SIZE = 8
    # --- MASQUES DE BORDURES (Anti-Débordement) ---
    MASK_NOT_A = 0xFEFEFEFEFEFEFEFE  # Tout sauf la colonne A (Gauche)
    MASK_NOT_H = 0x7F7F7F7F7F7F7F7F  # Tout sauf la colonne H (Droite)
    # Masque plein (64 bits à 1) : Sert à "couper" ce qui dépasse 64 bits
    FULL_MASK = 0xFFFFFFFFFFFFFFFF

    # --- DÉFINITION DES DIRECTIONS ---
    # Format : (Décalage, Masque à appliquer AVANT le décalage)
    # Positif = Vers la gauche (<<), Négatif = Vers la droite (>>)
    DIRECTIONS = {
        "NORTH": (-8, 0xFFFFFFFFFFFFFFFF),  # Pas de risque latéral
        "SOUTH": (8, 0xFFFFFFFFFFFFFFFF),
        "EAST": (1, MASK_NOT_H),  # Ne pas dépasser H
        "WEST": (-1, MASK_NOT_A),  # Ne pas dépasser A
        "NORTH_EAST": (-7, MASK_NOT_H),  # -8 (N) + 1 (E)
        "NORTH_WEST": (-9, MASK_NOT_A),  # -8 (N) - 1 (W)
        "SOUTH_EAST": (9, MASK_NOT_H),  # +8 (S) + 1 (E)
        "SOUTH_WEST": (7, MASK_NOT_A),  # +8 (S) - 1 (W)
    }

    @classmethod
    def set_board_size(cls, size: int):
        """Recalculate masks and constants according to the board size.

        :param size: The new dimension of the board (e.g., 8).

        """
        cls.SIZE = size
        cls.FULL_MASK = (1 << (size * size)) - 1
        # 1. Génération dynamique des masques de colonnes (Gauche/Droite)
        # On doit interdire la colonne A (index 0, size, 2*size...)
        # pour les déplacements OUEST
        # On doit interdire la dernière colonne (size-1, 2*size-1...)
        # pour les déplacements EST

        col_a_mask = 0
        col_last_mask = 0

        for row in range(size):
            # Ajoute le bit de la colonne de gauche (0, 8, 16...)
            col_a_mask |= 1 << (row * size)
            # Ajoute le bit de la colonne de droite (7, 15, 23...)
            col_last_mask |= 1 << ((row * size) + (size - 1))

        # Le masque "NOT A" est l'inverse de la colonne A
        # (limité au FULL_MASK)
        cls.MASK_NOT_A = cls.FULL_MASK ^ col_a_mask
        cls.MASK_NOT_H = cls.FULL_MASK ^ col_last_mask

        # 2. Reconstitution du dictionnaire DIRECTIONS avec les
        # nouvelles valeurs
        cls.DIRECTIONS = {
            "NORTH": (-size, cls.FULL_MASK),
            "SOUTH": (size, cls.FULL_MASK),
            "EAST": (1, cls.MASK_NOT_H),
            "WEST": (-1, cls.MASK_NOT_A),
            # NE: Nord (-size) + Est (+1)
            "NORTH_EAST": (-size + 1, cls.MASK_NOT_H),
            # NW: Nord (-size) + Ouest (-1)
            "NORTH_WEST": (-size - 1, cls.MASK_NOT_A),
            # SE: Sud (+size) + Est (+1)
            "SOUTH_EAST": (size + 1, cls.MASK_NOT_H),
            # SW: Sud (+size) + Ouest (-1)
            "SOUTH_WEST": (size - 1, cls.MASK_NOT_A),
        }

    @staticmethod
    def set_token(bitboard: int, index: int) -> int:
        """Places a token on the board (sets the bit to 1).

        :param bitboard: The current bitboard.
        :param index: The cell index (0-63).
        :return: The new bitboard with the token placed.

        """
        return bitboard | (1 << index)

    @staticmethod
    def get_token(bitboard: int, index: int) -> bool:
        """Checks if there is a token at a given index.

        :param bitboard: The bitboard to check.
        :param index: The cell index (0-63).
        :return: True if a token is present (bit is 1), False otherwise.

        """
        return (bitboard >> index) & 1

    @staticmethod
    def popcount(bitboard: int) -> int:
        """Counts the number of set bits (1s).

        :param bitboard: The bitboard to analyze.
        :return: The number of token on the board.

        """
        return bitboard.bit_count()

    @staticmethod
    def shift_direction(bitboard: int, direction: str) -> int:
        """Shifts the token in a given direction.

        Handles boundary masks to prevent overflows between rows/columns.

        :param bitboard: The bitboard containing the token to shift.
        :param direction: The shift direction ("NORTH", "SOUTH", "EAST",
            "WEST", "NORTH_EAST", "NORTH_WEST", "SOUTH_EAST",
            "SOUTH_WEST").
        :return: The new bitboard with shifted token.
        """
        shift_amount, safe_mask = BitboardOps.DIRECTIONS[direction]

        masked_board = bitboard & safe_mask

        # Décalage vers la gauche (<<) augmente l'index
        # (Vers le SUD ou EST)
        # Décalage vers la droite (>>) diminue l'index
        # (Vers le NORD ou OUEST)
        result = (
            (masked_board << shift_amount)
            if shift_amount > 0
            else (masked_board >> abs(shift_amount))
        )

        # Le & FULL_MASK force le résultat à rester sur 64 bits.
        return result & BitboardOps.FULL_MASK
