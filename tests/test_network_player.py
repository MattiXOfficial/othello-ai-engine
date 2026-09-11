import queue
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from othello.player.network_player import NetworkPlayer
from othello.user_interface.interface_view import InterfaceView


@pytest.fixture
def mock_view():
    view = MagicMock(spec=InterfaceView)
    view.display_message = MagicMock()
    view.display_error = MagicMock()
    return view


@pytest.fixture
def message_queue():
    return queue.Queue()


@pytest.fixture
def network_player(message_queue):
    player = NetworkPlayer("X", message_queue)
    player.game_session = MagicMock()
    return player


def test_get_move_remote_success(network_player, message_queue, mock_view):
    """Test get_move returns the move when OPPONENT_MOVE is received."""
    message_queue.put("OPPONENT_MOVE E4")

    move = network_player.get_move(None, view=mock_view)

    assert move == "E4"
    mock_view.display_message.assert_any_call(
        "Waiting for remote player (X) to move..."
    )
    mock_view.display_message.assert_any_call("Remote player chose: E4")


def test_get_move_remote_quit(network_player, message_queue, mock_view):
    """Test get_move returns 'quit' when QUIT is received."""
    message_queue.put("QUIT")

    move = network_player.get_move(None, view=mock_view)

    assert move == "quit"
    mock_view.display_error.assert_called_with("Network error/quit: QUIT")


def test_get_move_remote_error(network_player, message_queue, mock_view):
    """Test get_move returns 'quit' when an ERROR message is received."""
    message_queue.put("ERROR something went wrong")

    move = network_player.get_move(None, view=mock_view)

    assert move == "quit"
    mock_view.display_error.assert_called_with(
        "Network error/quit: ERROR something went wrong"
    )


def test_get_move_other_message_handled(
    network_player, message_queue, mock_view
):
    """Test that other messages are passed to handle_network_message."""
    message_queue.put("CHAT Hello")

    with patch.object(network_player.message_queue, "get") as mock_get:
        mock_get.side_effect = ["CHAT Hello", "OPPONENT_MOVE F5"]
        move = network_player.get_move(None, view=mock_view)

    assert move == "F5"
    network_player.game_session.handle_network_message.assert_called_with(
        "CHAT Hello"
    )


def test_get_move_local_input_invalid_color(
    network_player, message_queue, mock_view
):
    """Test that local input for the remote player's color is rejected."""
    # We use patch for sys.stdin.isatty and select.select to simulate CLI input
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch(
            "select.select", side_effect=[([True], [], []), ([True], [], [])]
        ),
        patch("sys.stdin.readline", side_effect=["X E4", "quit"]),
    ):  # First try to play as X (illegal), then another input
        # We also need a way to break the loop if the second input is
        # also rejected or ignored.
        # Let's make the second input be just "quit" or something that returns.
        # In NetworkPlayer.get_move, any local_input that is NOT rejected
        # by the color check is returned.

        move = network_player.get_move(None, view=mock_view)

    assert move == "quit"
    mock_view.display_error.assert_any_call(
        "Cannot play for remote player (X)!"
    )


def test_get_move_local_input_not_turn(
    network_player, message_queue, mock_view
):
    """Test that local input starting with an Othello color.

    When it's not our turn is rejected.
    """
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch(
            "select.select", side_effect=[([True], [], []), ([True], [], [])]
        ),
        patch("sys.stdin.readline", side_effect=["O E4", "help"]),
    ):
        move = network_player.get_move(None, view=mock_view)

    assert move == "help"
    mock_view.display_error.assert_called_with("It is not your turn.")


def test_get_move_gui_input(network_player, message_queue, mock_view):
    """Test that GUI input via input_queue is returned."""
    # We need to bypass the spec to add input_queue
    mock_view.input_queue = queue.Queue()
    mock_view.input_queue.put("hint")

    move = network_player.get_move(None, view=mock_view)

    assert move == "hint"
