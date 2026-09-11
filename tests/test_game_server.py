import socket
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from othello.network.game_server import GameServer


@pytest.fixture
def game_server():
    with patch("othello.network.game_server.DiscoveryService"):
        server = GameServer(port=12345, server_name="TestServer")
        server.player_manager = MagicMock()
        server.game_router = MagicMock()
        yield server
        server.is_running = False


@patch("socket.socket")
@patch("threading.Thread")
def test_start_server(mock_thread, mock_socket_patch, game_server):
    """Test start_server successfully binds and launches threads."""
    mock_socket_obj = MagicMock()
    mock_socket_patch.return_value = mock_socket_obj

    game_server.start_server(is_daemon=True)

    mock_socket_patch.assert_called_once()
    mock_socket_obj.bind.assert_called_with(("", 12345))
    mock_socket_obj.listen.assert_called()

    # Discovery broadcasting should be started
    game_server.discovery.start_broadcasting.assert_called_once()

    # Accept and timeout threads should be started
    assert mock_thread.call_count == 2
    assert game_server.is_running is True


@patch("socket.socket")
def test_start_server_failure(mock_socket_patch, game_server):
    """Test start_server handles bind failure gracefully."""
    mock_socket_obj = MagicMock()
    mock_socket_obj.bind.side_effect = OSError("Address in use")
    mock_socket_patch.return_value = mock_socket_obj

    game_server.start_server()

    assert game_server.is_running is False


def test_stop_server(game_server):
    """Test server shutdown cleans up sockets and services."""
    game_server.is_running = True

    mock_conn1 = MagicMock()
    mock_conn2 = MagicMock()

    game_server.player_manager.players_by_conn = {
        mock_conn1: {},
        mock_conn2: {},
    }

    game_server.stop_server()

    assert game_server.is_running is False
    game_server.discovery.stop_broadcasting.assert_called_once()

    # Ensure players were disconnected
    mock_conn1.sendall.assert_called()
    mock_conn1.close.assert_called()
    assert len(game_server.player_manager.players_by_conn) == 0


def test_process_message_routing(game_server):
    """Test routing mechanism of process_message."""
    mock_conn = MagicMock()

    # Test MOVE
    game_server._process_message(mock_conn, "MOVE e4")
    game_server.game_router.process_move.assert_called_with(
        mock_conn, "e4", game_server.player_manager._get_player.return_value
    )

    # Test NEW
    game_server._process_message(mock_conn, "NEW Player_2")
    game_server.game_router.handle_new_game_request.assert_called_with(
        mock_conn, "Player_2"
    )

    # Test PLAYERS
    game_server.player_manager._get_players_list.return_value = "Player List"
    game_server._process_message(mock_conn, "PLAYERS")
    mock_conn.sendall.assert_called_with(b"PLAYERS_LIST Player List\n")

    # Test SCOREBOARD
    game_server.player_manager._get_scoreboard.return_value = "Score data"
    game_server._process_message(mock_conn, "SCOREBOARD")
    mock_conn.sendall.assert_called_with(b"SCOREBOARD Score data\n")


def test_log(game_server):
    """Test logging to queue and console."""
    # To queue
    log_q = MagicMock()
    game_server.log_queue = log_q
    game_server._log("test message")
    log_q.put.assert_called_with("test message")

    # To console (stdout)
    game_server.log_queue = None
    with patch("builtins.print") as mock_print:
        game_server._log("test message 2")
        mock_print.assert_called_with("test message 2")


def test_start_server_already_running(game_server):
    """Test start_server early return if already running."""
    game_server.is_running = True
    with patch.object(game_server, "_log") as mock_log:
        game_server.start_server()
        mock_log.assert_called_with("Server is already running.")


def test_get_server_status(game_server):
    """Test server status string generation."""
    game_server.player_manager.players_by_conn = {"c1": {}, "c2": {}}
    game_server.game_router.games = {"g1": {}}
    status = game_server.get_server_status()
    assert "Connected Clients: 2" in status
    assert "Active Games: 1" in status
    assert "SERVER_STATUS" not in status


def test_process_message_ping_quit(game_server):
    """Test PING and QUIT commands."""
    mock_conn = MagicMock()
    game_server.player_manager._get_player.return_value = {"id": "P1"}

    # PING
    game_server._process_message(mock_conn, "PING")
    mock_conn.sendall.assert_called_with(b"PONG\n")

    # QUIT
    with patch.object(game_server, "_disconnect_client") as mock_disconnect:
        game_server._process_message(mock_conn, "QUIT")
        mock_disconnect.assert_called_with(mock_conn)


def test_process_message_reconnect(game_server):
    """Test RECONNECT command logic."""
    mock_conn = MagicMock()
    game_server.player_manager._get_player.side_effect = [
        {"id": "P_new", "addr": "addr1"},  # First call in _process_message
        {"id": "P_new", "addr": "addr1"},  # Second call to get addr
        {
            "id": "P_reconnected",
            "status": "ingame",
        },  # Third call after success
    ]

    # Success reconnection
    game_server.player_manager._reconnect_player.return_value = True
    game_server._process_message(mock_conn, "RECONNECT P1")
    game_server.game_router.handle_reconnect.assert_called()

    # Fail reconnection
    game_server.player_manager._get_player.side_effect = None
    game_server.player_manager._get_player.return_value = {
        "id": "P1",
        "addr": "addr1",
    }
    game_server.player_manager._reconnect_player.return_value = False
    game_server._process_message(mock_conn, "RECONNECT P1")
    mock_conn.sendall.assert_called_with(b"ERROR Reconnection failed.\n")


def test_process_message_name(game_server):
    """Test NAME command logic."""
    mock_conn = MagicMock()
    game_server.player_manager._get_player.return_value = {"id": "P1"}

    # Success
    game_server.player_manager._update_player_id.return_value = (
        True,
        "NewName",
    )
    game_server._process_message(mock_conn, "NAME NewName")
    mock_conn.sendall.assert_called_with(b"NAME_OK NewName\n")

    # Failure
    game_server.player_manager._update_player_id.return_value = (
        False,
        "Taken",
    )
    game_server._process_message(mock_conn, "NAME Taken")
    mock_conn.sendall.assert_called_with(b"ERROR Taken\n")


def test_process_message_unknown(game_server):
    """Test unknown command handling."""
    mock_conn = MagicMock()
    game_server.player_manager._get_player.return_value = {"id": "P1"}
    game_server._process_message(mock_conn, "BLAH")
    mock_conn.sendall.assert_called_with(b"ERROR Unknown command: BLAH\n")


@patch("threading.Thread")
def test_handle_client(mock_thread, game_server):
    """Test client handler loop and message processing."""
    mock_conn = MagicMock()
    mock_conn.recv.side_effect = [
        b"PING\n",
        b"",
    ]  # One message then disconnect
    game_server.is_running = True

    with patch.object(game_server, "_process_message") as mock_process:
        game_server._handle_client(mock_conn, ("127.0.0.1", 1234))
        mock_process.assert_called_with(mock_conn, "PING")


def test_check_timeouts_loop(game_server):
    """Test background timeout checker logic."""
    game_server.is_running = True
    mock_conn = MagicMock()
    game_server.player_manager._get_inactive_conns.return_value = [mock_conn]
    game_server.player_manager._check_disconnection_timeouts.return_value = [
        {"id": "P1"}
    ]

    # We need to mock time.sleep to avoid waiting
    with patch(
        "time.sleep", side_effect=[None, InterruptedError]
    ):  # Run once then exit
        try:
            game_server._check_timeouts_loop()
        except InterruptedError:
            pass

    game_server.game_router.handle_disconnect_timeout.assert_called_with(
        {"id": "P1"}
    )
    mock_conn.close.assert_called()


def test_stop_server_socket_exception(game_server):
    """Test server shutdown handles socket close exception."""
    game_server.server_socket = MagicMock()
    game_server.server_socket.close.side_effect = Exception("Close error")
    game_server.is_running = True
    game_server.stop_server()
    assert game_server.is_running is False


@patch("threading.Thread")
def test_accept_loop_exceptions(mock_thread, game_server):
    """Test _accept_loop handles timeout and OSError."""
    game_server.server_socket = MagicMock()
    game_server.server_socket.accept.side_effect = [socket.timeout, OSError]
    game_server.is_running = True

    game_server._accept_loop()
    mock_thread.assert_not_called()


def test_process_message_extended_commands(game_server):
    """Test routing mechanism for extended commands."""
    mock_conn = MagicMock()
    client_info = {"id": "P1"}
    game_server.player_manager._get_player.return_value = client_info

    # SERVER_STATUS
    game_server.get_server_status = MagicMock(return_value="Status\nLine 2")
    game_server._process_message(mock_conn, "SERVER_STATUS")

    # ACCEPT
    game_server._process_message(mock_conn, "ACCEPT")
    game_server.game_router.handle_accept_request.assert_called_with(mock_conn)

    # DECLINE
    game_server._process_message(mock_conn, "DECLINE")
    game_server.game_router.handle_decline_request.assert_called_with(
        mock_conn
    )

    # CANCEL
    game_server._process_message(mock_conn, "CANCEL")
    game_server.game_router.handle_cancel_request.assert_called_with(mock_conn)

    # AWAY
    game_server._process_message(mock_conn, "AWAY")
    game_server.player_manager._set_status.assert_any_call(mock_conn, "away")

    # BACK
    game_server._process_message(mock_conn, "BACK")
    game_server.player_manager._set_status.assert_any_call(mock_conn, "idle")

    # WAITGAME
    game_server.game_router.get_wait_status.return_value = "Waiting status"
    game_server._process_message(mock_conn, "WAITGAME")


def test_disconnect_client_coverage(game_server):
    """Test _disconnect_client handles ingame status and sudden disconnects."""
    mock_conn = MagicMock()
    client_info = {"id": "P1", "status": "ingame"}
    game_server.player_manager._get_player.return_value = client_info
    game_server.player_manager._mark_disconnected.return_value = client_info

    # Test ingame
    game_server._disconnect_client(mock_conn)
    game_server.game_router.handle_sudden_disconnect.assert_called_with(
        client_info
    )
    mock_conn.close.assert_called()

    # Test idle
    client_info["status"] = "idle"
    mock_conn.reset_mock()
    game_server._disconnect_client(mock_conn)
    game_server.player_manager._remove_player.assert_called_with(mock_conn)
    mock_conn.close.assert_called()
