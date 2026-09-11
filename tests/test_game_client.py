from unittest.mock import MagicMock
from unittest.mock import patch


from othello.network.game_client import GameClient
from othello.player.network_player import NetworkPlayer
from othello.player.real_player import RealPlayer
import pytest
import socket


@pytest.fixture
def mock_socket():
    return MagicMock()


@pytest.fixture
def game_client(mock_socket):
    with patch("socket.socket", return_value=mock_socket):
        client = GameClient("127.0.0.1", 12345)
        yield client
        client.is_connected = False


def test_initialization(game_client):
    assert game_client.ip == "127.0.0.1"
    assert game_client.port == 12345
    assert not game_client.is_connected


def test_connect_success(game_client, mock_socket):
    """Test successful connection."""
    with patch("threading.Thread") as mock_thread_cls:
        assert game_client.join() is True
        mock_socket.connect.assert_called_with(("127.0.0.1", 12345))
        assert game_client.is_connected is True
        mock_thread_cls.assert_called_once()


def test_connect_failure(game_client, mock_socket):
    """Test connection failure."""
    mock_socket.connect.side_effect = ConnectionRefusedError()
    assert game_client.join() is False
    assert game_client.is_connected is False


def test_disconnect(game_client, mock_socket):
    """Test safe disconnection."""
    game_client.is_connected = True
    game_client.socket = mock_socket
    game_client.quit()

    assert game_client.is_connected is False
    mock_socket.sendall.assert_called_with(b"QUIT\n")
    mock_socket.close.assert_called_once()


def test_send_message_success(game_client, mock_socket):
    """Test sending a message."""
    game_client.is_connected = True
    game_client.socket = mock_socket
    game_client.send_message("HELLO")

    mock_socket.sendall.assert_called_with(b"HELLO\n")


def test_receive_commands_via_queue(game_client):
    """Test queue interaction."""
    game_client.message_queue.put("OPPONENT_MOVE O e4")
    assert not game_client.message_queue.empty()
    assert game_client.message_queue.get() == "OPPONENT_MOVE O e4"
    assert game_client.message_queue.empty()


def test_get_server_status(game_client):
    """Test server status string."""
    assert game_client.get_server_status() == "Client: Not connected"
    game_client.is_connected = True
    game_client.ip = "1.2.3.4"
    game_client.port = 9999
    assert "Connected to 1.2.3.4:9999" in game_client.get_server_status()


def test_ping_not_connected(game_client):
    """Test ping when not connected."""
    with patch("builtins.print") as mock_print:
        game_client.ping()
        mock_print.assert_called_with("Cannot ping: Not connected.")


def test_ping_connected(game_client, mock_socket):
    """Test ping when connected."""
    game_client.is_connected = True
    game_client.socket = mock_socket
    game_client.ping()
    mock_socket.sendall.assert_called_with(b"PING\n")


def test_join_already_connected(game_client, mock_socket):
    """Test join when already connected (should quit first)."""
    game_client.is_connected = True
    game_client.socket = mock_socket
    with (
        patch.object(game_client, "quit") as mock_quit,
        patch("threading.Thread"),
    ):
        game_client.join()
        mock_quit.assert_called_once()


def test_join_with_id_reconnect(game_client, mock_socket):
    """Test joining with an existing client_id sends RECONNECT."""
    game_client.client_id = "Alice"
    with patch("threading.Thread"):
        game_client.join()
    mock_socket.sendall.assert_any_call(b"RECONNECT Alice\n")


def test_listen_loop_dispatch(game_client, mock_socket):
    """Test message dispatch in listen loop."""
    game_client.is_connected = True
    game_client.socket = mock_socket
    game_client.game_session = MagicMock()

    # Sequence of messages
    mock_socket.recv.side_effect = [
        b"YOUR_ID Player_1\n",
        b"NAME_OK Alice\n",
        b"YOUR_ID Player_2\n",  # Should be IGNORED because Alice is custom.
        # Actually logic says: if not new_id.startswith("Player_"), accept.
        # If new_id starts with Player_, only accept if current is None or
        # starts with Player_.
        b"SYNC_BOARD X 1 2\n",
        b"",  # Disconnect
    ]

    game_client._listen_loop()

    assert (
        game_client.client_id == "Player_2"
    )  # Client now properly accepts connection-assigned IDs to fix desyncs.
    # Logic: if new_id starts with Player_, only accept if current is generic.

    game_client.game_session.sync_board.assert_called_with("X 1 2")
    # Wait a bit if needed or just check if is_connected is False
    assert not game_client.is_connected
    # Ensure __DISCONNECTED__ is in the queue
    queue_list = list(game_client.message_queue.queue)
    assert "__DISCONNECTED__" in queue_list


def test_handle_disconnect(game_client):
    """Test disconnect signal in queue."""
    game_client.is_connected = True
    game_client._handle_disconnect()
    assert game_client.is_connected is False
    assert game_client.message_queue.get() == "__DISCONNECTED__"


def test_setup_network_game(game_client):
    """Test configuring local and network players."""
    game_client.game_session = MagicMock()
    game_client.game_session.players = {}

    game_client._setup_network_game("X")

    assert isinstance(game_client.game_session.players["X"], RealPlayer)
    assert isinstance(game_client.game_session.players["O"], NetworkPlayer)
    game_client.game_session.reset_game.assert_called()


def test_send_message_not_connected(game_client):
    """Test send_message logs and returns if not connected."""
    game_client.is_connected = False
    game_client.send_message("TEST")
    # socket methods shouldn't be called
    if game_client.socket:
        game_client.socket.sendall.assert_not_called()


def test_send_message_exception(game_client, mock_socket):
    """Test send_message exception handling calls quit()."""
    game_client.is_connected = True
    game_client.socket = mock_socket
    mock_socket.sendall.side_effect = Exception("Test Error")

    with patch.object(game_client, "quit") as mock_quit:
        game_client.send_message("TEST")
        mock_quit.assert_called_once()


def test_connect_to_server_exceptions(game_client, mock_socket):
    """Test connect_to_server catches timeout and OSError."""

    # Test socket.timeout
    mock_socket.connect.side_effect = socket.timeout("timeout")
    assert game_client.join() is False

    # Test generic OSError
    mock_socket.connect.side_effect = OSError("network error")
    assert game_client.join() is False


def test_listen_loop_exceptions_and_closure(game_client, mock_socket):
    """Test _listen_to_server exception handling and socket closure."""

    game_client.is_connected = True
    game_client.socket = mock_socket

    # Sequence of exceptions to hit all branches
    # 1. socket.timeout -> continue loop
    # 2. ConnectionResetError -> handle disconnect and break
    mock_socket.recv.side_effect = [
        socket.timeout("timeout"),
        ConnectionResetError("reset"),
    ]

    with patch.object(game_client, "_handle_disconnect") as mock_disconnect:
        game_client._listen_loop()
        assert mock_disconnect.call_count == 1
        assert game_client.socket is None  # it closes socket in finally block

    # Re-setup for OSError
    game_client.is_connected = True
    game_client.socket = mock_socket
    mock_socket.recv.side_effect = [OSError("os error")]

    with patch.object(game_client, "_handle_disconnect") as mock_disconnect:
        game_client._listen_loop()
        assert mock_disconnect.call_count == 1

    # Test the close() raising OSError branch
    game_client.is_connected = True
    game_client.socket = mock_socket
    mock_socket.recv.side_effect = [b""]
    mock_socket.close.side_effect = OSError("close error")
    game_client._listen_loop()
    assert game_client.socket is None


def test_handle_disconnect_branches(game_client):
    """Test early returns in _handle_disconnect."""
    # Not connected
    game_client.is_connected = False
    game_client._handle_disconnect()
    assert game_client.message_queue.empty()

    # Connected but no game_session
    game_client.is_connected = True
    game_client.game_session = None
    game_client._handle_disconnect()

    assert not game_client.message_queue.empty()
    assert game_client.message_queue.get() == "__DISCONNECTED__"
    # No exception or error because game_session is None


def test_listen_loop_custom_id(game_client, mock_socket):
    """Test receiving a custom ID from the server."""
    game_client.is_connected = True
    game_client.socket = mock_socket
    game_client.game_session = MagicMock()

    # Send an ID that does NOT start with Player_
    mock_socket.recv.side_effect = [b"YOUR_ID CustomName\n", b""]

    game_client._listen_loop()

    assert game_client.client_id == "CustomName"
    assert game_client.game_session.last_client_id == "CustomName"


def test_quit_recv_exception(game_client, mock_socket):
    """Test quit() handles recv exceptions."""
    game_client.is_connected = True
    game_client.socket = mock_socket

    # Test socket.timeout
    mock_socket.recv.side_effect = socket.timeout("timeout")
    game_client.quit()
    mock_socket.close.assert_called()

    # Reset
    game_client.is_connected = True
    game_client.socket = mock_socket
    mock_socket.reset_mock()

    # Test OSError in recv
    mock_socket.recv.side_effect = OSError("os error")
    game_client.quit()
    mock_socket.close.assert_called()


def test_quit_sendall_exception(game_client, mock_socket):
    """Test quit() handles sendall returning OSError."""
    game_client.is_connected = True
    game_client.socket = mock_socket

    mock_socket.sendall.side_effect = OSError("send error")
    game_client.quit()
    mock_socket.close.assert_called()


def test_quit_close_exception(game_client, mock_socket):
    """Test quit() when close raises OSError."""
    game_client.is_connected = True
    game_client.socket = mock_socket

    mock_socket.close.side_effect = OSError("close error")
    game_client.quit()
    assert game_client.socket is None
