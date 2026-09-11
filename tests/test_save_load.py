import os

from othello.common.config_manager import ConfigManager
from othello.orchestrator.bitboard_ops import BitboardOps


def test_save_load():
    filename = "test_save.txt"
    try:
        # simule une partie avec 3 pions noirs et 3 pions blancs
        black_bb = 0
        black_bb = BitboardOps.set_token(black_bb, 27)  # d4
        black_bb = BitboardOps.set_token(black_bb, 36)  # e5
        black_bb = BitboardOps.set_token(black_bb, 16)  # a3

        white_bb = 0
        white_bb = BitboardOps.set_token(white_bb, 28)  # e4
        white_bb = BitboardOps.set_token(white_bb, 35)  # d5
        white_bb = BitboardOps.set_token(white_bb, 63)  # h8

        state = {
            "current_player": "X",
            "black_board": black_bb,
            "white_board": white_bb,
        }

        cm = ConfigManager()

        # sauvegarde
        print(f"Saving to {filename}...")
        cm.save_game(filename, state)

        # chargement
        print(f"Loading from {filename}...")
        loaded_state = cm.load_game(filename)

        # verification
        print("Verifying...")
        assert loaded_state["current_player"] == "X"
        assert loaded_state["black_board"] == black_bb
        assert loaded_state["white_board"] == white_bb

        print("SUCCESS: Loaded state matches saved state.")

        # verification du contenu du fichier
        with open(filename, "r") as f:
            content = f.read()
            print("File content:")
            print(content)

    except Exception as e:
        print(f"FAILURE: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)


if __name__ == "__main__":
    test_save_load()
