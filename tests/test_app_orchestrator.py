from unittest.mock import patch

import pytest

from othello.common.config_manager import ConfigManager
from othello.orchestrator.app_orchestrator import Orchestrator
from othello.orchestrator.bitboard_ops import BitboardOps


@pytest.fixture(autouse=True)
def mock_cli_dependencies():
    """Execute before every test."""
    with (
        patch("othello.user_interface.cli_shell.readline"),
        patch("othello.user_interface.cli_shell.atexit"),
        patch("othello.user_interface.cli_shell.os"),
    ):
        yield


@pytest.fixture
def clean_config(tmp_path):
    """Ensure ConfigManager is reset.

    Uses a temporary config file before each test.
    """
    ConfigManager._instance = None
    with patch(
        "othello.common.config_manager.Path.home", return_value=tmp_path
    ):
        yield
    ConfigManager._instance = None


def test_orchestrator_init_defaults(clean_config):
    """Test that Orchestrator initializes with defaults.

    When no args are passed.
    """
    with patch("sys.argv", ["othello"]):
        orch = Orchestrator()

        # Check standard default config
        assert orch.config["size"] == "8"
        assert BitboardOps.SIZE == 8
        assert "input_file" not in orch.config


def test_orchestrator_init_with_args(clean_config):
    """Test that Orchestrator applies command line arguments.

    To configuration.
    """
    with patch("sys.argv", ["othello", "--size", "6", "--verbose"]):
        orch = Orchestrator()

        assert orch.config["size"] == "6"
        assert orch.config["verbose"] == "true"
        # Verify BitboardOps was updated
        assert BitboardOps.SIZE == 6


def test_orchestrator_run_start_session(clean_config):
    """Test that run() starts a GameSession."""
    with (
        patch("sys.argv", ["othello"]),
        patch(
            "othello.orchestrator.app_orchestrator.GameSession"
        ) as mock_session,
    ):
        orch = Orchestrator()
        orch.run()

        mock_session.assert_called_once()
        # Verify command_loop was called on the instance
        mock_session.return_value.command_loop.assert_called_once()


@patch("othello.orchestrator.app_orchestrator.GameServer")
def test_orchestrator_run_server_mode(mock_game_server, clean_config):
    """Test starting the app as a dedicated server in interactive mode."""
    with patch("sys.argv", ["othello", "--server"]):
        orch = Orchestrator()

        with patch(
            "othello.orchestrator.app_orchestrator.GameSession"
        ) as mock_session:
            orch.run()

            # check game server
            mock_game_server.assert_called_once()
            mock_game_server.return_value.start_server.assert_called_with(
                is_daemon=False
            )

            # check server command loop
            mock_session.assert_called_once()
            mock_session.return_value.server_command_loop.assert_called_once()


@patch("othello.orchestrator.app_orchestrator.GameServer")
def test_orchestrator_run_daemon_mode(mock_game_server, clean_config):
    """Test starting the app as a dedicated daemon server."""
    with patch("sys.argv", ["othello", "--server", "--daemon"]):
        orch = Orchestrator()

        # mock of os.fork and os.setsid to prevent actual forks during test
        # will not work without it
        with (
            patch("os.fork", return_value=0),
            patch("os.setsid"),
            patch("sys.exit"),
            patch("os.dup2"),
            patch("builtins.open"),
            patch("sys.stdin.fileno", return_value=0),
            patch("sys.stdout.fileno", return_value=1),
            patch("sys.stderr.fileno", return_value=2),
        ):
            # same for time
            mock_game_server.return_value.is_running = False
            orch.run()

            mock_game_server.return_value.start_server.assert_called_with(
                is_daemon=True
            )
