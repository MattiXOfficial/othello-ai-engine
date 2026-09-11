from unittest.mock import ANY
from unittest.mock import MagicMock
from unittest.mock import patch

import builtins
import pytest
import queue

from othello.common.command import AcceptCommand
from othello.common.command import AwayCommand
from othello.common.command import BackCommand
from othello.common.command import CancelCommand
from othello.common.command import CommandParser
from othello.common.command import CommandType
from othello.common.command import DeclineCommand
from othello.common.command import HelpCommand
from othello.common.command import HintCommand
from othello.common.command import JoinCommand
from othello.common.command import LoadCommand
from othello.common.command import MoveCommand
from othello.common.command import NameCommand
from othello.common.command import NewCommand
from othello.common.command import NewGameRemoteCommand
from othello.common.command import PauseCommand
from othello.common.command import PingCommand
from othello.common.command import PlayersCommand
from othello.common.command import QuitCommand
from othello.common.command import RedoCommand
from othello.common.command import SaveCommand
from othello.common.command import ScoreboardCommand
from othello.common.command import ServerCommand
from othello.common.command import ServerStatusCommand
from othello.common.command import SetCommand
from othello.common.command import ShowCommand
from othello.common.command import UndoCommand
from othello.common.command import WaitgameCommand
from othello.orchestrator.bitboard_ops import BitboardOps

# Mock translation function to avoid NameError during tests
builtins._ = lambda x: x


@pytest.fixture
def mock_session():
    """Crée une session de jeu mockée avec un état contrôlable."""
    session = MagicMock()
    # Configuration par défaut
    session.current_player = "X"
    session.game_state.black_board = 0
    session.game_state.white_board = 0
    session.game_client = None  # Explicitly set to None
    session.unsaved_changes = False  # Explicitly set to False
    session.blitz_mode = None
    # Mock de la vue pour éviter les erreurs
    session.view = MagicMock()
    session.game_server = None  # Ensure no ghost server
    return session


@pytest.fixture(autouse=True)
def setup_bitboard():
    BitboardOps.set_board_size(8)


def test_command_getters():
    # Move
    cmd = MoveCommand("X e4")
    assert cmd.get_type() == CommandType.MOVE
    assert cmd.get_data() == {"input": "X e4"}

    # Quit
    cmd = QuitCommand()
    assert cmd.get_type() == CommandType.QUIT
    assert cmd.get_data() == {"force": False}

    # Help
    cmd = HelpCommand()
    assert cmd.get_type() == CommandType.HELP
    assert cmd.get_data() == {"topic": None}

    # Save
    cmd = SaveCommand("file.txt", "comment")
    assert cmd.get_type() == CommandType.SAVE
    assert cmd.get_data() == {"filename": "file.txt", "comment": "comment"}

    # Load
    cmd = LoadCommand("file.txt")
    assert cmd.get_type() == CommandType.LOAD
    assert cmd.get_data() == {"filename": "file.txt"}


def test_parser_new():
    cmd = CommandParser.parse("new size=10 vs_ai")
    assert isinstance(cmd, NewCommand)
    assert cmd.args == ["size=10", "vs_ai"]


def test_parser_pause_hint():
    assert isinstance(CommandParser.parse("pause"), PauseCommand)
    assert isinstance(CommandParser.parse("hint"), HintCommand)


def test_parser_undo_redo():
    # Sans argument
    cmd_undo = CommandParser.parse("undo")
    assert isinstance(cmd_undo, UndoCommand)
    assert cmd_undo.n_moves == 1

    # Avec argument
    cmd_redo = CommandParser.parse("redo 3")
    assert isinstance(cmd_redo, RedoCommand)
    assert cmd_redo.n_moves == 3


def test_parser_show():
    # show board (défaut ou explicite)
    assert isinstance(
        CommandParser.parse("show"), HelpCommand
    )  # "show" seul -> Help

    cmd = CommandParser.parse("show board")
    assert isinstance(cmd, ShowCommand)
    assert cmd.target == "board"

    # Alias history
    assert isinstance(CommandParser.parse("history"), ShowCommand)
    assert CommandParser.parse("history").target == "history"

    # Alias config
    assert isinstance(CommandParser.parse("config"), ShowCommand)
    assert CommandParser.parse("config").target == "configuration"


def test_parser_set():
    # Cas 1 : set param=val
    cmd = CommandParser.parse("set debug=true")
    assert isinstance(cmd, SetCommand)
    assert cmd.param == "debug"
    assert cmd.value == "true"

    # Cas 3 : set vide -> Help
    assert isinstance(CommandParser.parse("set"), HelpCommand)


def test_parser_help():
    cmd = CommandParser.parse("help")
    assert isinstance(cmd, HelpCommand)


def test_parser_save_invalid():
    # Cas où l'utilisateur tape juste "save" sans fichier
    cmd = CommandParser.parse("save")
    assert isinstance(cmd, SaveCommand)
    assert cmd.filename is None


def test_parser_load_invalid():
    # Cas où l'utilisateur tape juste "load" sans fichier
    cmd = CommandParser.parse("load")
    assert isinstance(cmd, LoadCommand)
    assert cmd.filename is None


def test_move_execute_parsing_error(mock_session):
    cmd = MoveCommand("X Z99")  # Invalide

    # On force GameRules.move_parser à échouer
    # (si ce n'est pas déjà le cas nativement)
    with patch(
        "othello.game_engine.game_rules.GameRules.move_parser",
        side_effect=ValueError("Bad format"),
    ):
        result = cmd.execute(mock_session)

    assert result is True  # Le jeu continue
    mock_session.view.display_error.assert_called_with("Bad format")


def test_move_execute_wrong_turn(mock_session):
    mock_session.current_player = "X"
    cmd = MoveCommand("O a1")

    # On mock le parseur pour qu'il renvoie bien ("O", 0)
    with patch(
        "othello.game_engine.game_rules.GameRules.move_parser",
        return_value=("O", 0),
    ):
        result = cmd.execute(mock_session)

    assert result is True
    args, _ = mock_session.view.display_error.call_args
    assert "turn to play" in args[0]


def test_move_execute_invalid_move(mock_session):
    mock_session.current_player = "X"
    cmd = MoveCommand("X a1")

    with patch(
        "othello.game_engine.game_rules.GameRules.move_parser",
        return_value=("X", 0),
    ):
        # On force is_valid_move à False
        with patch(
            "othello.game_engine.game_rules.GameRules.is_valid_move",
            return_value=False,
        ):
            result = cmd.execute(mock_session)

    assert result is True
    args, _ = mock_session.view.display_error.call_args
    assert "Illegal move" in args[0]


def test_move_execute_success_and_switch_player(mock_session):
    mock_session.current_player = "X"

    cmd = MoveCommand("X c4")

    with (
        patch(
            "othello.game_engine.game_rules.GameRules.move_parser",
            return_value=("X", 27),
        ),
        patch(
            "othello.game_engine.game_rules.GameRules.is_valid_move",
            return_value=True,
        ),
        patch(
            "othello.game_engine.game_rules.GameRules.is_game_over",
            return_value=False,
        ),
        patch.object(
            mock_session.game_state,
            "apply_move",
            return_value=(mock_session.game_state, "O"),
        ),
    ):
        result = cmd.execute(mock_session)

    assert result is True
    assert mock_session.current_player == "O"


def test_move_execute_game_over(mock_session):
    mock_session.current_player = "X"
    cmd = MoveCommand("X c4")

    new_state = MagicMock()
    mock_session.game_state.apply_move.return_value = (new_state, "O")

    with patch(
        "othello.game_engine.game_rules.GameRules.move_parser",
        return_value=("X", 27),
    ):
        with patch(
            "othello.game_engine.game_rules.GameRules.is_valid_move",
            return_value=True,
        ):
            with patch(
                "othello.game_engine.game_rules.GameRules.compute_flips",
                return_value=0,
            ):
                # Cette fois, le jeu est fini
                with patch(
                    "othello.game_engine.game_rules.GameRules.is_game_over",
                    return_value=True,
                ):
                    result = cmd.execute(mock_session)

    # Le jeu doit s'arrêter
    assert result is False
    mock_session.view.render.assert_called()


def test_help_execute(mock_session):
    cmd = HelpCommand()
    assert cmd.execute(mock_session) is True
    mock_session.view.display_message.assert_called()


def test_quit_execute(mock_session):
    cmd = QuitCommand()
    assert cmd.execute(mock_session) is False  # Doit arrêter la boucle
    mock_session.view.display_message.assert_called()


def test_save_execute_valid(mock_session):
    cmd = SaveCommand("game.sav", "memo")
    assert cmd.execute(mock_session) is True
    mock_session.save_game.assert_called_with("game.sav", "memo")


def test_save_execute_missing_filename(mock_session):
    cmd = SaveCommand(None)
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Usage: save <filename> [comment]"
    )


def test_load_execute_valid(mock_session):
    cmd = LoadCommand("game.sav")
    mock_session.load_game.return_value = True

    assert cmd.execute(mock_session) is True
    mock_session.load_game.assert_called_with("game.sav")


def test_load_execute_load_fails(mock_session):
    """Le chargement échoue (fichier introuvable par exemple)."""
    cmd = LoadCommand("ghost.sav")
    mock_session.load_game.return_value = False

    assert cmd.execute(mock_session) is True
    mock_session.view.display_message.assert_not_called()


def test_load_execute_missing_filename(mock_session):
    cmd = LoadCommand(None)
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Usage: load <filename>"
    )


def test_move_sets_unsaved_flag():
    session = MagicMock()
    session.current_player = "X"
    session.unsaved_changes = False
    session.blitz_mode = None
    session.game_client = None
    new_state = MagicMock()
    session.game_state.apply_move.return_value = (new_state, "O")

    cmd = MoveCommand("X e4")

    # On mocke toute la logique de règles pour isoler le test du flag
    with patch(
        "othello.game_engine.game_rules.GameRules.move_parser",
        return_value=("X", 27),
    ):
        with patch(
            "othello.game_engine.game_rules.GameRules.is_valid_move",
            return_value=True,
        ):
            with patch(
                "othello.game_engine.game_rules.GameRules.compute_flips",
                return_value=0,
            ):
                with patch(
                    "othello.game_engine.game_rules.GameRules.is_game_over",
                    return_value=False,
                ):
                    cmd.execute(session)

    assert session.unsaved_changes is True


def test_undo_execute(mock_session):
    cmd = UndoCommand("2")
    mock_session.undo_move.return_value = True

    assert cmd.execute(mock_session) is True
    mock_session.undo_move.assert_called_with(2)
    mock_session.view.display_message.assert_called()


def test_redo_execute(mock_session):
    cmd = RedoCommand("1")
    mock_session.redo_move.return_value = True

    assert cmd.execute(mock_session) is True
    mock_session.redo_move.assert_called_with(1)


def test_new_execute_valid(mock_session):
    mock_session.game_client = None
    cmd = NewCommand(["--size", "10"])

    assert cmd.execute(mock_session) is True
    # Vérifie que reset_game a reçu les bons arguments parsés
    mock_session.reset_game.assert_called()
    call_args = mock_session.reset_game.call_args[0][0]
    assert call_args["size"] == "10"


def test_new_execute_invalid_size(mock_session):
    # Taille impaire interdite
    cmd = NewCommand(["--size", "7"])
    assert cmd.execute(mock_session) is True
    mock_session.reset_game.assert_not_called()


def test_set_execute_success(mock_session):
    cmd = SetCommand("debug", "true")

    # On mocke ConfigManager pour ne pas toucher au vrai fichier config
    with patch("othello.common.command.ConfigManager") as mock_config:
        mock_instance = mock_config.return_value
        # Simule que la validation passe
        mock_instance._validate_single_option.return_value = True

        assert cmd.execute(mock_session) is True

        mock_instance.set.assert_called_with("debug", "true")
        mock_session.view.display_message.assert_called()


def test_set_execute_invalid_value(mock_session):
    cmd = SetCommand("size", "999")

    with patch("othello.common.command.ConfigManager") as mock_config:
        mock_instance = mock_config.return_value
        mock_instance._validate_single_option.return_value = False

        assert cmd.execute(mock_session) is True
        mock_instance.set.assert_not_called()
        mock_session.view.display_error.assert_called()


def test_set_execute_size_during_game(mock_session):
    # Simule une partie en cours (historique non vide)
    mock_session.history = ["X E4"]
    cmd = SetCommand("size", "10")

    assert cmd.execute(mock_session) is True
    # Doit afficher une erreur et ne pas appeler ConfigManager
    mock_session.view.display_error.assert_called()
    assert (
        "Can't change the size during a game"
        in mock_session.view.display_error.call_args[0][0]
    )


def test_show_board(mock_session):
    cmd = ShowCommand("board")
    mock_session.current_player = "X"
    mock_session.game_state.get_board_as_string.return_value = "board_str"
    assert cmd.execute(mock_session) is True
    mock_session.view.render.assert_called_with("board_str", ANY, ANY, ANY)


def test_show_history_empty(mock_session):
    cmd = ShowCommand("history")
    mock_session.history = []
    assert cmd.execute(mock_session) is True
    mock_session.view.display_message.assert_called_with("History empty.")


def test_show_configuration(mock_session):
    cmd = ShowCommand("configuration")

    with patch("othello.common.command.ConfigManager") as mock_config:
        # Mock du dictionnaire de config
        mock_config.return_value.config_parser = {"defaults": {"lang": "fr"}}

        assert cmd.execute(mock_session) is True
        # Vérifie qu'on affiche bien la config
        args = mock_session.view.display_message.call_args[0][0]
        assert "lang = fr" in args


def test_show_unknown(mock_session):
    cmd = ShowCommand("kebab")
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called()


def test_show_time_blitz_disabled(mock_session):
    """Test 'show time' quand le mode blitz n'est pas actif."""
    mock_session.blitz_mode = None
    cmd = ShowCommand("time")

    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_once_with(
        "Blitz is not enabled."
    )


def test_show_time_blitz_active_player_x(mock_session):
    """Test 'show time' pendant le tour de X (lit le timer directement)."""
    mock_session.blitz_mode = MagicMock()
    # On simule que le thread a déjà descendu le temps à 250s pour X
    mock_session.blitz_mode.remaining_time = {"X": 250.0, "O": 300.0}
    mock_session.blitz_mode.is_paused = False
    mock_session.current_player = "X"

    cmd = ShowCommand("time")
    assert cmd.execute(mock_session) is True

    # 250 secondes = 04:10 pour X. O reste à 300 (05:00)
    mock_session.view.display_message.assert_called_once_with(
        "Remaining Time : X (04:10)- O (05:00)"
    )


def test_show_time_blitz_active_player_o(mock_session):
    """Test 'show time' pendant le tour de O."""
    mock_session.blitz_mode = MagicMock()
    mock_session.blitz_mode.remaining_time = {"X": 300.0, "O": 200.0}
    mock_session.blitz_mode.is_paused = False
    mock_session.current_player = "O"

    cmd = ShowCommand("time")
    assert cmd.execute(mock_session) is True

    # 200 secondes pour O (03:20). X reste à 300 (05:00)
    mock_session.view.display_message.assert_called_once_with(
        "Remaining Time : X (05:00)- O (03:20)"
    )


def test_show_time_blitz_paused(mock_session):
    """Test 'show time' quand le jeu est en pause."""
    mock_session.blitz_mode = MagicMock()
    mock_session.blitz_mode.remaining_time = {"X": 250.0, "O": 300.0}
    mock_session.blitz_mode.is_paused = True  # En pause

    cmd = ShowCommand("time")
    assert cmd.execute(mock_session) is True

    # Le statut (Paused) doit être affiché
    mock_session.view.display_message.assert_called_once_with(
        "Remaining Time (Paused) : X (04:10)- O (05:00)"
    )


def test_pause_execute(mock_session):
    mock_session.blitz_mode = MagicMock()
    assert PauseCommand().execute(mock_session) is True
    mock_session.blitz_mode.pause.assert_called_once()


def test_pause_execute_no_blitz(mock_session):
    mock_session.blitz_mode = None
    assert PauseCommand().execute(mock_session) is True
    mock_session.view.display_error.assert_called()


@patch("othello.common.command.AIPlayer.random_move")
def test_hint_execute(mock_random_move, mock_session):
    mock_random_move.return_value = "X e4"
    assert HintCommand().execute(mock_session) is True
    mock_random_move.assert_called_once_with((0, 0), "X")
    mock_session.view.display_message.assert_called_with(
        "Hint: X e4 seems like a good move."
    )


def test_parser_network_commands():
    assert isinstance(CommandParser.parse("server list"), ServerCommand)
    assert isinstance(CommandParser.parse("join 1.1.1.1:1234"), JoinCommand)
    assert isinstance(CommandParser.parse("ping"), PingCommand)
    assert isinstance(CommandParser.parse("players"), PlayersCommand)
    assert isinstance(CommandParser.parse("scoreboard"), ScoreboardCommand)
    assert isinstance(CommandParser.parse("players player1"), PlayersCommand)
    assert isinstance(CommandParser.parse("accept"), AcceptCommand)
    assert isinstance(CommandParser.parse("decline"), DeclineCommand)
    assert isinstance(CommandParser.parse("cancel"), CancelCommand)
    assert isinstance(CommandParser.parse("away"), AwayCommand)
    assert isinstance(CommandParser.parse("back"), BackCommand)
    assert isinstance(CommandParser.parse("waitgame"), WaitgameCommand)


def test_server_command_list(mock_session):
    cmd = ServerCommand("list")

    # We simulate the new logic (it uses game_session.discovery_service now)
    mock_ds_instance = MagicMock()
    mock_session.discovery_service = mock_ds_instance
    mock_ds_instance.get_server_list.return_value = ["ServerA@127.0.0.1:12345"]

    assert cmd.execute(mock_session) is True
    mock_session.view.display_message.assert_any_call(
        " - ServerA@127.0.0.1:12345"
    )


@patch("othello.common.command.GameServer")
def test_server_command_start(mock_game_server, mock_session):
    cmd = ServerCommand("start", "12345")
    mock_session.game_server = None
    # stops the current loop to enter server loop
    mock_game_server.return_value.is_running = False
    assert cmd.execute(mock_session) is False
    mock_game_server.assert_called_once()
    mock_session.server_command_loop.assert_called_once()


def test_join_command(mock_session):
    cmd = JoinCommand("127.0.0.1:12345")

    with patch("othello.network.game_client.GameClient.join") as mock_connect:
        mock_connect.return_value = True

        assert cmd.execute(mock_session) is True
        # if it succed a thread should be spawned for the client loop
        # to work with
        assert mock_session.game_client is not None
        mock_session.view.display_message.assert_called_with(
            "Successfully connected to the server. Type 'players' or "
            "'new <ids>' to interact ."
        )


def test_network_info_commands(mock_session):
    # We need to make sure game_server fails the
    # if check since mock hasattr returns
    # True for everything.
    mock_session.game_server = None
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True

    # Test players
    p_cmd = PlayersCommand()
    # Mock queue to avoid loop
    mock_session.game_client.message_queue.get.side_effect = queue.Empty()
    p_cmd.execute(mock_session)
    mock_session.game_client.send_message.assert_called_with("PLAYERS")

    # Test scoreboard
    s_cmd = ScoreboardCommand()
    mock_session.game_client.message_queue.get.side_effect = queue.Empty()
    s_cmd.execute(mock_session)
    mock_session.game_client.send_message.assert_called_with("SCOREBOARD")


def test_invitation_commands_execute(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True

    AcceptCommand().execute(mock_session)
    mock_session.game_client.send_message.assert_called_with("ACCEPT")

    DeclineCommand().execute(mock_session)
    mock_session.game_client.send_message.assert_called_with("DECLINE")

    CancelCommand().execute(mock_session)
    mock_session.game_client.send_message.assert_called_with("CANCEL")


def test_status_commands_execute(mock_session):
    mock_session.game_server = None
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True

    AwayCommand().execute(mock_session)
    mock_session.game_client.send_message.assert_any_call("AWAY")

    BackCommand().execute(mock_session)
    mock_session.game_client.send_message.assert_any_call("BACK")

    WaitgameCommand().execute(mock_session)
    mock_session.game_client.send_message.assert_any_call("WAITGAME")


def test_players_command_cli_wait(mock_session):
    mock_session.game_server = None
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    # Redirect view to avoid print
    mock_session.view = MagicMock()
    # Force CLI mode
    type(mock_session.view).__name__ = "CLIShell"

    q = queue.Queue()
    q.put("PLAYERS_LIST header")
    mock_session.game_client.message_queue = q

    # Mock time to avoid infinite loop
    with patch("time.time", side_effect=[100.0, 100.1, 100.2, 110.0, 110.0]):
        PlayersCommand("arthur").execute(mock_session)

    mock_session.game_client.send_message.assert_called_with("PLAYERS arthur")
    mock_session.handle_network_message.assert_called_with(
        "PLAYERS_LIST header"
    )


def test_quit_execute_connected(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True

    mock_client = mock_session.game_client
    cmd = QuitCommand()
    assert (
        cmd.execute(mock_session) is True
    )  # Should return True to continue in local mode after disconnect
    mock_client.quit.assert_called_once()
    assert mock_session.game_client is None
    mock_session.view.display_message.assert_called_with(
        "Disconnected from server."
    )
    mock_session.reset_game.assert_called_with({})


def test_load_execute_empty_filename(mock_session):
    # This specifically tests the branch inside the command execution
    # if called with empty string
    # though parser usually handles it.
    cmd = LoadCommand("")
    assert cmd.execute(mock_session) is True
    # If the code reaches the check "if not filename" inside execute
    # (assuming we bypass parser validation)
    mock_session.view.display_error.assert_called_with(
        "Usage: load <filename>"
    )


def test_new_execute_lobby(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True

    # Missing args
    cmd = NewCommand([])
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Usage in Lobby: new <player_id>"
    )

    # Correct usage
    cmd = NewCommand(["arthur"])
    assert cmd.execute(mock_session) is True
    mock_session.game_client.send_message.assert_called_with("NEW arthur")


def test_server_command_getters():
    cmd = ServerCommand("start", 1234)
    assert cmd.get_type() == CommandType.SERVER
    assert cmd.get_data() == {"action": "start", "port": 1234}


def test_server_command_list_error(mock_session):
    cmd = ServerCommand("list")
    mock_session.discovery_service = None
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Background discovery service not initialized."
    )


def test_server_command_list_empty(mock_session):
    cmd = ServerCommand("list")
    mock_session.discovery_service = MagicMock()
    mock_session.discovery_service.get_server_list.return_value = []
    # Force CLI mode
    mock_session.view.__class__.__name__ = "CLIShell"

    assert cmd.execute(mock_session) is True
    mock_session.view.display_message.assert_called_with(
        "No servers found (listening in background...)."
    )


def test_server_command_start_running(mock_session):
    cmd = ServerCommand("start")
    mock_session.game_server = MagicMock()
    mock_session.game_server.is_running = True
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Server is already running."
    )


def test_server_command_stop(mock_session):
    cmd = ServerCommand("stop")

    # No server
    mock_session.game_server = None
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with("No server running.")

    # Running server
    mock_server = MagicMock()
    mock_session.game_server = mock_server
    assert cmd.execute(mock_session) is True
    mock_server.stop_server.assert_called_once()
    assert mock_session.game_server is None
    mock_session.view.display_message.assert_called_with("Server stopped.")


def test_server_command_unknown(mock_session):
    cmd = ServerCommand("unknown")
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_any_call(
        "Unknown server action: unknown"
    )


def test_join_command_complex(mock_session):
    # Case: already connected, should quit first
    old_client = MagicMock()
    old_client.client_id = "old_id"
    old_client.is_connected = True
    mock_session.game_client = old_client

    with patch("othello.common.command.GameClient") as mock_client_class:
        new_client = mock_client_class.return_value
        new_client.join.return_value = True
        cmd = JoinCommand("localhost:5555", "new_id")
        assert cmd.execute(mock_session) is True

        old_client.quit.assert_called_once()
        assert new_client.client_id == "new_id"
        assert new_client.game_session == mock_session


def test_join_command_fail(mock_session):
    mock_session.game_client = None
    with patch("othello.common.command.GameClient") as mock_client_class:
        new_client = mock_client_class.return_value
        new_client.join.return_value = False

        cmd = JoinCommand("1.1.1.1:1111")
        assert cmd.execute(mock_session) is True
        assert mock_session.game_client is None
        mock_session.view.display_error.assert_called_with(
            "Could not join server."
        )


def test_ping_command_full(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True

    # Mock message queue behavior
    q = queue.Queue()
    q.put("OTHER_MSG")
    q.put("PONG")
    mock_session.game_client.message_queue = q

    cmd = PingCommand()
    assert cmd.execute(mock_session) is True

    mock_session.game_client.ping.assert_called_once()
    mock_session.view.display_message.assert_any_call("Ping requested.")
    # Check that OTHER_MSG was re-queued
    assert q.get() == "OTHER_MSG"


def test_ping_command_timeout(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    mock_session.game_client.message_queue = queue.Queue()  # Empty

    with patch("time.time", side_effect=[100, 100.1, 103]):  # Force timeout
        cmd = PingCommand()
        assert cmd.execute(mock_session) is True
        mock_session.view.display_error.assert_called_with(
            "Ping timeout: No response from server."
        )


def test_server_status_command(mock_session):
    # Case 1: local server
    mock_session.game_server = MagicMock()
    mock_session.game_server.get_server_status.return_value = "STATUS OK"

    cmd = ServerStatusCommand()
    assert cmd.execute(mock_session) is True
    mock_session.view.display_message.assert_called_with("STATUS OK")

    # Case 2: remote server
    mock_session.game_server = None
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    q = queue.Queue()
    q.put("SERVER_STATUS details")
    mock_session.game_client.message_queue = q

    assert cmd.execute(mock_session) is True
    mock_session.game_client.send_message.assert_called_with("SERVER_STATUS")
    mock_session.handle_network_message.assert_called_with(
        "SERVER_STATUS details"
    )


def test_name_command_execute(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    q = queue.Queue()
    q.put("NAME_OK arthur")
    mock_session.game_client.message_queue = q
    # Force CLI mode
    mock_session.view.__class__.__name__ = "CLIShell"

    cmd = NameCommand("arthur")
    assert cmd.execute(mock_session) is True
    mock_session.game_client.send_message.assert_called_with("NAME arthur")
    mock_session.handle_network_message.assert_called_with("NAME_OK arthur")


def test_players_command_gui_server(mock_session):
    mock_session.game_server = MagicMock()
    mock_session.game_server.player_manager._get_players_list.return_value = (
        "PLAYERS_LIST - P1\nPLAYERS_LIST - P2"
    )

    # Mock GUI view
    mock_session.view = MagicMock()
    mock_session.view.__str__.return_value = "GUIApp"
    type(mock_session.view).__name__ = (
        "GUIApp"  # Potentially needed if code uses type()
    )

    # I'll use a hack to satisfy: "GUIApp" in str(type(game_session.view))
    class GUIApp:
        pass

    mock_session.view = GUIApp()
    mock_session.view.output_queue = queue.Queue()

    cmd = PlayersCommand()
    assert cmd.execute(mock_session) is True

    # Check queue content
    data = mock_session.view.output_queue.get()
    assert data == ("player_list", ["P1", "P2"])


def test_parser_complex_join():
    # join localhost:1234 arthur
    cmd = CommandParser.parse("join localhost:1234 arthur")
    assert isinstance(cmd, JoinCommand)
    assert cmd.target == "localhost:1234"
    assert cmd.client_id == "arthur"

    # join arthur (no IP)
    cmd = CommandParser.parse("join arthur")
    assert isinstance(cmd, JoinCommand)
    assert cmd.target == "127.0.0.1:12345"
    assert cmd.client_id == "arthur"


def test_scoreboard_command_sync(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    q = queue.Queue()
    q.put("SCOREBOARD data")
    mock_session.game_client.message_queue = q

    cmd = ScoreboardCommand()

    # Mock time.time to ensure the loop runs at least once
    with patch("time.time", side_effect=[100.0, 100.1, 100.2, 110.0]):
        mock_session.game_server = None  # Important
        assert cmd.execute(mock_session) is True

    mock_session.handle_network_message.assert_called_with("SCOREBOARD data")


def test_new_game_remote_command():
    cmd = NewGameRemoteCommand("target")
    assert cmd.get_type() == CommandType.NEW
    assert cmd.get_data() == {"target": "target"}

    mock_session = MagicMock()
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True

    assert cmd.execute(mock_session) is True
    mock_session.game_client.send_message.assert_called_with("NEW target")


def test_ping_command_exception(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    # Raise exception when accessing message_queue
    mock_session.game_client.message_queue = MagicMock()
    mock_session.game_client.message_queue.get.side_effect = Exception(
        "Queue error"
    )

    cmd = PingCommand()
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Ping Error: Queue error"
    )


def test_ping_command_disconnected(mock_session):
    mock_session.game_client = None
    cmd = PingCommand()
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Not connected to a server. Try 'join' first."
    )


def test_server_status_command_disconnected(mock_session):
    mock_session.game_server = None
    mock_session.game_client = None
    cmd = ServerStatusCommand()
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Not connected to a server."
    )


def test_players_command_disconnected(mock_session):
    mock_session.game_server = None
    mock_session.game_client = None
    cmd = PlayersCommand()
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Not connected to a server."
    )


def test_invitation_commands_disconnected(mock_session):
    mock_session.game_client = None
    # Test all invitation related commands when disconnected
    commands = [
        AcceptCommand(),
        DeclineCommand(),
        CancelCommand(),
        AwayCommand(),
        BackCommand(),
        WaitgameCommand(),
    ]
    for cmd in commands:
        assert cmd.execute(mock_session) is True
        mock_session.view.display_error.assert_called_with(
            "Not connected to a server."
        )


def test_scoreboard_command_local(mock_session):
    mock_session.game_server = MagicMock()
    mock_session.game_server.player_manager._get_scoreboard.return_value = (
        "LOCAL SCORE"
    )

    cmd = ScoreboardCommand()
    assert cmd.execute(mock_session) is True
    mock_session.view.display_message.assert_called_with("LOCAL SCORE")


def test_players_command_sync_wait_details(mock_session):
    mock_session.game_server = None
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    q = queue.Queue()
    # First some other message, then header
    q.put("OTHER")
    q.put("PLAYERS_LIST Connected Players:\n- P1")
    mock_session.game_client.message_queue = q

    # Mock time to avoid infinite loop but allow one iteration
    with patch(
        "time.time",
        side_effect=[100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 110.0, 110.0],
    ):
        cmd = PlayersCommand()
        assert cmd.execute(mock_session) is True

    mock_session.handle_network_message.assert_any_call(
        "PLAYERS_LIST Connected Players:\n- P1"
    )
    # Verify OTHER was re-queued
    assert q.get() == "OTHER"


def test_parser_server_status():
    cmd = CommandParser.parse("server status")
    assert isinstance(cmd, ServerStatusCommand)


def test_parser_name():
    cmd = CommandParser.parse("name arthur")
    assert isinstance(cmd, NameCommand)
    assert cmd.pseudo == "arthur"


def test_show_in_network_lobby(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    mock_session.players = {"X": MagicMock(), "O": MagicMock()}

    cmd = ShowCommand("history")
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "You are not in a game."
    )


def test_hint_in_network_mode(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True

    cmd = HintCommand()
    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "AI commands are not available in network mode."
    )


def test_set_in_network_mode(mock_session):
    mock_session.game_client = MagicMock()
    mock_session.game_client.is_connected = True
    cmd = SetCommand("size", "10")

    assert cmd.execute(mock_session) is True
    mock_session.view.display_error.assert_called_with(
        "Cannot change game rules or AI settings while connected to a server."
    )
