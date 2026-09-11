"""Commands Module."""

from abc import ABC
from abc import abstractmethod
from enum import Enum
from typing import Any
from typing import Optional
from typing import TYPE_CHECKING

# Monitor the server queue to render the board live
import queue
import time

from othello.common.arg_parser import ArgParser
from othello.common.config_manager import ConfigManager
from othello.common.i18n_manager import I18nManager
from othello.game_engine.game_rules import GameRules
from othello.game_engine.move_advisor import get_advice
from othello.network.game_client import GameClient
from othello.network.game_server import GameServer
from othello.orchestrator.bitboard_ops import BitboardOps
from othello.player.ai_player import AIPlayer

if TYPE_CHECKING:
    from othello.orchestrator.game_session import GameSession


def _(message):
    return I18nManager().gettext(message)


class CommandType(Enum):
    """Enumeration of available command types."""

    MOVE = "move"
    QUIT = "quit"
    HELP = "help"
    SAVE = "save"
    LOAD = "load"
    UNDO = "undo"
    REDO = "redo"
    NEW = "new"
    PAUSE = "pause"
    HINT = "hint"
    SHOW = "show"
    SET = "set"
    SERVER = "server"
    JOIN = "join"
    PING = "ping"

    SERVER_STATUS = "server_status"
    PLAYERS = "players"
    SCOREBOARD = "scoreboard"
    NAME = "name"

    ACCEPT = "accept"
    DECLINE = "decline"
    CANCEL = "cancel"
    AWAY = "away"
    BACK = "back"
    WAITGAME = "waitgame"


class Command(ABC):
    """Abstract base class for commands.

    Encapsulates user actions in a uniform way, allowing GameSession to
    handle commands identically whether they come from CLI or GUI.

    Each command knows how to execute itself given the game session context.

    """

    @abstractmethod
    def get_type(self) -> CommandType:
        """Get the type of this command.

        :return: CommandType enum value

        """

    @abstractmethod
    def get_data(self) -> dict[str, Any]:
        """Get command-specific data.

        :return: Dictionary containing command parameters

        """

    @abstractmethod
    def execute(self, game_session: "GameSession") -> bool:
        """Execute this command in the context of the given game session.

        :param game_session: The GameSession instance providing context
        :return: True if the game should continue, False if it should end

        """


class MoveCommand(Command):
    """Command representing a game move."""

    def __init__(self, raw_input: str):
        """Initialize a move command.

        :param raw_input: Raw input string (e.g., "X e4")

        """
        self.raw_input = raw_input

    def get_type(self) -> CommandType:
        return CommandType.MOVE

    def get_data(self) -> dict[str, Any]:
        return {"input": self.raw_input}

    def execute(self, game_session: "GameSession") -> bool:
        """Execute a move command: parse move, validate, and apply.

        :return: True to continue game, False if game is over

        """
        if (
            hasattr(game_session, "blitz_mode")
            and game_session.blitz_mode
            and game_session.blitz_mode.is_paused
        ):
            game_session.view.display_error(
                _("Game is paused. Use 'pause' to resume the game.")
            )
            return True
        size = BitboardOps.SIZE

        # 1. Move Parsing
        try:
            color, index = GameRules.move_parser(self.raw_input)
        except ValueError as error:
            game_session.view.display_error(
                str(error)
            )  # On ne traduit pas l'erreur Python brute ici
            return True  # Continue game

        # Turn Verification
        if color != game_session.current_player:
            game_session.view.display_error(
                _("It's {player}'s turn to play!").format(
                    player=game_session.current_player
                )
            )
            return True  # Continue game

        # Bitboard Retrieval
        if color == "X":
            player_bb = game_session.game_state.black_board
            opponent_bb = game_session.game_state.white_board
        else:
            player_bb = game_session.game_state.white_board
            opponent_bb = game_session.game_state.black_board

        col = index % size
        row = index // size

        # 2. Valid Move Check
        if not GameRules.is_valid_move(player_bb, opponent_bb, col, row):
            game_session.view.display_error(
                _(
                    "Illegal move: The square must be empty "
                    "and take at least one opponent piece."
                )
            )
            return True  # Continue game
        game_session.register_move(self.raw_input)

        # Broadcast the move if connected and it's a locally originated move
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            current_player = game_session.players[color]
            # Avoid echoing moves we just received from the network
            if type(current_player).__name__ != "NetworkPlayer":
                game_session.game_client.send_message(f"MOVE {self.raw_input}")
        # 3. Apply Move
        # Centralized State update
        new_state, next_player = game_session.game_state.apply_move(
            color, index
        )
        game_session.game_state = new_state

        # Game Over Check
        if GameRules.is_game_over(
            game_session.game_state.black_board,
            game_session.game_state.white_board,
        ):
            game_session.view.render(
                game_session.game_state.get_board_as_string(),
                0,
                game_session.current_player,
                game_session.unsaved_changes,
            )
            return False  # End game

        # Switch Player
        if next_player == color:
            game_session.view.display_message(
                _("Next player has no valid moves and must skip their turn!")
            )
        game_session.current_player = next_player

        if hasattr(game_session, "blitz_mode") and game_session.blitz_mode:
            game_session.blitz_mode.handle_turn(color, self.raw_input)

        game_session.unsaved_changes = True

        return True  # Continue game


class QuitCommand(Command):
    """Command to quit the game."""

    def __init__(self, force: bool = False):
        """Initialize quit command.

        :param force: If True, quit without prompting for save.
        """
        self.force = force

    def get_type(self) -> CommandType:
        return CommandType.QUIT

    def get_data(self) -> dict[str, Any]:
        return {"force": self.force}

    def execute(self, game_session: "GameSession") -> bool:
        """Execute quit command: display message and end game.

        :return: False to end the game
        """
        # Handle network disconnect first
        if (
            hasattr(game_session, "game_client")
            and game_session.game_client
            and game_session.game_client.is_connected
        ):
            game_session.game_client.send_message("ABANDON")
            game_session.game_client.quit()
            game_session.game_client = None
            game_session.view.display_message(_("Disconnected from server."))
            # Reset to a clean local game state
            game_session.reset_game({})
            return True  # Continue in local mode

        # Standard quit for local games
        if not game_session.unsaved_changes or self.force:
            game_session.view.display_message(_("End of the game."))
            return False

        while True:
            choice = (
                game_session.view.get_input(
                    _("Save the game before quitting? [y/N] ")
                )
                .strip()
                .lower()
            )

            if choice in ["y", "yes"]:
                filename = game_session.view.get_input(
                    _("Enter filename: ")
                ).strip()
                if not filename:
                    game_session.view.display_error(
                        _("Filename cannot be empty.")
                    )
                    continue

                if game_session.save_game(filename):
                    game_session.view.display_message(
                        _("Game saved. End of the game.")
                    )
                    return False
                else:
                    game_session.view.display_error(
                        _(
                            "Failed to save. Please try another filename "
                            "or quit without saving."
                        )
                    )
                    continue
            else:
                game_session.view.display_message(_("End of the game."))
                return False


class HelpCommand(Command):
    """Command to display help information."""

    def __init__(self, topic: Optional[str] = None):
        self.topic = topic

    def get_type(self) -> CommandType:
        return CommandType.HELP

    def get_data(self) -> dict[str, Any]:
        return {"topic": self.topic}

    def execute(self, game_session: "GameSession") -> bool:
        """Execute help command: display available commands.

        :return: True to continue the game
        """
        help_details = {
            "new": _(
                """
Usage: new [-h] [-V] [-v] [-d] [-b] [-t TIME] [-g] [-c] [-s {6,8,10,12}].

               [-a [AI]] [--ai-time AI_TIME]
               [--ai-mode {minimax,iterative,mcts}]
               [--ai-mcts-selection {UCT,ML,DL}]
               [--ai-minimax-depth AI_MINIMAX_DEPTH]
               [--ai-minimax-scoring AI_MINIMAX_SCORING]
               [--server [SERVER]] [--daemon]
               [-l {en,fr}]
               [file]
            Usage in Lobby: new <player_id>

Othello Game

positional arguments:
  file                  File to load (game save or contest file)

options:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
  -v, --verbose         Increase verbosity
  -d, --debug           Show debug messages
  -b, --blitz           Enable blitz mode
  -t, --time TIME       Time limit in minutes for blitz mode
  -g, --gui             Launch GUI
  -c, --contest         Contest mode
  -s, --size {6,8,10,12}
                        Board size (6, 8, 10 or 12). Default = 8.
  -a, --ai [AI]         Enable AI for a color (or all)
  --ai-time AI_TIME     AI thinking time in seconds
  --ai-mode {minimax,iterative,mcts}
                        AI algorithm mode
  --ai-mcts-selection {UCT,ML,DL}
                        MCTS Selection algorithm
  --ai-minimax-depth AI_MINIMAX_DEPTH
                        Minimax depth
  --ai-minimax-scoring AI_MINIMAX_SCORING
                        Minimax scoring function
  --server, -S [SERVER]
                        Start as server on port
  --daemon              Run server in daemon mode
  -l, --lang {en,fr}    Choose language

Note: When connected to a server, 'new <player_id>' sends a game invitation.
"""
            ),
            "move": _(
                "Usage: <Color> <Coordinates>\n"
                "Plays a move on the board.\n"
                "Example: 'X E4', 'O d3'"
            ),
            "save": _(
                "Usage: save <filename> [comment]\n"
                "Saves the current game state to a file.\n"
                "Example: 'save mygame.json', 'save backup \"Easy win\"'"
            ),
            "load": _(
                "Usage: load <filename>\n"
                "Loads a game state from a file.\n"
                "Example: 'load mygame.json'"
            ),
            "undo": _(
                "Usage: undo [N]\n"
                "Cancels the last N moves (default is 1).\n"
                "Example: 'undo', 'undo 3'"
            ),
            "redo": _(
                "Usage: redo [N]\n"
                "Replays the last N canceled moves (default is 1).\n"
                "Example: 'redo', 'redo 2'"
            ),
            "show": _(
                "Usage: show <target>\n"
                "Displays information about the game state.\n"
                "Targets:\n"
                " - board : Display the board\n"
                " - history : Display move history\n"
                " - time : Display remaining time\n"
                " - configuration : Display current settings"
            ),
            "set": _(
                "Usage: set <param>=<value>\n"
                "Modifies the current configuration.\n"
                "Example: 'set debug=true', 'set theme=dark'"
            ),
            "hint": _("Usage: hint\nAsks the engine for a move suggestion."),
            "pause": _("Usage: pause\nPauses the game timer (Blitz mode)."),
            "server": _(
                "Usage: server <list|start [port]|stop|status>\n"
                "Manages the local Othello server.\n"
                " - list : See available servers on the local network.\n"
                " - start : Starts a server on the given port (default "
                "12345).\n"
                " - stop : Stops the current running server.\n"
                " - status : Displays information about the current server "
                "state."
            ),
            "join": _(
                "Usage: join <ip:port> [id]\n"
                "Connect to an existing Othello server.\n"
                "Example: 'join 192.168.1.10:12345' or 'join bob' if bob "
                "was your previous ID."
            ),
            "ping": _(
                "Usage: ping\nTests the connection to the connected server."
            ),
            "players": _(
                "Usage: players or players [PLAYER_ID] for details\n"
                "Lists all players or shows details for a specific player.\n"
                "Details include status (idle, away, waitgame, ingame), "
                "score, and statistics."
            ),
            "scoreboard": _(
                "Usage: scoreboard\nDisplays the current scoreboard from "
                "the server."
            ),
            "name": _(
                "Usage: name <pseudo>\nChanges your player name on the server."
            ),
            "quit": _(
                "Usage: quit [force]\nExits the game or disconnects from "
                "server."
            ),
            "help": _(
                "Usage: help [command]\n"
                "Displays this list or details for a specific command."
            ),
            "accept": _("Usage: accept\nAccepts a pending game invitation."),
            "decline": _("Usage: decline\nRefuses a pending game invitation."),
            "cancel": _(
                "Usage: cancel\nCancels an invitation you have sent "
                "(if still pending)."
            ),
            "away": _(
                "Usage: away\nSets your status to 'away' "
                "(no invitations received)."
            ),
            "back": _("Usage: back\nSets your status back to 'idle'."),
            "waitgame": _(
                "Usage: waitgame\nDisplays your current search/invitation "
                "status."
            ),
        }

        if self.topic:
            if (topic_key := self.topic.lower()) in help_details:
                game_session.view.display_message(
                    _("\n--- Help: {topic_key} ---\n{details}").format(
                        topic_key=topic_key.upper(),
                        details=help_details[topic_key],
                    )
                )
            else:
                game_session.view.display_error(
                    _("No help available for command '{topic}'.").format(
                        topic=self.topic
                    )
                )
        else:
            msg = _(
                "Available commands (type 'help <CMD>' for details):\n"
                "---------------------------------------------------\n"
                " - Game      : new, load, save, quit\n"
                " - Play      : <Color> <Coord> (e.g. X E4), undo, redo, "
                "hint\n"
                " - Info      : show (board, history, time, configuration),\n"
                "              scoreboard, players, waitgame\n"
                " - Settings  : set, pause, name, away, back\n"
                " - Network   : join, server, ping, players, accept, "
                "decline, cancel\n"
                " - System    : help\n"
            )
            game_session.view.display_message(msg)
        return True


class SaveCommand(Command):
    """Command to save the game."""

    def __init__(self, filename: str | None, comment: str | None = None):
        """Initialize a save command.

        :param filename: Path to save file (None if not provided)
        :param comment: Optional comment to include in save file

        """
        self.filename = filename
        self.comment = comment

    def get_type(self) -> CommandType:
        return CommandType.SAVE

    def get_data(self) -> dict[str, Any]:
        return {"filename": self.filename, "comment": self.comment}

    def execute(self, game_session: "GameSession") -> bool:
        """Execute save command: save current game state to file.

        :return: True to continue the game
        """
        # Network Check
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            game_session.view.display_error(
                _(
                    "Cannot save game during a network match. "
                    "Finish or disconnect first."
                )
            )
            return True

        if self.filename:
            game_session.save_game(self.filename, self.comment)
        else:
            game_session.view.display_error(
                _("Usage: save <filename> [comment]")
            )
        return True  # Continue game


class LoadCommand(Command):
    """Command to load a saved game."""

    def __init__(self, filename: str | None):
        """Initialize a load command.

        :param filename: Path to file to load (None if not provided)

        """
        self.filename = filename

    def get_type(self) -> CommandType:
        return CommandType.LOAD

    def get_data(self) -> dict[str, Any]:
        return {"filename": self.filename}

    def execute(self, game_session: "GameSession") -> bool:
        """Execute load command: load game state from file.

        :return: True to continue the game
        """
        # Network Check
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            game_session.view.display_error(
                _("Cannot load game during a network match.")
            )
            return True

        if self.filename:
            if game_session.load_game(self.filename):
                game_session.view.display_message(
                    _("Game loaded from {filename}").format(
                        filename=self.filename
                    )
                )
        else:
            game_session.view.display_error(_("Usage: load <filename>"))

        return True  # Continue game


class UndoCommand(Command):
    """Command to undo move."""

    def __init__(self, n_moves: str = "1"):
        """Initialize an undo command.

        :param n_moves: Number of moves to undo.

        """
        self.n_moves = int(n_moves) if n_moves.isdigit() else 1

    def get_type(self) -> CommandType:
        return CommandType.UNDO

    def get_data(self) -> dict[str, Any]:
        return {"n_moves": self.n_moves}

    def execute(self, game_session: "GameSession") -> bool:
        """Execute undo command: Undo moves.

        :return: True to continue the game.
        """
        # Network Check
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            game_session.view.display_error(
                _("Undo is not available in network mode.")
            )
            return True

        if game_session.undo_move(self.n_moves):
            game_session.view.display_message(
                _("Undid {n} move(s).").format(n=self.n_moves)
            )
        return True


class RedoCommand(Command):
    """Command to redo move."""

    def __init__(self, n_moves: str = "1"):
        """Initialize a redo command.

        :param n_moves: Number of moves to redo.

        """
        self.n_moves = int(n_moves) if n_moves.isdigit() else 1

    def get_type(self) -> CommandType:
        return CommandType.REDO

    def get_data(self) -> dict[str, Any]:
        return {"n_moves": self.n_moves}

    def execute(self, game_session: "GameSession") -> bool:
        """Execute redo command: redo moves.

        :return: True to continue the game.
        """
        # Network Check
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            game_session.view.display_error(
                _("Redo is not available in network mode.")
            )
            return True

        if game_session.redo_move(self.n_moves):
            game_session.view.display_message(
                _("Redid {n} move(s).").format(n=self.n_moves)
            )
        return True


class NewCommand(Command):
    """Command to start a new game with configurable parameters."""

    def __init__(self, args: list[str]):
        """Initialize a new command.

        :param args: List of args.

        """
        self.args = args

    def get_type(self) -> CommandType:
        return CommandType.NEW

    def get_data(self) -> dict[str, Any]:
        return {"args": self.args}

    def execute(self, game_session: "GameSession") -> bool:
        # Check if connected to a network lobby first
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            if not self.args or len(self.args) != 1:
                game_session.view.display_error(
                    _("Usage in Lobby: new <player_id>")
                )
                return True
            game_session.game_client.send_message(f"NEW {self.args[0]}")
            return True

        config = ConfigManager()

        if self.args:  # Only parse args if they are provided (CLI)
            parser = ArgParser()
            try:
                parser.parse(self.args)
            except SystemExit:
                return True
            except Exception as error:
                game_session.view.display_error(
                    _("Error parsing arguments: {error}").format(error=error)
                )
                return True

        new_options = dict(config.config_parser["defaults"])
        msg_parts = [_("Starting new game...")]
        if "size" in new_options:
            msg_parts.append(
                _("Size: {size}").format(size=new_options["size"])
            )

        if new_options.get("ai_enabled", "").lower() == "true":
            color = new_options.get("ai_color", "?")
            msg_parts.append(_("Mode: vs AI ({color})").format(color=color))

        if new_options.get("blitz", "").lower() == "true":
            msg_parts.append(_("Mode: Blitz"))

        if new_options.get("contest", "").lower() == "true":
            msg_parts.append(_("Mode: Contest"))

        game_session.view.display_message(" ".join(msg_parts))
        game_session.reset_game(new_options)
        return True


class PauseCommand(Command):
    """Command to pause timers."""

    def get_type(self) -> CommandType:
        return CommandType.PAUSE

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        if hasattr(game_session, "blitz_mode") and game_session.blitz_mode:
            game_session.blitz_mode.pause()
        else:
            game_session.view.display_error(_("Can pause only in Blitz."))
        return True


class HintCommand(Command):
    """Command to ask a hint."""

    def get_type(self) -> CommandType:
        return CommandType.HINT

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        is_network_mode = (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        )
        if is_network_mode:
            game_session.view.display_error(
                _("AI commands are not available in network mode.")
            )
            return True

        board = (
            game_session.game_state.white_board,
            game_session.game_state.black_board,
        )
        # TODO(Remi) : use minimax or other algorithm to get an actual
        # hint (not implemented yet)
        move = get_advice(
            board, AIPlayer.random_move, game_session.current_player
        )
        game_session.view.display_message(
            _("Hint: {move} seems like a good move.").format(move=move)
        )
        return True


class ShowCommand(Command):
    """Command to show things."""

    def __init__(self, target: str):
        self.target = target.lower()

    def get_type(self) -> CommandType:
        return CommandType.SHOW

    def get_data(self) -> dict[str, Any]:
        return {"target": self.target}

    def execute(self, game_session: "GameSession") -> bool:
        is_network_mode = (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        )
        is_in_match = is_network_mode and any(
            type(p).__name__ == "NetworkPlayer"
            for p in game_session.players.values()
        )
        if (
            is_network_mode
            and not is_in_match
            and self.target in ("history", "time")
        ):
            game_session.view.display_error(_("You are not in a game."))
            return True

        if self.target == "board":
            if game_session.current_player == "X":
                legal_moves = GameRules.get_legal_moves(
                    game_session.game_state.black_board,
                    game_session.game_state.white_board,
                )
            else:
                legal_moves = GameRules.get_legal_moves(
                    game_session.game_state.white_board,
                    game_session.game_state.black_board,
                )
            game_session.view.render(
                game_session.game_state.get_board_as_string(),
                legal_moves,
                game_session.current_player,
                game_session.unsaved_changes,
            )
        elif self.target == "history":
            if not (hist := game_session.history):
                game_session.view.display_message(_("History empty."))
            else:
                formatted_history = [_("[History]\n")]
                i = 0
                while i < len(hist):
                    move1 = hist[i]
                    if (i + 1) < len(hist) and hist[i][0].upper() != hist[
                        i + 1
                    ][0].upper():
                        move2 = hist[i + 1]
                        formatted_history.append(f"{move1} {move2}")
                        i += 2
                    else:
                        # Le tour est incomplet ou le joueur suivant a passé
                        formatted_history.append(f"{move1}")
                        i += 1

                game_session.view.display_message("\n".join(formatted_history))
        elif self.target == "time":
            if hasattr(game_session, "blitz_mode") and game_session.blitz_mode:
                time_x = game_session.blitz_mode.remaining_time["X"]
                time_o = game_session.blitz_mode.remaining_time["O"]
                mins_x, secs_x = divmod(max(0, int(time_x)), 60)
                mins_o, secs_o = divmod(max(0, int(time_o)), 60)

                status = (
                    _(" (Paused)") if game_session.blitz_mode.is_paused else ""
                )
                game_session.view.display_message(
                    _(
                        "Remaining Time{status} : "
                        "X ({mx:02d}:{sx:02d})- O ({mo:02d}:{so:02d})"
                    ).format(
                        status=status,
                        mx=mins_x,
                        sx=secs_x,
                        mo=mins_o,
                        so=secs_o,
                    )
                )
            else:
                game_session.view.display_error(_("Blitz is not enabled."))
        elif self.target == "configuration":
            config = ConfigManager()
            defaults = config.config_parser["defaults"]
            lines = [_("=== Current Configuration ===")]
            for key, value in defaults.items():
                lines.append(f"{key} = {value}")
            game_session.view.display_message("\n".join(lines))
        else:
            game_session.view.display_error(
                _("Unknown show target: {target}").format(target=self.target)
            )
        return True


class SetCommand(Command):
    """Command to change configuration."""

    def __init__(self, param: str, value: str):
        self.param = param
        self.value = value

    def get_type(self) -> CommandType:
        return CommandType.SET

    def get_data(self) -> dict[str, Any]:
        return {"param": self.param, "value": self.value}

    def execute(self, game_session: "GameSession") -> bool:
        config = ConfigManager()

        is_network_mode = (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        )
        forbidden_in_network = [
            "size",
            "ai_enabled",
            "ai_color",
            "ai_mode",
            "ai_mcts_selection",
            "ai_minimax_depth",
            "ai_minimax_scoring",
            "blitz",
            "time",
        ]
        if is_network_mode and self.param in forbidden_in_network:
            game_session.view.display_error(
                _(
                    "Cannot change game rules or AI settings while "
                    "connected to a server."
                )
            )
            return True

        if self.param == "size":
            game_session.view.display_error(
                _(
                    "Can't change the size during a game.\n"
                    "End the game or use 'new size=...'"
                )
            )
            return True
        if config._validate_single_option(self.param, self.value):
            config.set(self.param, self.value)

            game_session.view.display_message(
                _("Configuration updated: {param} = {value}").format(
                    param=self.param, value=self.value
                )
            )

        else:
            # En cas d'erreur, ConfigManager affiche le détail sur stderr
            game_session.view.display_error(
                _(
                    "Invalid value for '{param}'. check 'help set' or logs."
                ).format(param=self.param)
            )
        return True


class ServerCommand(Command):
    """Command to manage the local server (list, start, stop)."""

    def __init__(self, action: str, port: str = "12345"):
        """Initialize server command.

        :param action: The action to perform (list, start, stop).
        :param port: The target port for starting the server.
        """
        self.action = action.lower()
        self.port = port

    def get_type(self) -> CommandType:
        return CommandType.SERVER

    def get_data(self) -> dict[str, Any]:
        return {"action": self.action, "port": self.port}

    def execute(self, game_session: "GameSession") -> bool:
        if self.action == "list":
            if not getattr(game_session, "discovery_service", None):
                game_session.view.display_error(
                    _("Background discovery service not initialized.")
                )
                return True

            servers = game_session.discovery_service.get_server_list()
            is_gui = "GUIApp" in str(type(game_session.view))

            if is_gui:
                game_session.view.output_queue.put(
                    ("discovered_servers", servers)
                )
            else:
                if not servers:
                    game_session.view.display_message(
                        _("No servers found (listening in background...).")
                    )
                else:
                    game_session.view.display_message(
                        _("Found {count} server(s):").format(
                            count=len(servers)
                        )
                    )
                    for s in servers:
                        game_session.view.display_message(f" - {s}")
        elif self.action == "start":
            if (
                game_session.game_server
                and game_session.game_server.is_running
            ):
                game_session.view.display_error(
                    _("Server is already running.")
                )
                return True

            port = int(self.port)
            is_gui = "GUIApp" in str(type(game_session.view))

            log_queue = game_session.server_log_queue if is_gui else None
            game_session.game_server = GameServer(
                port=port, log_queue=log_queue
            )
            game_session.game_server.start_server(
                is_daemon=True
            )  # Run in background for GUI

            if not is_gui:
                game_session.view.display_message(
                    _(
                        "Custom server started on TCP port {port}. "
                        "Press Ctrl+C to stop."
                    ).format(port=port)
                )
                game_session.server_command_loop()
                return False  # End session after server loop

        elif self.action == "stop":
            if game_session.game_server:
                game_session.game_server.stop_server()
                game_session.game_server = None
                game_session.view.display_message(_("Server stopped."))
            else:
                game_session.view.display_error(_("No server running."))
        else:
            game_session.view.display_error(
                _("Unknown server action: {action}").format(action=self.action)
            )
            game_session.view.display_message(
                _("Usage: server <list|start [port]|stop>")
            )
        return True


class JoinCommand(Command):
    """Command to join a server."""

    def __init__(self, target: str = "127.0.0.1:12345", client_id: str = None):
        """Initialize join command.

        :param target: Server address (IP:PORT format).
        :param client_id: Optional custom player ID to use.
        """
        self.target = target
        self.client_id = client_id

    def get_type(self) -> CommandType:
        return CommandType.JOIN

    def get_data(self) -> dict[str, Any]:
        return {"target": self.target}

    def execute(self, game_session: "GameSession") -> bool:
        # string parsing -> can be name@ip:port or ip:port
        target = self.target
        if "@" in target:
            target = target.split("@")[1]

        parts = target.split(":")
        ip = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 12345

        # Priority: use specific client_id if provided (e.g. join bob),
        # otherwise use the one from the existing/previous client (alice),
        # otherwise use the last known successful ID.
        active_id = None
        if getattr(game_session, "game_client", None):
            active_id = game_session.game_client.client_id
            if game_session.game_client.is_connected:
                game_session.game_client.quit()

        game_session.game_client = GameClient(ip=ip, port=port)

        if self.client_id:
            game_session.game_client.client_id = self.client_id
        elif active_id:
            game_session.game_client.client_id = active_id
        elif getattr(game_session, "last_client_id", None):
            game_session.game_client.client_id = game_session.last_client_id

        game_session.game_client.game_session = game_session
        is_gui = "GUIApp" in str(type(game_session.view))

        if game_session.game_client.join():
            if is_gui:
                game_session.view.display_message(
                    _("Successfully connected to the server.")
                )
                game_session.view.output_queue.put(("show_lobby", None))
            else:
                # CLI mode enters a blocking lobby loop here
                game_session.view.display_message(
                    _(
                        "Successfully connected to the server. "
                        "Type 'players' or 'new <ids>' to interact ."
                    )
                )

            # RESET SESSION: Force return to Lobby state
            # (removes old NetworkPlayers)
            # This fixes the message queue offset/lag issue.
            game_session.reset_game({})
            return True
        else:
            game_session.game_client = None
            game_session.view.display_error(_("Could not join server."))
            return True


class PingCommand(Command):
    """Command to ping the connected server."""

    def get_type(self) -> CommandType:
        return CommandType.PING

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        if game_session.game_client and game_session.game_client.is_connected:
            game_session.game_client.ping()
            game_session.view.display_message(_("Ping requested."))

            start_time = time.time()
            try:
                # Wait up to 2 seconds for a PONG response
                end_time = start_time + 2.0
                non_pongs = []
                found_pong = None

                while time.time() < end_time:
                    try:
                        msg = game_session.game_client.message_queue.get(
                            timeout=0.1
                        )
                        if msg.startswith("PONG"):
                            found_pong = msg
                            break
                        else:
                            non_pongs.append(msg)
                    except queue.Empty:
                        continue

                # Re-queue the non-pong messages
                for m in non_pongs:
                    game_session.game_client.message_queue.put(m)

                if found_pong:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    game_session.view.display_message(
                        _("Server reply: PONG TIME={ms}ms").format(
                            ms=elapsed_ms
                        )
                    )
                else:
                    game_session.view.display_error(
                        _("Ping timeout: No response from server.")
                    )
            except Exception as e:
                game_session.view.display_error(
                    _("Ping Error: {error}").format(error=e)
                )
        else:
            game_session.view.display_error(
                _("Not connected to a server. Try 'join' first.")
            )
        return True


class ServerStatusCommand(Command):
    """Command to request detailed status information from the server."""

    def get_type(self) -> CommandType:
        return CommandType.SERVER_STATUS

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        # Priorité au client réseau
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            game_session.game_client.send_message("SERVER_STATUS")

            end_time = time.time() + 1.0
            while time.time() < end_time:
                try:
                    msg = game_session.game_client.message_queue.get(
                        timeout=0.05
                    )
                    if msg.startswith("SERVER_STATUS "):
                        game_session.handle_network_message(msg)
                        break
                    else:
                        # Re-queue other messages
                        game_session.game_client.message_queue.put(msg)
                        time.sleep(
                            0.01
                        )  # Avoid tight loop if same msg keeps popping
                except queue.Empty:
                    continue
        # 2. Fallback pour l'administration pure du serveur
        elif hasattr(game_session, "game_server") and game_session.game_server:
            game_session.view.display_message(
                game_session.game_server.get_server_status()
            )
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class PlayersCommand(Command):
    """Command to request the list of connected players from the server.

    If a player ID is provided, requests detailed info about that player.
    """

    def __init__(self, player_id: str = None):
        """Initialize players command.

        :param player_id: Optional ID of a specific player to query.
        """
        self.player_id = player_id

    def get_type(self) -> CommandType:
        return CommandType.PLAYERS

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        is_gui = "GUIApp" in str(type(game_session.view))

        # priority to network client for up-to-date info and details
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            msg = "PLAYERS"
            if self.player_id:
                msg += f" {self.player_id}"
            game_session.game_client.send_message(msg)

            if not is_gui:
                # CLI Sync Wait: wait for the list header and some entries

                end_time = time.time() + 1.0
                while time.time() < end_time:
                    try:
                        msg = game_session.game_client.message_queue.get(
                            timeout=0.05
                        )
                        if msg.startswith("PLAYERS_LIST"):
                            game_session.handle_network_message(msg)
                            if (
                                "Connected Players:" in msg
                                or "--- Player Info:" in msg
                            ):
                                end_time = time.time() + 0.3
                        else:
                            game_session.game_client.message_queue.put(msg)
                            time.sleep(0.01)
                    except queue.Empty:
                        continue

        # 2. Fallback pour l'administration pure du serveur
        elif hasattr(game_session, "game_server") and game_session.game_server:
            player_list_str = (
                game_session.game_server.player_manager._get_players_list(
                    self.player_id
                )
            )
            if is_gui:
                lines = player_list_str.strip().split("\n")
                player_data = [
                    line.replace("PLAYERS_LIST - ", "")
                    for line in lines
                    if line.startswith("PLAYERS_LIST - ")
                ]
                game_session.view.output_queue.put(
                    ("player_list", player_data)
                )
            else:
                game_session.view.display_message(player_list_str)
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class AcceptCommand(Command):
    """Command to accept a pending game invitation."""

    def get_type(self) -> CommandType:
        return CommandType.ACCEPT

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        if game_session.game_client and game_session.game_client.is_connected:
            game_session.game_client.send_message("ACCEPT")
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class DeclineCommand(Command):
    """Command to decline a pending game invitation."""

    def get_type(self) -> CommandType:
        return CommandType.DECLINE

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        if game_session.game_client and game_session.game_client.is_connected:
            game_session.game_client.send_message("DECLINE")
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class CancelCommand(Command):
    """Command to cancel an outgoing game invitation."""

    def get_type(self) -> CommandType:
        return CommandType.CANCEL

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        if game_session.game_client and game_session.game_client.is_connected:
            game_session.game_client.send_message("CANCEL")
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class AwayCommand(Command):
    """Command to set the player status to away."""

    def get_type(self) -> CommandType:
        return CommandType.AWAY

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        if game_session.game_client and game_session.game_client.is_connected:
            game_session.game_client.send_message("AWAY")
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class BackCommand(Command):
    """Command to set the player status back to idle from away."""

    def get_type(self) -> CommandType:
        return CommandType.BACK

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        if game_session.game_client and game_session.game_client.is_connected:
            game_session.game_client.send_message("BACK")
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class WaitgameCommand(Command):
    """Command to request the current invitation or challenge status."""

    def get_type(self) -> CommandType:
        return CommandType.WAITGAME

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        if game_session.game_client and game_session.game_client.is_connected:
            game_session.game_client.send_message("WAITGAME")
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class ScoreboardCommand(Command):
    """Command to request the global scoreboard from the server."""

    def get_type(self) -> CommandType:
        return CommandType.SCOREBOARD

    def get_data(self) -> dict[str, Any]:
        return {}

    def execute(self, game_session: "GameSession") -> bool:
        # Priorité au client réseau
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            game_session.game_client.send_message("SCOREBOARD")

            if "GUIApp" not in str(type(game_session.view)):
                # CLI Sync Wait

                end_time = time.time() + 1.0
                while time.time() < end_time:
                    try:
                        msg = game_session.game_client.message_queue.get(
                            timeout=0.05
                        )
                        if msg.startswith("SCOREBOARD "):
                            game_session.handle_network_message(msg)
                            break
                        else:
                            game_session.game_client.message_queue.put(msg)
                            time.sleep(0.01)
                    except queue.Empty:
                        continue

        # Fallback pour l'administration du serveur
        elif hasattr(game_session, "game_server") and game_session.game_server:
            game_session.view.display_message(
                game_session.game_server.player_manager._get_scoreboard()
            )
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class NewGameRemoteCommand(Command):
    """Command to challenge a specific player to a new game."""

    def __init__(self, target_id: str):
        """Initialize new game remote command.

        :param target_id: ID of the player to challenge.
        """
        self.target_id = target_id

    def get_type(self) -> CommandType:
        return CommandType.NEW

    def get_data(self) -> dict[str, Any]:
        return {"target": self.target_id}

    def execute(self, game_session: "GameSession") -> bool:
        if game_session.game_client and game_session.game_client.is_connected:
            game_session.game_client.send_message(f"NEW {self.target_id}")
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class NameCommand(Command):
    """Command to change the player's name/pseudo on the server."""

    def __init__(self, pseudo: str):
        """Initialize name command.

        :param pseudo: The new name/pseudo requested.
        """
        self.pseudo = pseudo

    def get_type(self) -> CommandType:
        return CommandType.NAME

    def get_data(self) -> dict[str, Any]:
        return {"pseudo": self.pseudo}

    def execute(self, game_session: "GameSession") -> bool:
        if (
            getattr(game_session, "game_client", None)
            and game_session.game_client.is_connected
        ):
            game_session.game_client.send_message(f"NAME {self.pseudo}")

            if "GUIApp" not in str(type(game_session.view)):
                end_time = time.time() + 1.0
                while time.time() < end_time:
                    try:
                        msg = game_session.game_client.message_queue.get(
                            timeout=0.05
                        )
                        if msg.startswith("NAME_OK ") or msg.startswith(
                            "ERROR "
                        ):
                            game_session.handle_network_message(msg)
                            break
                        else:
                            game_session.game_client.message_queue.put(msg)
                            time.sleep(0.01)
                    except queue.Empty:
                        continue
        else:
            game_session.view.display_error(_("Not connected to a server."))
        return True


class CommandParser:
    """Utility class to parse string input into Command objects.

    Used primarily by CLI to convert user input strings into commands.
    GUI implementations would create Command objects directly
    from UI events.

    """

    @staticmethod
    def parse(input_str: str) -> Command:
        """Command Parser.

        :param input_str: The string to parse.
        :return: The Command to execute

        """
        if not (parts := input_str.strip().split()):
            return MoveCommand("")

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "quit":
            force = len(args) > 0 and args[0].lower() == "force"
            return QuitCommand(force=force)
        elif cmd == "help":
            return HelpCommand(args[0] if args else None)
        elif cmd == "new":
            return NewCommand(args)
        elif cmd == "pause":
            return PauseCommand()
        elif cmd == "hint":
            return HintCommand()
        elif cmd == "show":
            if not args:
                return HelpCommand("show")  # Fallback
            return ShowCommand(args[0])
        elif cmd == "history":
            return ShowCommand("history")
        elif cmd in ("config", "configuration"):
            return ShowCommand("configuration")
        elif cmd == "set":
            # Expect set param=value
            if args and "=" in args[0]:
                param, val = args[0].split("=", 1)
                return SetCommand(param, val)
            return HelpCommand("set")
        elif cmd == "save":
            filename = args[0] if args else None
            comment = " ".join(args[1:]) if len(args) > 1 else None
            return SaveCommand(filename, comment)
        elif cmd == "load":
            return LoadCommand(args[0] if args else None)
        elif cmd == "undo":
            return UndoCommand(args[0] if args else "1")
        elif cmd == "redo":
            return RedoCommand(args[0] if args else "1")
        elif cmd == "server":
            action = args[0] if args else "list"
            if action == "status":
                return ServerStatusCommand()
            port = args[1] if len(args) > 1 else "12345"
            return ServerCommand(action, port)
        elif cmd == "join":
            target = "127.0.0.1:12345"
            client_id = None
            if args:
                if ":" in args[0] or "." in args[0] or args[0] == "localhost":
                    target = args[0]
                    if len(args) > 1:
                        client_id = args[1]
                else:
                    client_id = args[0]
                    if len(args) > 1:
                        target = args[1]
            return JoinCommand(target, client_id)
        elif cmd == "ping":
            return PingCommand()
        elif cmd == "players":
            return PlayersCommand(args[0] if args else None)
        elif cmd == "accept":
            return AcceptCommand()
        elif cmd == "decline":
            return DeclineCommand()
        elif cmd == "cancel":
            return CancelCommand()
        elif cmd == "away":
            return AwayCommand()
        elif cmd == "back":
            return BackCommand()
        elif cmd == "waitgame":
            return WaitgameCommand()
        elif cmd == "scoreboard":
            return ScoreboardCommand()
        elif cmd == "server" and len(args) > 0 and args[0] == "status":
            return ServerStatusCommand()
        elif cmd == "name" and args:
            return NameCommand(args[0])

        # Default fallback to move
        return MoveCommand(input_str)
