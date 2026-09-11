import json
import time
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from othello.network.discovery_service import DiscoveryService


@pytest.fixture
def discovery_service():
    """Provides a fresh DiscoveryService instance for each test."""
    ds = DiscoveryService(server_name="TestServer", tcp_port=12345)
    # for the lock to prevent actual deadlock
    yield ds


def test_initialization(discovery_service):
    """Test correctly initialized DiscoveryService."""
    assert discovery_service.server_name == "TestServer"
    assert discovery_service.tcp_port == 12345
    assert discovery_service.is_broadcasting is False
    assert discovery_service.is_listening is False
    assert discovery_service.discovered_servers == {}


@patch("socket.socket")
def test_start_broadcasting(mock_socket_cls, discovery_service):
    """Test start_broadcasting thread launches correctly."""
    with patch("threading.Thread") as mock_thread_cls:
        mock_thread_instance = MagicMock()
        mock_thread_cls.return_value = mock_thread_instance

        discovery_service.start_broadcasting()

        assert discovery_service.is_broadcasting is True
        mock_thread_cls.assert_called_once()
        mock_thread_instance.start.assert_called_once()

        # Should not start twice
        discovery_service.start_broadcasting()
        mock_thread_instance.start.assert_called_once()


@patch("othello.network.discovery_service.DiscoveryService.broadcast_shutdown")
def test_stop_broadcasting(mock_broadcast_shutdown, discovery_service):
    """Test stopping the broadcast."""
    discovery_service.is_broadcasting = True
    discovery_service.stop_broadcasting()

    assert discovery_service.is_broadcasting is False
    mock_broadcast_shutdown.assert_called_once()


def test_update_local_list(discovery_service):
    """Test adding servers to the local list updates timestamps."""
    with patch("time.time", return_value=100.0):
        discovery_service.update_local_list("ServerA", "192.168.1.10", 5000)

    expected_key = "ServerA@192.168.1.10:5000"
    assert expected_key in discovery_service.discovered_servers
    assert discovery_service.discovered_servers[expected_key] == 100.0


def test_remove_from_local_list(discovery_service):
    """Test removing servers explicitly."""
    discovery_service.discovered_servers["ServerA@192.168.1.10:5000"] = 100.0
    discovery_service.remove_from_local_list("ServerA", "192.168.1.10", 5000)
    assert (
        "ServerA@192.168.1.10:5000" not in discovery_service.discovered_servers
    )

    # Should not error if missing
    discovery_service.remove_from_local_list("MissingServer", "10.0.0.1", 1234)


def test_clear_inactive_servers_logic(discovery_service):
    """Test the logic of clearing inactive servers.

    Without running the infinite loop.
    """
    discovery_service.discovered_servers["ActiveServer@1.1.1.1:1234"] = 1000.0
    discovery_service.discovered_servers["StaleServer@2.2.2.2:5678"] = 500.0

    # simulate time passing so that we can test without runnign
    # the locking loop
    with patch("time.time", return_value=1020.0):
        # rest is runned manually
        now = time.time()
        to_remove = []
        for key, last_seen in discovery_service.discovered_servers.items():
            if now - last_seen > discovery_service.CLEAR_TIMEOUT:
                to_remove.append(key)
        for key in to_remove:
            del discovery_service.discovered_servers[key]

    assert "ActiveServer@1.1.1.1:1234" in discovery_service.discovered_servers
    assert (
        "StaleServer@2.2.2.2:5678" not in discovery_service.discovered_servers
    )


def test_get_server_list(discovery_service):
    """Test retrieving server list."""
    discovery_service.discovered_servers["S1@1.1.1.1:1"] = 100.0
    discovery_service.discovered_servers["S2@2.2.2.2:2"] = 200.0
    s_list = discovery_service.get_server_list()
    assert len(s_list) == 2
    assert "S1@1.1.1.1:1" in s_list
    assert "S2@2.2.2.2:2" in s_list


@patch("socket.socket")
def test_broadcast_presence(mock_socket_cls, discovery_service):
    """Test broadcasting loop (single pass)."""
    mock_socket = MagicMock()
    mock_socket_cls.return_value = mock_socket
    discovery_service.is_broadcasting = True

    # Use side_effect to break the loop
    def stop_loop(*args, **kwargs):
        discovery_service.is_broadcasting = False

    mock_socket.sendto.side_effect = stop_loop

    with patch("time.sleep"):  # immediately return
        discovery_service.broadcast_presence()

    mock_socket.sendto.assert_called()
    call_args = mock_socket.sendto.call_args[0]
    sent_msg = json.loads(call_args[0].decode("utf-8"))
    assert sent_msg["type"] == "PRESENCE"
    assert sent_msg["name"] == "TestServer"


@patch("socket.socket")
def test_broadcast_shutdown(mock_socket_cls, discovery_service):
    """Test shutdown broadcast message."""
    mock_socket = MagicMock()
    mock_socket_cls.return_value = mock_socket

    discovery_service.broadcast_shutdown()

    mock_socket.sendto.assert_called()
    call_args = mock_socket.sendto.call_args[0]
    sent_msg = json.loads(call_args[0].decode("utf-8"))
    assert sent_msg["type"] == "SHUTDOWN"
    mock_socket.close.assert_called_once()


@patch("socket.socket")
def test_listen_for_servers(mock_socket_cls, discovery_service):
    """Test listener handling presence and shutdown messages."""
    mock_socket = MagicMock()
    mock_socket_cls.return_value = mock_socket
    discovery_service.is_listening = True

    presence_msg = json.dumps(
        {"type": "PRESENCE", "name": "FoundS", "port": 5555}
    ).encode("utf-8")
    shutdown_msg = json.dumps(
        {"type": "SHUTDOWN", "name": "FoundS", "port": 5555}
    ).encode(
        "utf-8"
    )  # Feed it one presence, then one shutdown, then stop

    def _recv_side_effect(*args, **kwargs):
        if mock_socket.recvfrom.call_count == 1:
            return (presence_msg, ("10.0.0.2", 12346))
        if mock_socket.recvfrom.call_count == 2:
            return (shutdown_msg, ("10.0.0.2", 12346))
        discovery_service.is_listening = False
        return (b"", ("", 0))

    mock_socket.recvfrom.side_effect = _recv_side_effect
    mock_socket.recvfrom.call_count = 0

    discovery_service.listen_for_servers()

    # FoundS should have been added then removed
    assert "FoundS@10.0.0.2:5555" not in discovery_service.discovered_servers


def test_clear_inactive_servers_loop(discovery_service):
    """Test clear inactive loop (one pass)."""
    discovery_service.is_listening = True
    discovery_service.discovered_servers["S1@1.1.1.1:1"] = 1.0  # Very stale

    with patch(
        "time.sleep", side_effect=[None, OSError]
    ):  # run once then crash
        try:
            discovery_service.clear_inactive_servers()
        except OSError:
            pass

    assert "S1@1.1.1.1:1" not in discovery_service.discovered_servers


@patch("threading.Thread")
def test_start_listening(mock_thread, discovery_service):
    """Test start_listening starts both threads."""
    discovery_service.start_listening()
    assert discovery_service.is_listening is True
    assert (
        mock_thread.call_count == 2
    )  # listen_for_servers and clear_inactive_servers


def test_broadcast_loop_exception(discovery_service):
    """Test broadcast_presence catching generic Exception."""
    discovery_service.is_broadcasting = True

    with patch("socket.socket") as mock_socket_cls:
        mock_socket = MagicMock()
        mock_socket_cls.return_value = mock_socket

        def mock_sendto(*args, **kwargs):
            discovery_service.is_broadcasting = False
            raise Exception("Broadcast Error")

        mock_socket.sendto.side_effect = mock_sendto
        with patch("time.sleep"):  # to prevent waiting
            discovery_service.broadcast_presence()

        mock_socket.sendto.assert_called_once()


def test_broadcast_shutdown_oserror(discovery_service):
    """Test broadcast_shutdown handling OSError."""
    with patch("socket.socket") as mock_socket_cls:
        mock_socket = MagicMock()
        mock_socket_cls.return_value = mock_socket
        mock_socket.sendto.side_effect = OSError("Network unreachable")

        discovery_service.broadcast_shutdown()
        mock_socket.sendto.assert_called_once()
        mock_socket.close.assert_called_once()


@patch("socket.socket")
def test_listen_for_servers_exceptions(mock_socket_cls, discovery_service):
    """Test listen_for_servers handling generic Exceptions."""
    mock_socket = MagicMock()
    mock_socket_cls.return_value = mock_socket
    discovery_service.is_listening = True

    mock_socket.recvfrom.side_effect = Exception("Fatal Error")

    with patch("builtins.print") as mock_print:
        discovery_service.listen_for_servers()
        assert mock_socket.recvfrom.call_count == 1
        mock_socket.close.assert_called_once()
        mock_print.assert_any_call("Discovery listener error: Fatal Error")


@patch("socket.socket")
def test_listen_for_servers_bind_exception(mock_socket_cls, discovery_service):
    """Test listen_for_servers catching bind exception."""
    mock_socket = MagicMock()
    mock_socket_cls.return_value = mock_socket
    mock_socket.bind.side_effect = Exception("Bind Error")

    with patch("builtins.print") as mock_print:
        discovery_service.listen_for_servers()
        mock_print.assert_any_call("Error binding UDP listener: Bind Error")


def test_update_local_list_empty_parameters(discovery_service):
    """Test update_local_list handles missing name or port."""
    discovery_service.update_local_list("", "127.0.0.1", 1234)
    assert len(discovery_service.discovered_servers) == 0

    discovery_service.update_local_list("Name", "127.0.0.1", 0)
    assert len(discovery_service.discovered_servers) == 0
