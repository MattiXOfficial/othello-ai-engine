import time
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from othello.network.game_router import GameRouter


@pytest.fixture
def mock_server():
    server = MagicMock()
    server.player_manager = MagicMock()
    server.player_manager.players_by_conn = {
        "conn1": {"id": "Player_1", "status": "idle", "opponent": None},
        "conn2": {"id": "Player_2", "status": "idle", "opponent": None},
        "conn3": {"id": "Player_3", "status": "ingame", "opponent": "conn4"},
    }

    def _get_player_by_id(pid):
        for conn, info in server.player_manager.players_by_conn.items():
            if info.get("id") == pid:
                return conn, info
        return None, None

    server.player_manager._get_player_by_id = MagicMock(
        side_effect=_get_player_by_id
    )
    server.player_manager._get_player = MagicMock(
        side_effect=lambda conn: server.player_manager.players_by_conn.get(
            conn
        )
    )
    return server


@pytest.fixture
def game_router(mock_server):
    return GameRouter(mock_server)


def test_handle_new_game_request_success(game_router, mock_server):
    """Test successful invitation between two idle players."""
    game_router.handle_new_game_request("conn1", "Player_2")

    # Check invitation was tracked
    assert "conn2" in game_router.pending_invitations
    assert game_router.pending_invitations["conn2"]["requester"] == "conn1"

    # Check status changes
    assert (
        mock_server.player_manager.players_by_conn["conn1"]["status"]
        == "waitgame"
    )
    assert (
        mock_server.player_manager.players_by_conn["conn2"]["status"]
        == "waitgame"
    )

    # Check messages sent
    mock_server._send.assert_any_call(
        "conn1", "INVITATION_SENT PLAYER=Player_2 TIMEOUT=300s"
    )
    mock_server._send.assert_any_call(
        "conn2", "INVITATION_RECEIVED FROM=Player_1 EXPIRES=300s"
    )


def test_handle_accept_request_success(game_router, mock_server):
    """Test accepting an invitation starts the game."""
    # Setup pending invitation
    game_router.pending_invitations["conn2"] = {
        "requester": "conn1",
        "expires": 9999999999,
    }
    mock_server.player_manager.players_by_conn["conn1"]["status"] = "waitgame"
    mock_server.player_manager.players_by_conn["conn2"]["status"] = "waitgame"

    game_router.handle_accept_request("conn2")

    # Check game started
    assert len(game_router.games) == 1
    assert "conn2" not in game_router.pending_invitations
    assert (
        mock_server.player_manager.players_by_conn["conn1"]["status"]
        == "ingame"
    )
    assert (
        mock_server.player_manager.players_by_conn["conn2"]["status"]
        == "ingame"
    )


def test_handle_decline_request(game_router, mock_server):
    """Test declining an invitation resets statuses."""
    game_router.pending_invitations["conn2"] = {
        "requester": "conn1",
        "expires": 9999999999,
    }
    mock_server.player_manager.players_by_conn["conn1"]["status"] = "waitgame"
    mock_server.player_manager.players_by_conn["conn2"]["status"] = "waitgame"

    game_router.handle_decline_request("conn2")

    assert "conn2" not in game_router.pending_invitations
    assert (
        mock_server.player_manager.players_by_conn["conn1"]["status"] == "idle"
    )
    assert (
        mock_server.player_manager.players_by_conn["conn2"]["status"] == "idle"
    )
    mock_server._send.assert_any_call(
        "conn1", "INFO Player_2 declined your invitation."
    )


def test_handle_cancel_request(game_router, mock_server):
    """Test cancelling an invitation resets statuses."""
    game_router.pending_invitations["conn2"] = {
        "requester": "conn1",
        "expires": 9999999999,
    }
    mock_server.player_manager.players_by_conn["conn1"]["status"] = "waitgame"
    mock_server.player_manager.players_by_conn["conn2"]["status"] = "waitgame"

    game_router.handle_cancel_request("conn1")

    assert "conn2" not in game_router.pending_invitations
    assert (
        mock_server.player_manager.players_by_conn["conn1"]["status"] == "idle"
    )
    assert (
        mock_server.player_manager.players_by_conn["conn2"]["status"] == "idle"
    )
    mock_server._send.assert_any_call(
        "conn2", "INFO Player_1 cancelled the invitation."
    )


def test_invitation_timeout(game_router, mock_server):
    """Test cleanup of expired invitations."""
    game_router.pending_invitations["conn2"] = {
        "requester": "conn1",
        "expires": time.time() - 10,
    }
    mock_server.player_manager.players_by_conn["conn1"]["status"] = "waitgame"
    mock_server.player_manager.players_by_conn["conn2"]["status"] = "waitgame"

    game_router.check_invitation_timeouts()

    assert "conn2" not in game_router.pending_invitations
    assert (
        mock_server.player_manager.players_by_conn["conn2"]["status"] == "idle"
    )
    assert (
        mock_server.player_manager.players_by_conn["conn1"]["status"] == "idle"
    )
    mock_server._send.assert_any_call("conn2", "INFO Invitation expired.")
    mock_server._send.assert_any_call("conn1", "INFO Your invitation expired.")


def test_get_wait_status(game_router, mock_server):
    """Test waitgame command response."""
    game_router.pending_invitations["conn2"] = {
        "requester": "conn1",
        "expires": 9999999999,
    }
    mock_server.player_manager.players_by_conn["conn1"]["status"] = "waitgame"
    mock_server.player_manager.players_by_conn["conn2"]["status"] = "waitgame"

    # Test for requester
    msg = game_router.get_wait_status("conn1")
    assert "Waiting for Player_2" in msg

    # Test for target
    msg = game_router.get_wait_status("conn2")
    assert "Challenged by Player_1" in msg


def test_handle_new_game_request_away(game_router, mock_server):
    """Test cannot invite away player."""
    mock_server.player_manager.players_by_conn["conn2"]["status"] = "away"
    game_router.handle_new_game_request("conn1", "Player_2")
    mock_server._send.assert_called_with(
        "conn1", "ERROR Player Player_2 is away."
    )


def test_handle_new_game_request_busy(game_router, mock_server):
    """Test cannot play against someone already in game."""
    mock_conn1 = MagicMock()
    mock_conn3 = MagicMock()

    mock_server.player_manager.players_by_conn = {
        mock_conn1: {"id": "Player_1", "status": "idle"},
        mock_conn3: {"id": "Player_3", "status": "ingame"},
    }

    game_router.handle_new_game_request(mock_conn1, "Player_3")
    mock_server._send.assert_called_with(
        mock_conn1, "ERROR Player Player_3 is ingame."
    )


def test_handle_new_game_request_self(game_router, mock_server):
    """Test player cannot challenge themselves."""
    mock_conn1 = MagicMock()
    mock_server.player_manager.players_by_conn = {
        mock_conn1: {"id": "Player_1", "status": "idle"},
    }

    game_router.handle_new_game_request(mock_conn1, "Player_1")
    mock_server._send.assert_called_with(
        mock_conn1, "ERROR You are challenging yourself."
    )


def test_handle_new_game_request_requester_busy(game_router, mock_server):
    """Test cannot start a game if requester is busy."""
    mock_conn1 = MagicMock()
    mock_conn2 = MagicMock()

    mock_server.player_manager.players_by_conn = {
        mock_conn1: {"id": "Player_1", "status": "ingame"},
        mock_conn2: {"id": "Player_2", "status": "idle"},
    }

    game_router.handle_new_game_request(mock_conn1, "Player_2")
    mock_server._send.assert_called_with(mock_conn1, "ERROR You are not idle.")


def test_handle_new_game_request_target_corrupted(game_router, mock_server):
    """Test that target state is reset if corrupted (has game_id but idle)."""
    mock_conn1 = MagicMock()
    mock_conn2 = MagicMock()

    mock_server.player_manager.players_by_conn = {
        mock_conn1: {"id": "Player_1", "status": "idle"},
        mock_conn2: {
            "id": "Player_2",
            "status": "idle",
            "game_id": "old_game",
        },
    }

    game_router.handle_new_game_request(mock_conn1, "Player_2")
    # It sends an invitation because status is idle
    mock_server._send.assert_any_call(
        mock_conn2, "INVITATION_RECEIVED FROM=Player_1 EXPIRES=300s"
    )


@patch("othello.game_engine.game_rules.GameRules.is_valid_move")
def test_process_move_valid(mock_is_valid, game_router, mock_server):
    """Test processing a valid move."""
    mock_is_valid.return_value = True
    mock_conn_x = MagicMock()
    mock_conn_o = MagicMock()

    mock_server.player_manager.players_by_conn = {
        mock_conn_x: {
            "id": "Player_1",
            "status": "ingame",
            "color": "X",
            "opponent": mock_conn_o,
            "game_id": "game1",
        },
        mock_conn_o: {
            "id": "Player_2",
            "status": "ingame",
            "color": "O",
            "opponent": mock_conn_x,
            "game_id": "game1",
        },
    }

    mock_state = MagicMock()
    mock_state.get_bitboards.return_value = (0, 0)
    mock_state.apply_move.return_value = (MagicMock(), "O")
    game_router.games["game1"] = {
        "X": mock_conn_x,
        "O": mock_conn_o,
        "state": mock_state,
        "current_player": "X",
    }

    client_info_x = mock_server.player_manager.players_by_conn[mock_conn_x]
    game_router.process_move(mock_conn_x, "X e4", client_info_x)
    mock_server._send.assert_called_with(mock_conn_o, "OPPONENT_MOVE X e4")


def test_process_move_terminal_state(game_router, mock_server):
    """Test processing a move that results in terminal state (game over)."""
    with (
        patch(
            "othello.game_engine.game_rules.GameRules.is_valid_move",
            return_value=True,
        ),
        patch(
            "othello.game_engine.game_rules.GameRules.is_terminal_state",
            return_value=True,
        ),
        patch(
            "othello.game_engine.game_rules.GameRules.determine_winner",
            return_value="X",
        ),
    ):

        mock_conn_x = MagicMock()
        mock_conn_o = MagicMock()

        mock_server.player_manager.players_by_conn = {
            mock_conn_x: {
                "id": "Player_1",
                "status": "ingame",
                "color": "X",
                "opponent": mock_conn_o,
                "game_id": "game1",
            },
            mock_conn_o: {
                "id": "Player_2",
                "status": "ingame",
                "color": "O",
                "opponent": mock_conn_x,
                "game_id": "game1",
            },
        }

        # We must explicitly add a lock
        mock_server.player_manager.lock = MagicMock()
        mock_server.player_manager._update_score = MagicMock()

        mock_state = MagicMock()
        mock_state.get_bitboards.return_value = (0, 0)
        mock_state.apply_move.return_value = (MagicMock(), "O")
        game_router.games["game1"] = {
            "X": mock_conn_x,
            "O": mock_conn_o,
            "state": mock_state,
            "current_player": "X",
        }

        client_info_x = mock_server.player_manager.players_by_conn[mock_conn_x]
        game_router.process_move(mock_conn_x, "X e4", client_info_x)

        # Check clean up logic
        assert "game1" not in game_router.games

        assert (
            mock_server.player_manager.players_by_conn[mock_conn_x]["status"]
            == "idle"
        )
        assert (
            mock_server.player_manager.players_by_conn[mock_conn_o]["status"]
            == "idle"
        )
        assert (
            mock_server.player_manager.players_by_conn[mock_conn_x]["game_id"]
            is None
        )

        mock_server.player_manager._update_score.assert_any_call(
            "Player_1", won=True
        )
        mock_server.player_manager._update_score.assert_any_call(
            "Player_2", won=False
        )

        # Check message dispatched
        mock_server._send.assert_any_call(mock_conn_o, "OPPONENT_MOVE X e4")
        msg = "INFO Game over! Winner is X."
        mock_server._send.assert_any_call(mock_conn_x, msg)
        mock_server._send.assert_any_call(mock_conn_o, msg)


def test_process_move_no_game_id(game_router, mock_server):
    """Test move rejected if client has no game_id."""
    mock_conn = MagicMock()
    game_router.process_move(mock_conn, "X e4", {"id": "P1"})
    mock_server._send.assert_called_with(
        mock_conn, "ERROR You are not in a game."
    )


def test_process_move_game_not_found(game_router, mock_server):
    """Test move rejected if game object is missing."""
    mock_conn = MagicMock()
    game_router.process_move(
        mock_conn, "X e4", {"id": "P1", "game_id": "missing"}
    )
    mock_server._send.assert_called_with(mock_conn, "ERROR Game not found.")


def test_process_move_wrong_turn(game_router, mock_server):
    """Test move rejected if it's not the player's turn."""
    mock_conn = MagicMock()
    game_router.games["g1"] = {"current_player": "O"}
    game_router.process_move(
        mock_conn, "X e4", {"id": "P1", "game_id": "g1", "color": "X"}
    )
    mock_server._send.assert_called_with(
        mock_conn, "ERROR It is not your turn."
    )


def test_process_move_invalid_format(game_router, mock_server):
    """Test move rejected if format is invalid."""
    mock_conn = MagicMock()
    game_router.games["g1"] = {"current_player": "X"}
    game_router.process_move(
        mock_conn, "invalid", {"id": "P1", "game_id": "g1", "color": "X"}
    )
    assert "ERROR Invalid move" in mock_server._send.call_args[0][1]


def test_process_move_wrong_color_in_msg(game_router, mock_server):
    """Test move rejected if player tries to play for opponent's color."""
    mock_conn = MagicMock()
    game_router.games["g1"] = {"current_player": "X"}
    game_router.process_move(
        mock_conn, "O e4", {"id": "P1", "game_id": "g1", "color": "X"}
    )
    mock_server._send.assert_called_with(
        mock_conn, "ERROR You cannot play for O."
    )


@patch("othello.game_engine.game_rules.GameRules.is_valid_move")
def test_process_move_illegal(mock_is_valid, game_router, mock_server):
    """Test move rejected if illegal according to rules."""
    mock_is_valid.return_value = False
    mock_conn = MagicMock()
    mock_state = MagicMock()
    mock_state.get_bitboards.return_value = (0, 0)
    game_router.games["g1"] = {"current_player": "X", "state": mock_state}

    game_router.process_move(
        mock_conn, "X e4", {"id": "P1", "game_id": "g1", "color": "X"}
    )
    mock_server._send.assert_called_with(
        mock_conn, "ERROR Move rejected by server (illegal): X e4"
    )


def test_handle_sudden_disconnect(game_router, mock_server):
    """Test alerting opponent on sudden disconnect."""
    mock_conn_o = MagicMock()
    game_router.handle_sudden_disconnect(
        {"game_id": "g1", "opponent": mock_conn_o}
    )
    assert "Opponent disconnected" in mock_server._send.call_args[0][1]
    assert mock_server._send.call_args[0][0] == mock_conn_o


def test_handle_disconnect_timeout(game_router, mock_server):
    """Test cleanup after reconnection timeout."""
    mock_conn_o = MagicMock()
    opp_info = {"id": "P2", "status": "ingame"}
    mock_server.player_manager.players_by_conn[mock_conn_o] = opp_info
    game_router.games["g1"] = {}

    game_router.handle_disconnect_timeout(
        {"game_id": "g1", "opponent": mock_conn_o}
    )
    assert "g1" not in game_router.games
    assert opp_info["status"] == "idle"
    assert "forfeit" in mock_server._send.call_args[0][1]


def test_handle_reconnect_success(game_router, mock_server):
    """Test successful reconnection restores state."""
    mock_conn_new = MagicMock()
    mock_conn_opp = MagicMock()
    opp_info = {"id": "P2", "opponent": "old_conn"}
    mock_server.player_manager.players_by_conn[mock_conn_opp] = opp_info

    mock_state = MagicMock()
    mock_state.black_board = 123
    mock_state.white_board = 456
    game_router.games["g1"] = {
        "X": "old_conn",
        "O": mock_conn_opp,
        "state": mock_state,
        "current_player": "X",
    }

    game_router.handle_reconnect(
        mock_conn_new,
        {"game_id": "g1", "color": "X", "opponent": mock_conn_opp},
    )

    assert game_router.games["g1"]["X"] == mock_conn_new
    assert opp_info["opponent"] == mock_conn_new
    mock_server._send.assert_any_call(mock_conn_new, "START X")
    mock_server._send.assert_any_call(mock_conn_new, "SYNC_BOARD X 123 456")


def test_handle_reconnect_no_game(game_router, mock_server):
    """Test reconnection fail if game no longer exists."""
    mock_conn = MagicMock()
    client_info = {"game_id": "g1", "color": "X"}
    game_router.handle_reconnect(mock_conn, client_info)

    assert client_info["status"] == "idle"
    mock_server._send.assert_called_with(
        mock_conn, "ERROR The game no longer exists (aborted)."
    )


def test_handle_new_game_request_target_not_found(game_router, mock_server):
    """Test challenging a non-existent player."""
    mock_conn1 = MagicMock()
    mock_server.player_manager.players_by_conn = {
        mock_conn1: {"id": "Player_1", "status": "idle"},
    }
    mock_server.player_manager._get_player_by_id = MagicMock(
        return_value=(None, None)
    )
    game_router.handle_new_game_request(mock_conn1, "Unknown")
    mock_server._send.assert_called_with(
        mock_conn1, "ERROR Player Unknown not found."
    )


def test_handle_accept_request_invalid_states(game_router, mock_server):
    """Test exceptions in handle_accept_request."""
    mock_conn = MagicMock()

    # Target info none or not waitgame
    mock_server.player_manager.players_by_conn = {}
    game_router.handle_accept_request(mock_conn)
    mock_server._send.assert_called_with(
        mock_conn, "ERROR You have no pending invitation."
    )

    # Target info exists, but no invitation
    mock_server.player_manager.players_by_conn = {
        mock_conn: {"id": "P2", "status": "waitgame"}
    }
    game_router.handle_accept_request(mock_conn)
    mock_server._send.assert_called_with(
        mock_conn, "ERROR Invitation expired or not found."
    )

    # Target info exists, invitation exists, but requester is gone
    mock_server.player_manager.players_by_conn[mock_conn][
        "status"
    ] = "waitgame"
    game_router.pending_invitations[mock_conn] = {"requester": "missing_conn"}
    game_router.handle_accept_request(mock_conn)
    mock_server._send.assert_called_with(
        mock_conn, "ERROR Requester disconnected."
    )


def test_handle_decline_request_invalid_states(game_router, mock_server):
    """Test exceptions in handle_decline_request."""
    mock_conn = MagicMock()
    # Missing target_info
    mock_server.player_manager.players_by_conn = {}
    game_router.handle_decline_request(mock_conn)
    mock_server._send.assert_called_with(
        mock_conn, "ERROR No invitation to decline."
    )


def test_handle_cancel_request_invalid_states(game_router, mock_server):
    """Test exceptions in handle_cancel_request."""
    mock_conn = MagicMock()
    # Missing requester_info
    mock_server.player_manager.players_by_conn = {}
    game_router.handle_cancel_request(mock_conn)
    mock_server._send.assert_called_with(
        mock_conn, "ERROR No invitation to cancel."
    )


def test_get_wait_status_invalid_states(game_router, mock_server):
    """Test edge cases for get_wait_status."""
    mock_conn = MagicMock()

    # Not connected
    mock_server.player_manager.players_by_conn = {}
    assert "ERROR Not connected" in game_router.get_wait_status(mock_conn)

    # Not waitgame
    mock_server.player_manager.players_by_conn = {
        mock_conn: {"id": "P1", "status": "idle"}
    }
    assert "INFO You are not currently waiting" in game_router.get_wait_status(
        mock_conn
    )

    # Waitgame but requester in pending_invitations (simulated via loop)
    mock_server.player_manager.players_by_conn[mock_conn][
        "status"
    ] = "waitgame"
    mock_target_conn = MagicMock()
    mock_server.player_manager.players_by_conn[mock_target_conn] = {
        "id": "TargetP",
        "status": "idle",
    }
    game_router.pending_invitations[mock_target_conn] = {
        "requester": mock_conn,
        "expires": time.time() + 10,
    }
    assert "Waiting for TargetP" in game_router.get_wait_status(mock_conn)
