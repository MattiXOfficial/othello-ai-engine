import time
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from othello.network.player_manager import PlayerManager


@pytest.fixture
def mock_server():
    server = MagicMock()
    server.message_queue = MagicMock()
    server.game_router = MagicMock()
    server.game_router.remove_player_from_games = MagicMock()
    return server


@pytest.fixture
def player_manager(mock_server):
    return PlayerManager(mock_server)


def test_add_player(player_manager):
    """Test adding a new player correctly assigns an ID.

    And stores the connection.
    """
    mock_conn = MagicMock()
    mock_addr = ("127.0.0.1", 5000)

    player_manager._add_player(mock_conn, mock_addr)

    assert mock_conn in player_manager.players_by_conn
    player_data = player_manager.players_by_conn[mock_conn]
    assert player_data["id"] == "Player_1"
    assert player_data["status"] == "idle"
    assert player_data["opponent"] is None


def test_remove_player(player_manager, mock_server):
    """Test removing a connected player."""
    mock_conn = MagicMock()
    mock_addr = ("127.0.0.1", 5000)

    player_manager._add_player(mock_conn, mock_addr)

    player_manager._remove_player(mock_conn)

    assert mock_conn not in player_manager.players_by_conn


def test_remove_nonexistent_player(player_manager):
    """Test removing a player that doesn't exist doesn't crash."""
    mock_conn = MagicMock()
    player_manager._remove_player(mock_conn)  # Should just return silently


def test_get_players_list(player_manager):
    """Test getting formatted players list."""
    mock_conn1 = MagicMock()
    mock_conn2 = MagicMock()

    player_manager._add_player(mock_conn1, ("127.0.0.1", 5001))
    player_manager._add_player(mock_conn2, ("127.0.0.1", 5002))

    # Set one player in game
    player_manager.players_by_conn[mock_conn2]["status"] = "ingame"

    players_list = player_manager._get_players_list()

    assert "Connected Players:" in players_list
    assert "- Player_1 [idle]" in players_list
    assert "- Player_2 [ingame]" in players_list


def test_get_scoreboard(player_manager):
    """Test getting the formatted scoreboard."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))
    player_id = player_manager.players_by_conn[mock_conn]["id"]

    # Manually tweak scoreboard
    player_manager.scoreboard[player_id]["wins"] = 2
    player_manager.scoreboard[player_id]["losses"] = 1
    player_manager.scoreboard[player_id]["played"] = 3

    scoreboard = player_manager._get_scoreboard()
    assert "Scoreboard" in scoreboard
    assert f"{player_id}: 2 Wins, 1 Losses (3 Played)" in scoreboard


def test_mark_disconnected(player_manager):
    """Test marking a player as disconnected."""
    mock_conn = MagicMock()
    mock_addr = ("127.0.0.1", 5000)
    player_manager._add_player(mock_conn, mock_addr)
    player_id = player_manager.players_by_conn[mock_conn]["id"]

    info = player_manager._mark_disconnected(mock_conn)

    assert mock_conn not in player_manager.players_by_conn
    assert player_id in player_manager.disconnected_players
    assert info["id"] == player_id


def test_reconnect_player_from_disconnected(player_manager):
    """Test reconnecting a previously disconnected player."""
    mock_conn1 = MagicMock()
    mock_addr1 = ("127.0.0.1", 5000)
    player_manager._add_player(mock_conn1, mock_addr1)
    player_id = player_manager.players_by_conn[mock_conn1]["id"]
    player_manager._mark_disconnected(mock_conn1)

    mock_conn2 = MagicMock()
    mock_addr2 = ("127.0.0.1", 5001)
    success = player_manager._reconnect_player(
        mock_conn2, mock_addr2, player_id
    )

    assert success is True
    assert mock_conn2 in player_manager.players_by_conn
    assert player_manager.players_by_conn[mock_conn2]["id"] == player_id
    assert player_id not in player_manager.disconnected_players


def test_reconnect_player_active_busy(player_manager):
    """Test re-binding an already active player (TCP race window)."""
    mock_conn1 = MagicMock()
    mock_addr1 = ("127.0.0.1", 5000)
    player_manager._add_player(mock_conn1, mock_addr1)
    player_id = player_manager.players_by_conn[mock_conn1]["id"]

    mock_conn2 = MagicMock()
    mock_addr2 = ("127.0.0.1", 5001)
    # This should kick the old connection and bind the new one
    success = player_manager._reconnect_player(
        mock_conn2, mock_addr2, player_id
    )

    assert success is True
    assert mock_conn1 not in player_manager.players_by_conn
    assert mock_conn2 in player_manager.players_by_conn
    mock_conn1.close.assert_called_once()


def test_check_disconnection_timeouts(player_manager):
    """Test that inactive disconnected players are removed after timeout."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))
    player_id = player_manager.players_by_conn[mock_conn]["id"]
    player_manager._mark_disconnected(mock_conn)

    # Mock time to be in the future
    with patch("time.time", return_value=time.time() + 100):
        timed_out = player_manager._check_disconnection_timeouts(
            timeout_seconds=60
        )

    assert len(timed_out) == 1
    assert timed_out[0]["id"] == player_id
    assert player_id not in player_manager.disconnected_players


def test_remove_ghost_connection(player_manager, mock_server):
    """Test removing a ghost connection.

    (duplicate from same IP while in game).
    """
    mock_conn = MagicMock()
    addr = ("1.2.3.4", 5000)
    player_manager._add_player(mock_conn, addr)
    player_manager._set_status(mock_conn, "ingame")

    # Try to remove ghost from same IP
    ghost_info = player_manager._remove_ghost_connection(("1.2.3.4", 5001))

    assert ghost_info is not None
    assert ghost_info["addr"] == addr
    assert mock_conn not in player_manager.players_by_conn


def test_update_player_id_success(player_manager):
    """Test successfully changing a player's pseudo."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))
    old_id = player_manager.players_by_conn[mock_conn]["id"]

    success, result = player_manager._update_player_id(mock_conn, "Alice")

    assert success is True
    assert result == "Alice"
    assert player_manager.players_by_conn[mock_conn]["id"] == "Alice"
    assert "Alice" in player_manager.scoreboard
    assert old_id not in player_manager.scoreboard


def test_update_player_id_taken(player_manager):
    """Test that changing to a taken name fails."""
    mock_conn1 = MagicMock()
    player_manager._add_player(mock_conn1, ("127.0.0.1", 5000))

    mock_conn2 = MagicMock()
    player_manager._add_player(mock_conn2, ("127.0.0.1", 5001))
    player2_id = player_manager.players_by_conn[mock_conn2]["id"]

    # Try to change Player 1's name to Player 2's name
    success, error = player_manager._update_player_id(mock_conn1, player2_id)

    assert success is False
    assert "already taken" in error


def test_get_inactive_conns(player_manager):
    """Test identifying connections that haven't sent activity recently."""
    mock_conn1 = MagicMock()

    # In our mock setup, both might be inactive if we don't fix the start time.
    now = 1000.0
    with patch("time.time", return_value=now):
        player_manager._add_player(mock_conn1, ("127.0.0.1", 5000))
        mock_conn2 = MagicMock()
        player_manager._add_player(mock_conn2, ("127.0.0.1", 5001))

    with patch("time.time", return_value=now + 5):
        player_manager._update_activity(mock_conn1)

    with patch("time.time", return_value=now + 15):
        inactive = player_manager._get_inactive_conns(timeout_seconds=10)

    assert mock_conn2 in inactive
    assert mock_conn1 not in inactive


def test_set_status_new_types(player_manager):
    """Test setting away and waitgame statuses."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))

    player_manager._set_status(mock_conn, "away")
    assert player_manager.players_by_conn[mock_conn]["status"] == "away"

    player_manager._set_status(mock_conn, "waitgame")
    assert player_manager.players_by_conn[mock_conn]["status"] == "waitgame"


def test_get_players_list_with_id(player_manager):
    """Test getting detailed info for a single player."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))
    player_id = player_manager.players_by_conn[mock_conn]["id"]

    # Set some stats
    player_manager.scoreboard[player_id] = {
        "wins": 5,
        "losses": 2,
        "played": 7,
    }

    details = player_manager._get_players_list(target_id=player_id)
    assert f"--- Player Info: {player_id} ---" in details
    assert "Score: 5 Wins, 2 Losses (7 Played)" in details


def test_get_players_list_wait_details(player_manager):
    """Test that the players list shows invitation details."""
    mock_conn1 = MagicMock()
    mock_conn2 = MagicMock()
    player_manager._add_player(mock_conn1, ("127.0.0.1", 5001))
    player_manager._add_player(mock_conn2, ("127.0.0.1", 5002))
    id1 = player_manager.players_by_conn[mock_conn1]["id"]
    id2 = player_manager.players_by_conn[mock_conn2]["id"]

    player_manager._set_status(mock_conn1, "waitgame")
    player_manager._set_status(mock_conn2, "waitgame")

    # Mock invitation context
    invitations = {mock_conn2: {"requester": mock_conn1}}

    # We call it with mocked invitations from router
    players_list = player_manager._get_players_list(invitations=invitations)

    assert f"- {id1} [waitgame] (waiting for {id2})" in players_list
    assert f"- {id2} [waitgame] (challenged by {id1})" in players_list


def test_get_player(player_manager):
    """Test getting a player's info by their connection."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))

    info = player_manager._get_player(mock_conn)
    assert info is not None
    assert info["id"] == "Player_1"

    # Test non-existent connection
    assert player_manager._get_player(MagicMock()) is None


def test_get_player_by_id(player_manager):
    """Test finding player connection by ID."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))
    player_id = player_manager.players_by_conn[mock_conn]["id"]

    found_conn, info = player_manager._get_player_by_id(player_id)
    assert found_conn == mock_conn
    assert info["id"] == player_id

    # Test non-existent ID
    found_conn, info = player_manager._get_player_by_id("Unknown_ID")
    assert found_conn is None
    assert info is None


def test_record_game_result(player_manager):
    """Test recording game results (win/loss)."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))
    player_id = player_manager.players_by_conn[mock_conn]["id"]

    # Record win
    player_manager._update_score(player_id, won=True)
    assert player_manager.scoreboard[player_id]["played"] == 1
    assert player_manager.scoreboard[player_id]["wins"] == 1
    assert player_manager.scoreboard[player_id]["losses"] == 0

    # Record loss
    player_manager._update_score(player_id, won=False)
    assert player_manager.scoreboard[player_id]["played"] == 2
    assert player_manager.scoreboard[player_id]["wins"] == 1
    assert player_manager.scoreboard[player_id]["losses"] == 1


def test_update_player_id_edge_cases(player_manager):
    """Test the failure modes and edge cases of name changes."""
    mock_conn = MagicMock()
    player_manager._add_player(mock_conn, ("127.0.0.1", 5000))
    old_id = player_manager.players_by_conn[mock_conn]["id"]

    # Empty name
    success, err = player_manager._update_player_id(mock_conn, "")
    assert success is False
    assert "cannot be empty" in err

    # Unknown connection
    unknown_conn = MagicMock()
    success, err = player_manager._update_player_id(unknown_conn, "Bob")
    assert success is False
    assert "Player not found" in err

    # Same name (no-op)
    success, res = player_manager._update_player_id(mock_conn, old_id)
    assert success is True
    assert res == old_id

    # Disconnected player name taken
    mock_conn2 = MagicMock()
    player_manager._add_player(mock_conn2, ("127.0.0.1", 5001))
    player2_id = player_manager.players_by_conn[mock_conn2]["id"]
    player_manager._mark_disconnected(mock_conn2)

    success, err = player_manager._update_player_id(mock_conn, player2_id)
    assert success is False
    assert "reserved by a disconnected" in err
