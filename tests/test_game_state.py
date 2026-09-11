from othello.game_engine.game_state import GameState


def test_init():
    gs = GameState()
    assert gs.white_board == 0
    assert gs.black_board == 0


def test_get_board():
    gs = GameState()
    gs.white_board = 1
    gs.black_board = 2
    assert gs.get_board() == (1, 2)
