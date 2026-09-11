import os

from othello.common.config_manager import ConfigManager
from othello.orchestrator.bitboard_ops import BitboardOps


def test_save_comment():
    filename = "test_comment.txt"
    try:
        state = {
            "current_player": "O",
            "black_board": BitboardOps.set_token(0, 27),
            "white_board": BitboardOps.set_token(0, 28),
        }

        cm = ConfigManager()
        comment = "Ceci est un test de commentaire"

        print(f"Saving to {filename} with comment: '{comment}'...")
        cm.save_game(filename, state, comment)

        # verifie le contenu du fichier
        with open(filename, "r") as f:
            content = f.read()
            print("File content:")
            print(content)

            if f"# {comment}" in content:
                print("SUCCESS: Comment found in file.")
            else:
                print("FAILURE: Comment NOT found in file.")

        # verifie le chargement du fichier
        print("Loading...")
        loaded = cm.load_game(filename)
        if loaded and loaded["current_player"] == "O":
            print("SUCCESS: Loaded correctly")
        else:
            print("FAILURE: Load failed or incorrect data.")

    except Exception as e:
        print(f"FAILURE: {e}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)


if __name__ == "__main__":
    test_save_comment()
