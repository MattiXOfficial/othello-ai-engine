import pytest
import queue
import sys

from othello.orchestrator.bitboard_ops import BitboardOps
from othello.orchestrator.game_session import GameSession
from othello.player.real_player import RealPlayer
from unittest.mock import MagicMock
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_gettext(monkeypatch):
    """Avoid NameError for _() function."""
    import builtins

    monkeypatch.setattr(builtins, "_", lambda x: x, raising=False)


@pytest.fixture
def mock_ui():
    """Returns a mock for the InterfaceView."""
    view = MagicMock()
    view.get_input.return_value = "quit"

    del view.input_queue
    del view.game_over

    return view


@pytest.fixture
def mock_config_manager():
    with patch("othello.orchestrator.game_session.ConfigManager") as mock_cm:
        instance = mock_cm.return_value
        mock_cm.DEFAULT_CONFIG = {"debug": "false", "turns-limit": "100"}
        instance.config_parser = {"defaults": {"input_file": "", "size": "8"}}
        yield instance


@pytest.fixture
def session(tmp_path, mock_ui):
    """Creates a GameSession instance.

    Isolated in a temp directory for saves.
    """
    BitboardOps.set_board_size(8)
    gs = GameSession(view=mock_ui)
    # Important : on redirige le dossier de sauvegarde
    # vers le dossier temporaire du test
    gs.SAVES_DIR = str(tmp_path)
    return gs


def test_init(session, mock_ui):
    assert session.current_player == "X"
    assert session.view == mock_ui
    assert BitboardOps.SIZE == 8


def test_command_loop_save_call(session):
    """Test that 'save mygame' triggers the save_game method."""
    with patch.object(session, "save_game") as mock_save:
        session.view.get_input.side_effect = ["save mygame", "quit", "quit"]
        session.command_loop()
        mock_save.assert_called_once_with("mygame", None)


def test_command_loop_save_error(session):
    """Test 'save' without filename displays error."""
    session.view.get_input.side_effect = ["save", "quit", "quit"]
    session.command_loop()
    session.view.display_error.assert_called_with(
        "Usage: save <filename> [comment]"
    )


def test_command_loop_load_call(session):
    """Test that 'load mygame' triggers the load_game method."""
    with patch.object(session, "load_game") as mock_load:
        session.view.get_input.side_effect = ["load mygame", "quit", "quit"]
        session.command_loop()

        mock_load.assert_called_once_with("mygame")


def test_command_loop_load_error(session):
    """Test 'load' without filename displays error."""
    session.view.get_input.side_effect = ["load", "quit", "quit"]
    session.command_loop()
    session.view.display_error.assert_called_with("Usage: load <filename>")


def test_real_save_game(session, tmp_path):
    """Test writing a game state to a file."""
    filename = "test_save.othello"

    session.game_state.current_player = "O"

    session.save_game(filename, comment="Unit Test")

    saved_file = tmp_path / filename
    assert saved_file.exists()
    content = saved_file.read_text(encoding="utf-8")
    assert "[settings]" in content
    assert "[game]" in content
    assert "[history]" in content
    assert "# Unit Test" in content
    assert "O" in content

    session.view.display_message.assert_called_with(
        f"Game saved successfully to {saved_file}"
    )


def test_real_load_game_success(session, tmp_path):
    """Test loading a valid game file updates the state."""
    filename = "test_load.othello"
    file_path = tmp_path / filename
    content = """[settings]
debug=false

[game]
O
X O _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
X-captures: 1
O-captures: 1
"""
    file_path.write_text(content, encoding="utf-8")

    assert session.load_game(filename) is True

    assert session.current_player == "O"
    assert session.game_state.black_board == (1 << 0)

    session.view.display_message.assert_called_with(
        f"Game loaded from {file_path}"
    )


def test_real_load_game_not_found(session):
    session.load_game("ghost.othello")
    args, _ = session.view.display_error.call_args
    assert "File not found" in args[0]


def test_real_load_game_resize(session, tmp_path):
    """Test loading a 6x6 game into an 8x8 session resizes the rules."""
    assert BitboardOps.SIZE == 8

    filename = "small.othello"
    content = """[settings]
debug=false

[game]
X
_ _ _ _ _ _
_ _ X O _ _
_ _ O X _ _
_ _ _ _ _ _
_ _ _ _ _ _
_ _ _ _ _ _
"""
    (tmp_path / filename).write_text(content, encoding="utf-8")

    session.load_game(filename)

    assert BitboardOps.SIZE == 6
    session.view.display_message.assert_any_call("Loaded board size is 6.")


def test_read_clean_lines_io_error(session):
    """Test _read_clean_lines returns None on IOError."""
    with patch("builtins.open", side_effect=IOError):
        result = session._read_clean_lines("fake_path")
        assert result is None


def test_init_with_input_file_success(mock_ui):
    """Test __init__ when an input_file is defined.

    In config and loads successfully.
    """
    # On mocke ConfigManager juste pour ce test pour avoir un input_file
    with patch("othello.orchestrator.game_session.ConfigManager") as mock_cm:
        instance = mock_cm.return_value
        instance.config_parser = {
            "defaults": {"input_file": "save.txt", "size": "8"}
        }

        with patch.object(
            GameSession, "load_game", return_value=True
        ) as mock_load:
            gs = GameSession(view=mock_ui)

            mock_load.assert_called_once_with("save.txt")
            assert gs.game_state.black_board == 0


def test_init_with_input_file_failure(mock_ui):
    """Test __init__ when input_file fails to load (fallback to default)."""
    with patch("othello.orchestrator.game_session.ConfigManager") as mock_cm:
        instance = mock_cm.return_value
        instance.config_parser = {
            "defaults": {"input_file": "bad.txt", "size": "8"}
        }

        # On mocke load_game pour simuler un échec
        with patch.object(GameSession, "load_game", return_value=False):
            gs = GameSession(view=mock_ui)

            mock_ui.display_error.assert_called_with(
                "Could not load bad.txt. Starting default game."
            )
            assert gs.game_state.black_board != 0


def test_save_game_io_error(session):
    """Test save_game handles IOError gracefully."""
    # On mocke open pour lever une erreur (ex: permission denied)
    with patch("builtins.open", side_effect=IOError("Disk full")):
        session.save_game("test.txt")
        session.view.display_error.assert_called_with(
            "Error saving game: Disk full"
        )


def test_load_game_empty_file(session, tmp_path):
    """Test loading an empty file."""
    f = tmp_path / "empty.othello"
    f.write_text("")  # Fichier vide
    session.load_game("empty.othello")
    session.view.display_error.assert_called_with("File is empty or invalid.")


def test_load_game_missing_sections(session, tmp_path):
    """Test loading a file with missing sections."""
    f = tmp_path / "bad_header.othello"
    f.write_text("[game]\nX\n_ _\n_ _\n")
    session.load_game("bad_header.othello")
    session.view.display_error.assert_called_with(
        "Invalid file format: Missing [settings] or [game] section."
    )


def test_load_game_game_section_too_short(session, tmp_path):
    """Test [game] section with not enough lines."""
    f = tmp_path / "short.othello"
    content = """[settings]
debug=false
[game]
X
"""  # Il manque le plateau
    f.write_text(content)
    session.load_game("short.othello")
    # Message d'erreur mis à jour
    session.view.display_error.assert_called_with(
        "Invalid board size '0' in save file."
    )


def test_load_game_file_too_short_for_board(session, tmp_path):
    """Test file content is shorter than the declared board size."""
    f = tmp_path / "truncated.othello"
    content = """[settings]
debug=false
[game]
X
X X X
"""
    f.write_text(content)

    session.load_game("truncated.othello")
    args, _ = session.view.display_error.call_args
    assert "Invalid board size '1' in save file." in args[0]


def test_load_game_inconsistent_row_length(session, tmp_path):
    """Test a row having different length than the first row."""
    f = tmp_path / "inconsistent.othello"
    content = """[settings]
debug=false
[game]
X
X X X
X X
X X X
"""
    f.write_text(content)
    session.load_game("inconsistent.othello")
    args, _ = session.view.display_error.call_args
    assert "Invalid board size '3' in save file." in args[0]


def test_load_game_general_exception(session, tmp_path):
    """Test unexpected exception during load."""
    # On mocke _read_clean_lines pour lever une erreur générique
    filename = "bad_file.othello"
    (tmp_path / filename).touch()
    with patch.object(
        session, "_read_clean_lines", side_effect=Exception("Boom")
    ):
        session.load_game(filename)
        session.view.display_error.assert_called_with(
            "Error loading game: Boom"
        )


def test_command_loop_unexpected_exception(session):
    """Test generic exception in loop (should continue, then quit)."""
    session.view.get_input.side_effect = [
        Exception("Random crash"),
        "quit",
        "quit",
    ]
    session.command_loop()
    session.view.display_error.assert_called_with(
        "An unexpected error occurred: Random crash"
    )


def test_load_game_with_complex_comments(session, tmp_path):
    """Test loading a file with mixed inline (#) and block ({}) comments."""
    filename = "comments.othello"
    file_path = tmp_path / filename
    content = """[settings]
debug=false

[game]
{ Ce fichier est un test
  pour les commentaires blocs
  sur plusieurs lignes }
O { Le joueur }
{ Bloc ignoré } X { Bloc ignoré } O _ _ _ _ _ _ # Fin de ligne ignorée
_ _ _ _ { # Ce dièse ne doit pas couper le bloc } _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
_ _ _ _ _ _ _ _
"""
    file_path.write_text(content, encoding="utf-8")

    assert session.load_game(filename) is True
    assert session.current_player == "O"
    assert BitboardOps.get_token(session.game_state.black_board, 0) == 1
    assert BitboardOps.get_token(session.game_state.white_board, 1) == 1

    session.view.display_message.assert_called_with(
        f"Game loaded from {file_path}"
    )


def test_load_game_block_comment_inside_inline(session, tmp_path):
    """Test that a { inside a # comment is ignored."""
    filename = "edge_case.othello"
    file_path = tmp_path / filename

    content = """[settings]
debug=false

[game]
X
# Voici un commentaire avec une accolade ouvrante { qui ne doit pas tout casser
X X X X X X X X
X X X X X X X X
X X X X X X X X
X X X X X X X X
X X X X X X X X
X X X X X X X X
X X X X X X X X
X X X X X X X X
"""
    file_path.write_text(content, encoding="utf-8")
    assert session.load_game(filename) is True
    assert session.current_player == "X"


def test_parse_history_success(session):
    """Test that _parse_history correctly populates the history list."""
    # We force valid moves to bypass rule checks and focus on parsing logic
    with patch(
        "othello.game_engine.game_rules.GameRules.is_valid_move",
        return_value=True,
    ):
        lines = ["X f5", "O d6", "X c5"]
        assert session._parse_history(lines) is True
        # The history should contain exactly these 3 moves
        assert len(session.history) == 3
        assert session.history[0].upper().strip() == "X F5"
        assert session.history[1].upper().strip() == "O D6"
        assert session.history[2].upper().strip() == "X C5"


def test_server_command_loop_quit(session):
    """Test the server owner's interactive loop can quit."""
    session.game_server = MagicMock()
    session.view.get_input.side_effect = ["server status", "quit"]
    session.server_command_loop()

    # Should stop the server
    session.game_server.stop_server.assert_called_once()


def test_command_loop_keyboard_interrupt_network_disconnect(session):
    """Test KeyboardInterrupt when game_client is disconnected.

    (server crash).
    """
    # Mocking termios so tests don't fail cross-platform
    with patch("sys.stdin"), patch("termios.tcflush", create=True):
        session.game_client = MagicMock()
        session.game_client.is_connected = False

        # simulate the keyboard interrupt
        # should hit the network check, and loop again
        # next input should be "quit" to end normally without infinite loop
        session.view.get_input.side_effect = [
            KeyboardInterrupt(),
            "quit",
            "quit",
        ]

        session.command_loop()

        # shouldn't see "Interrupted. End of the game."
        # because the network branch catches
        # it and 'continues'. But 'quit' commands end the loop
        # Check that it didn't call the immediate quit print
        calls = session.view.display_message.call_args_list
        for call in calls:
            assert "Interrupted. End of the game." not in call[0][0]


def test_handle_network_message_info_cli(session):
    """Test INFO message handling in CLI."""
    assert (
        session.handle_network_message("INFO Game started against bob") is True
    )
    session.view.display_message.assert_called_with("Game started against bob")
    assert getattr(session, "_lobby_prompt_active", True) is False


def test_handle_network_message_info_gui(session):
    """Test INFO message with OPPONENT logic in GUI."""

    class DummyGUIApp(MagicMock):
        pass

    session.view = DummyGUIApp()
    session.view.output_queue = queue.Queue()

    msg = "INFO Game started against alice!"
    assert session.handle_network_message(msg) is True
    session.view.display_message.assert_called_with(
        "Game started against alice!"
    )

    assert not session.view.output_queue.empty()
    item = session.view.output_queue.get()
    assert item == ("set_network_status", "[Online] vs alice")


def test_handle_network_message_invitation_received_gui(session):
    class DummyGUIApp(MagicMock):
        pass

    session.view = DummyGUIApp()
    session.view.output_queue = queue.Queue()
    assert (
        session.handle_network_message(
            "INVITATION_RECEIVED FROM=alice EXPIRES=30"
        )
        is True
    )
    assert not session.view.output_queue.empty()
    item = session.view.output_queue.get()
    assert item == ("invitation_received", "alice")


def test_handle_network_message_error_disconnect(session):
    with patch.object(session, "reset_game") as mock_reset:
        assert (
            session.handle_network_message("ERROR Opponent disconnected")
            is True
        )
        mock_reset.assert_called_once_with({})


def test_handle_network_message_start(session):
    session.game_client = MagicMock()
    assert session.handle_network_message("START X") is True
    session.game_client._setup_network_game.assert_called_once_with("X")


def test_handle_network_message_players_list_no_players(session):
    assert (
        session.handle_network_message("PLAYERS_LIST No players connected.")
        is True
    )
    session.view.display_message.assert_called_with("No players connected.")


def test_sync_board(session):
    session.current_player = "O"
    session.game_state.black_board = 0
    session.game_state.white_board = 0

    sync_data = "X 8 16"
    session.sync_board(sync_data)

    assert session.current_player == "X"
    assert session.game_state.black_board == 8
    assert session.game_state.white_board == 16
    assert session.unsaved_changes is True
    session.view.render.assert_called()


def test_handle_network_disconnect(session):
    mock_client = MagicMock()
    mock_client.is_connected = True
    session.game_client = mock_client

    mock_server = MagicMock()
    mock_server.is_running = True
    session.game_server = mock_server

    with patch.object(session, "reset_game") as mock_reset:
        session.handle_network_disconnect()

        mock_client.quit.assert_called_once()
        assert session.game_client is None
        mock_server.stop_server.assert_called_once()
        assert session.game_server is None
        mock_reset.assert_called_once_with({})


def test_command_loop_network_messages(session):
    """Test that command_loop processes messages from game_client's queue."""
    session.game_client = MagicMock()
    session.game_client.message_queue = queue.Queue()
    session.game_client.message_queue.put("__DISCONNECTED__")

    with (
        patch.object(session, "handle_network_disconnect") as mock_disconnect,
        patch("select.select", side_effect=KeyboardInterrupt()),
    ):
        session.command_loop()
        mock_disconnect.assert_called_once()


def test_command_loop_network_opponent_move(session):
    session.game_client = MagicMock()
    session.game_client.message_queue = queue.Queue()
    session.game_client.message_queue.put("OPPONENT_MOVE D3")

    with patch("select.select", side_effect=KeyboardInterrupt()):
        session.command_loop()

    assert not session.game_client.message_queue.empty()
    assert session.game_client.message_queue.get() == "OPPONENT_MOVE D3"


def test_command_loop_network_quit(session):
    session.game_client = MagicMock()
    session.game_client.message_queue = queue.Queue()
    session.game_client.message_queue.put("QUIT")

    with (
        patch(
            "othello.orchestrator.game_session.CommandParser.parse"
        ) as mock_parse,
        patch("select.select", side_effect=KeyboardInterrupt()),
    ):
        mock_command = MagicMock()
        mock_parse.return_value = mock_command

        session.command_loop()

        mock_parse.assert_any_call("quit")
        mock_command.execute.assert_called_with(session)


def test_server_command_loop_exception(session):
    """Test exceptions in server command loop are caught."""
    session.game_server = MagicMock()
    session.view.get_input.side_effect = [
        Exception("Test Server Error"),
        "quit",
    ]
    session.server_command_loop()

    session.view.display_error.assert_called_with(
        "An unexpected error occurred: Test Server Error"
    )


def test_server_command_loop_keyboard_interrupt_stop(session):
    """Test KeyboardInterrupt in server command loop stops server."""
    session.game_server = MagicMock()
    session.view.get_input.side_effect = KeyboardInterrupt()
    session.server_command_loop()

    session.game_server.stop_server.assert_called_once()


def test_handle_network_message_invitation_sent(session):
    assert (
        session.handle_network_message("INVITATION_SENT target_player") is True
    )
    session.view.display_message.assert_called_with(
        "Invitation sent: target_player"
    )
    assert getattr(session, "_lobby_prompt_active", True) is False


def test_handle_network_message_invitation_received_cli(session):
    assert (
        session.handle_network_message(
            "INVITATION_RECEIVED FROM=alice EXPIRES=300s"
        )
        is True
    )
    session.view.display_message.assert_any_call(
        "\n*** CHALLENGE RECEIVED ***\nFROM=alice EXPIRES=300s"
    )
    session.view.display_message.assert_any_call("Type 'accept' or 'decline'.")
    assert getattr(session, "_lobby_prompt_active", True) is False


def test_handle_network_message_invitation_accepted(session):
    assert session.handle_network_message("INVITATION_ACCEPTED") is True
    session.view.display_message.assert_called_with(
        "Invitation accepted! Game starting..."
    )


def test_handle_network_message_game_start(session):
    assert session.handle_network_message("GAME_START") is True


def test_handle_network_message_opponent(session):
    class DummyGUIApp(MagicMock):
        pass

    session.view = DummyGUIApp()
    session.view.output_queue = queue.Queue()
    assert session.handle_network_message("OPPONENT=charlie") is True
    item = session.view.output_queue.get()
    assert item == ("set_network_status", "[Online] vs charlie")


def test_handle_network_message_server_msg(session):
    assert session.handle_network_message("--- welcome ---") is True
    session.view.display_message.assert_called_with("\n--- welcome ---")
    assert getattr(session, "_lobby_prompt_active", True) is False

    assert session.handle_network_message("Server: goes down") is True
    session.view.display_message.assert_called_with("\nServer: goes down")


def test_handle_network_message_players_list_item(session):
    assert (
        session.handle_network_message("PLAYERS_LIST - alice (Idle)") is True
    )
    assert hasattr(session, "_player_list_buffer")
    assert "alice (Idle)" in session._player_list_buffer
    session.view.display_message.assert_called_with("alice (Idle)")


def test_handle_network_message_connected_players_cli(session):
    assert (
        session.handle_network_message("PLAYERS_LIST Connected Players:")
        is True
    )
    assert getattr(session, "_player_list_buffer") == []
    session.view.display_message.assert_called_with("Connected Players:")


def test_handle_network_message_players_list_detail_cli(session):
    assert session.handle_network_message("PLAYERS_LIST detail info") is True
    session.view.display_message.assert_called_with("detail info")


def test_handle_network_message_sync_board_routing(session):
    with patch.object(session, "sync_board") as mock_sync:
        assert session.handle_network_message("SYNC_BOARD X 123 456") is True
        mock_sync.assert_called_once_with("X 123 456")


def test_handle_network_message_scoreboard_cli(session):
    assert session.handle_network_message("SCOREBOARD 1 - alice (10)") is True
    session.view.display_message.assert_called_with("1 - alice (10)")
    assert getattr(session, "_lobby_prompt_active", True) is False


def test_handle_network_message_scoreboard_gui(session):
    class DummyGUIApp(MagicMock):
        pass

    session.view = DummyGUIApp()
    session.view.output_queue = queue.Queue()
    assert session.handle_network_message("SCOREBOARD 1 - bob (20)") is True
    assert session.view.output_queue.get() == (
        "scoreboard_line",
        "1 - bob (20)",
    )


def test_handle_network_message_server_status_cli(session):
    assert session.handle_network_message("SERVER_STATUS OK") is True
    session.view.display_message.assert_called_with("OK")
    assert getattr(session, "_lobby_prompt_active", True) is False


def test_handle_network_message_server_status_gui(session):
    class DummyGUIApp(MagicMock):
        pass

    session.view = DummyGUIApp()
    session.view.output_queue = queue.Queue()
    assert session.handle_network_message("SERVER_STATUS GOOD") is True
    assert session.view.output_queue.get() == ("server_status_line", "GOOD")


def test_handle_network_message_pong(session):
    assert session.handle_network_message("PONG") is True
    session.view.display_message.assert_called_with("PONG")


def test_handle_network_message_name_ok(session):
    assert session.handle_network_message("NAME_OK SuperPlayer") is True
    session.view.display_message.assert_called_with(
        "Name changed to: SuperPlayer"
    )
    assert getattr(session, "_lobby_prompt_active", True) is False


def test_handle_network_message_your_id(session):
    assert session.handle_network_message("YOUR_ID 99998888") is True


def test_instant_log_with_output_queue(session):
    session.view.output_queue = queue.Queue()
    session.server_log_queue.put("test log")
    assert session.view.output_queue.get() == ("server_log", "test log")


def test_instant_log_without_output_queue(session):
    del session.view.output_queue  # Ensure hasattr returns False
    session.server_log_queue.put("test log")
    session.view.display_message.assert_any_call("test log")


def test_setup_players_ai_both(session):
    with patch("othello.orchestrator.game_session.ConfigManager") as mock_cm:
        instance = mock_cm.return_value
        instance.config_parser = {
            "defaults": {"ai_enabled": "true", "ai_color": "A"}
        }
        session._setup_players()
        assert session.players["X"].__class__.__name__ == "AIPlayer"
        assert session.players["O"].__class__.__name__ == "AIPlayer"


def test_setup_players_ai_black(session):
    with patch("othello.orchestrator.game_session.ConfigManager") as mock_cm:
        instance = mock_cm.return_value
        instance.config_parser = {
            "defaults": {"ai_enabled": "true", "ai_color": "b"}
        }
        session._setup_players()
        assert session.players["X"].__class__.__name__ == "AIPlayer"
        assert session.players["O"].__class__.__name__ == "RealPlayer"


def test_setup_players_ai_white(session):
    with patch("othello.orchestrator.game_session.ConfigManager") as mock_cm:
        instance = mock_cm.return_value
        instance.config_parser = {
            "defaults": {"ai_enabled": "true", "ai_color": "w"}
        }
        session._setup_players()
        assert session.players["X"].__class__.__name__ == "RealPlayer"
        assert session.players["O"].__class__.__name__ == "AIPlayer"


def test_load_default_board(session):
    session.game_state.black_board = 0
    session.game_state.white_board = 0
    session.load_default_board(8)
    assert BitboardOps.popcount(session.game_state.black_board) == 2
    assert BitboardOps.popcount(session.game_state.white_board) == 2


def test_on_blitz_timeout_cli(session):
    session._on_blitz_timeout("X")
    assert session.pending_timeout == "X"
    session.view.display_message.assert_called()


def test_on_blitz_timeout_gui(session):
    session.view.input_queue = queue.Queue()
    session._on_blitz_timeout("O")
    assert session.pending_timeout == "O"
    assert session.view.input_queue.get() == "__TIMEOUT__ O"


def test_reset_game_with_blitz_options(session):
    options = {"blitz": "true", "timeout": "10.0"}
    session.reset_game(options)
    assert session.blitz_mode is not None
    assert session.blitz_mode.time_limit == 10.0 * 60.0


def test_save_history_passed_turn(session, tmp_path):
    session.history = ["X e3", "X c5"]
    filename = "test_pass.othello"
    session.save_game(filename, comment="Sample")
    saved_file = tmp_path / filename
    content = saved_file.read_text(encoding="utf-8")
    assert "X e3\n" in content
    assert "# Sample\n" in content


def test_load_game_parse_game_state_missing_lines(session, tmp_path):
    f = tmp_path / "missing.othello"
    content = "[settings]\ndebug=false\n[game]\n"
    f.write_text(content)
    session.load_game("missing.othello")
    session.view.display_error.assert_called_with(
        "Invalid save file: [game] section is empty."
    )


def test_load_game_invalid_player(session, tmp_path):
    f = tmp_path / "inv_player.othello"
    content = "[settings]\ndebug=false\n[game]\nZ\n"
    f.write_text(content)
    session.load_game("inv_player.othello")
    session.view.display_error.assert_called_with(
        "Invalid player 'Z' in save file."
    )


def test_parse_history_sync_current_player(session):
    lines = ["X e3", "X c5"]
    session._parse_history(lines)
    assert session.current_player == "X"


def test_parse_history_execution_error(session):
    lines = ["X e3"]
    mock_cmd = MagicMock()
    mock_cmd.execute.return_value = False
    with patch(
        "othello.orchestrator.game_session.CommandParser.parse",
        return_value=mock_cmd,
    ):
        res = session._parse_history(lines)
        assert not res
        session.view.display_error.assert_called()


def test_load_game_parse_settings_fails(session, tmp_path):
    f = tmp_path / "test.othello"
    content = "[settings]\ndebug=false\n[game]\nX\n"
    f.write_text(content)
    with patch.object(session, "_parse_settings", return_value=False):
        assert session.load_game("test.othello") is False


def test_load_game_parse_game_fails(session, tmp_path):
    f = tmp_path / "test.othello"
    content = "[settings]\ndebug=false\n[game]\nX\n"
    f.write_text(content)
    with patch.object(session, "_parse_game_state", return_value=False):
        assert session.load_game("test.othello") is False


def test_command_loop_pending_timeout(session):
    session.pending_timeout = "X"
    session.command_loop()
    session.view.display_message.assert_called()
    assert session.pending_timeout is None


def test_command_loop_pending_timeout_gui(session):
    session.pending_timeout = "O"
    session.view.game_over = MagicMock(return_value="restart")
    with patch.object(session, "reset_game") as mock_reset:
        # Provide a quick quit input to break the loop after restarting
        session.view.get_input.side_effect = ["quit", "quit"]
        if hasattr(session.view, "input_queue"):
            del session.view.input_queue
        session.command_loop()
        mock_reset.assert_called_once()


def test_command_loop_starts_blitz_mode(session):
    mock_blitz = MagicMock()
    session.blitz_mode = mock_blitz
    session.view.get_input.side_effect = ["quit"]
    session.command_loop()
    mock_blitz.start.assert_called_once()


def test_command_loop_no_legal_moves_not_over(session):
    # simulate a situation where legal moves == 0, but game isn't over
    session.current_player = "X"
    session.game_state.black_board = 0
    session.game_state.white_board = 1  # White has pieces
    from othello.player.real_player import RealPlayer

    session.players["O"] = RealPlayer(
        "O"
    )  # Prevent AI MCTS invoking board state infinitely
    with (
        patch(
            "othello.orchestrator.game_session.GameRules.get_legal_moves",
            side_effect=[0] + [4] * 10,
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.is_game_over",
            return_value=False,
        ),
    ):
        session.view.get_input.side_effect = ["quit"] * 10
        session.command_loop()
        # verify that it passes the turn
        assert session.current_player == "O"
        session.view.display_message.assert_any_call(
            "No moves for X. Turn passed."
        )


def test_command_loop_no_legal_moves_game_over(session):
    # simulate a situation where game is over and legal_moves == 0
    session.current_player = "X"
    from othello.player.real_player import RealPlayer

    session.players["O"] = RealPlayer("O")
    with (
        patch(
            "othello.orchestrator.game_session.GameRules.get_legal_moves",
            side_effect=[0] + [4] * 10,
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.is_game_over",
            side_effect=[True, False],
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.determine_winner",
            return_value="X",
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.calculate_score",
            return_value={"X": 2, "O": 0},
        ),
    ):
        session.view.game_over = MagicMock(return_value="restart")
        session.view.get_input.side_effect = ["quit"] * 10  # after restart
        session.command_loop()
        # Game over should be called
        session.view.game_over.assert_called_once_with("X", {"X": 2, "O": 0})


def test_command_loop_network_game_over(session):
    """Test that command_loop resets the game and"""
    """continues when a network game naturally ends."""
    session.current_player = "X"

    session.players["X"] = RealPlayer("X")
    session.players["O"] = RealPlayer("O")

    # Enable network check
    session.game_client = MagicMock()
    session.game_client.is_connected = True
    # Do not put anything in message_queue to avoid interference

    with (
        patch(
            "othello.orchestrator.game_session.GameRules.get_legal_moves",
            side_effect=[0, 4],
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.is_game_over",
            return_value=True,
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.determine_winner",
            return_value="X",
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.calculate_score",
            return_value={"X": 2, "O": 0},
        ),
        patch.object(session, "reset_game") as mock_reset,
        patch("select.select", return_value=([sys.stdin], [], [])),
        patch("sys.stdin.readline", return_value="quit\n"),
    ):
        # We ensure it doesn't have GUI game over handling,
        # so it evaluates the CLI network condition
        if hasattr(session.view, "game_over"):
            delattr(session.view, "game_over")

        session.command_loop()

        # reset_game({}) should be called because it's a network game!
        mock_reset.assert_called_once_with({})


def test_init_blitz(mock_ui):
    with patch("othello.orchestrator.game_session.ConfigManager") as mock_cm:
        instance = mock_cm.return_value
        instance.config_parser = {
            "defaults": {
                "ai_enabled": "false",
                "blitz": "true",
                "timeout": "15",
            }
        }
        gs = GameSession(view=mock_ui)
        assert gs.blitz_mode is not None


def test_reset_game_size(session):
    session.reset_game({"size": "10"})
    assert 10 == BitboardOps.SIZE


def test_parse_game_state_inconsistent_row(session):
    # Pass a valid player line first
    lines = ["X", "X _ _ O O _ _ _ X"]
    assert not session._parse_game_state(lines)


def test_parse_history_exception(session):
    session.view.display_error = MagicMock()
    with patch("re.compile", side_effect=Exception("regex error")):
        assert not session._parse_history(["X c5"])
        session.view.display_error.assert_called()


def test_command_loop_gui_interception(session):
    import queue

    session.view.input_queue = queue.Queue()
    session.view.input_queue.put("quit")
    session.command_loop()
    session.view.quit.assert_called()


def test_command_loop_server_log(session):
    import queue

    session.view.output_queue = queue.Queue()
    session.server_log_queue.put("queued log")
    session.view.get_input.side_effect = ["quit", "quit"]
    session.command_loop()
    # It pulls it and places it in output queue
    assert not session.view.output_queue.empty()


def test_command_loop_disconnect(session):
    with patch.object(session, "handle_network_disconnect") as mock_disc:
        session.view.get_input.side_effect = [
            "__DISCONNECTED__",
            "quit",
            "quit",
        ]
        session.command_loop()
        mock_disc.assert_called_once()


def test_command_loop_timeout_input(session):
    session.view.get_input.side_effect = ["__TIMEOUT__ O", "quit", "quit"]
    session.command_loop()


def test_command_loop_game_over_after_command(session):
    session.view.get_input.side_effect = ["quit", "quit"]
    with (
        patch(
            "othello.orchestrator.game_session.GameRules.is_game_over",
            return_value=True,
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.determine_winner",
            return_value="X",
        ),
        patch(
            "othello.orchestrator.game_session.GameRules.get_legal_moves",
            return_value=4,
        ),
    ):
        session.view.game_over = MagicMock(return_value="quit")
        session.command_loop()
        session.view.game_over.assert_called_once()
        session.view.quit.assert_called()


def test_handle_network_message_info(session):
    assert session.handle_network_message(
        "INFO Game started against OPPONENT=TestBot"
    )
    session.view.display_message.assert_called()


def test_handle_network_message_invitation(session):
    assert session.handle_network_message("INVITATION_SENT Target")
    assert session.handle_network_message(
        "INVITATION_RECEIVED FROM=P1 EXPIRES=10"
    )
    assert session.handle_network_message("INVITATION_ACCEPTED")
    assert session.handle_network_message("GAME_START")


def test_handle_network_message_error(session):
    assert session.handle_network_message("ERROR Invalid move")
    session.view.display_error.assert_called()


def test_handle_network_message_players_list(session):
    assert session.handle_network_message("PLAYERS_LIST No players connected.")
    assert session.handle_network_message("PLAYERS_LIST - Player_1")
    assert session.handle_network_message("PLAYERS_LIST Connected Players:")


def test_handle_network_message_misc(session):
    assert session.handle_network_message("SYNC_BOARD X 1 2")
    assert session.handle_network_message("SCOREBOARD test")
    assert session.handle_network_message("SERVER_STATUS ok")
    assert session.handle_network_message("PONG")
    assert session.handle_network_message("NAME_OK test")
    assert session.handle_network_message("YOUR_ID 123")
    assert not session.handle_network_message("UNKNOWN_MSG")


def test_sync_board_invalid(session):
    session.sync_board("invalid")
    session.sync_board("X 1 invalid")


def test_server_command_loop(session):
    session.game_server = MagicMock()
    session.game_server.is_running = True
    session.view.get_input.side_effect = ["quit", "invalid command"]
    session.server_command_loop()
    session.game_server.stop_server.assert_called()


def test_server_command_loop_keyboard_interrupt(session):
    session.game_server = MagicMock()
    session.game_server.is_running = True
    session.view.get_input.side_effect = [KeyboardInterrupt()]
    session.server_command_loop()
    session.game_server.stop_server.assert_called()


def test_undo_redo_empty(session):
    assert not session.undo_move()
    assert not session.redo_move()


def test_undo_redo_move(session):
    session.register_move("X c5")
    assert session.undo_move()
    assert session.redo_move()


def test_save_game_with_comment(session):
    from unittest.mock import mock_open

    with patch("builtins.open", new_callable=mock_open) as mock_file:
        session.save_game("test.txt", comment="My comment")
        mock_file.assert_called()


def test_setup_players_ai_random(session):
    with patch("othello.orchestrator.game_session.ConfigManager") as mock_cm:
        instance = mock_cm.return_value
        instance.config_parser = {
            "defaults": {"ai_enabled": "true", "ai_color": "random"}
        }
        gs = GameSession(view=MagicMock())
        from othello.player.real_player import RealPlayer

        assert isinstance(gs.players["X"], RealPlayer)


def test_command_loop_ai_thread(session):
    from othello.player.ai_player import AIPlayer
    import queue

    session.players["X"] = AIPlayer("X")
    session.view.input_queue = queue.Queue()

    def fake_get_move(*args):
        import time

        time.sleep(0.1)
        session.view.input_queue.put("quit")
        time.sleep(0.1)
        return "quit"

    with (
        patch.object(AIPlayer, "get_move", side_effect=fake_get_move),
        patch(
            "othello.orchestrator.game_session.GameRules.get_legal_moves",
            return_value=4,
        ),
    ):
        session.command_loop()


def test_command_loop_network_client(session):

    session.game_client = MagicMock()
    session.game_client.is_connected = True
    session.game_client.message_queue = queue.Queue()
    session.game_client.message_queue.put("__DISCONNECTED__")

    # Mock get_input to return quit to exit the lobby loop
    session.view.get_input.side_effect = ["quit"]
    # Mock select.select to simulate input ready
    with patch("select.select", return_value=([sys.stdin], [], [])):
        with patch("sys.stdin.readline", return_value="quit\n"):
            session.command_loop()


def test_handle_network_message_players_list_details(session):
    assert session.handle_network_message("PLAYERS_LIST some details")
    session.view.display_message.assert_called()


def test_handle_network_disconnect_server():

    gs = GameSession(view=MagicMock())
    mock_server = MagicMock()
    gs.game_server = mock_server
    mock_server.is_running = True
    gs.handle_network_disconnect()
    mock_server.stop_server.assert_called()


def test_reset_game_stops_blitz(session):
    mock_blitz = MagicMock()
    session.blitz_mode = mock_blitz
    session.reset_game()
    mock_blitz.stop.assert_called()
