from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from othello.common.command import QuitCommand


@pytest.fixture
def mock_session():
    view = MagicMock()
    patch("builtins._", lambda x: x).start()
    session = MagicMock()
    session.view = view
    session.unsaved_changes = False
    session.game_client = None  # Explicitly set to None
    return session


def test_quit_clean_session(mock_session):
    cmd = QuitCommand()
    result = cmd.execute(mock_session)
    assert result is False
    mock_session.view.get_input.assert_not_called()


def test_quit_session_answer_no(mock_session):
    mock_session.unsaved_changes = True
    mock_session.view.get_input.return_value = "N"
    cmd = QuitCommand()
    result = cmd.execute(mock_session)
    assert result is False
    mock_session.view.get_input.assert_called_with(
        "Save the game before quitting? [y/N] "
    )
    mock_session.save_game.assert_not_called()


def test_quit_session_answer_default(mock_session):
    """Quit with updates and press Enter (Default: No)."""
    mock_session.unsaved_changes = True
    mock_session.view.get_input.return_value = ""  # Entrée vide
    cmd = QuitCommand()
    result = cmd.execute(mock_session)
    assert result is False
    mock_session.save_game.assert_not_called()


def test_quit_session_save_success(mock_session):
    mock_session.unsaved_changes = True
    mock_session.view.get_input.side_effect = ["y", "final.save"]
    mock_session.save_game.return_value = True
    cmd = QuitCommand()
    result = cmd.execute(mock_session)
    assert result is False
    mock_session.save_game.assert_called_with("final.save")


def test_quit_session_save_fail_then_no(mock_session):
    mock_session.unsaved_changes = True
    # Séquence d'inputs :
    # 1. "y" (Je veux sauver)
    # 2. "bad.file" (Nom fichier)
    # -- save_game retourne False ici --
    # 3. "n" (Finalement non, je quitte sans sauver)
    mock_session.view.get_input.side_effect = ["y", "bad.file", "n"]
    mock_session.save_game.return_value = False
    cmd = QuitCommand()
    result = cmd.execute(mock_session)
    assert result is False
    mock_session.save_game.assert_called_once()
    # Vérifie qu'on a posé la question [y/N] deux fois
    assert mock_session.view.get_input.call_count == 3
