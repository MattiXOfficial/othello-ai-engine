"""Game session Module."""

import os
import queue
import re
import select
import sys
import threading
import time

from othello.common.command import CommandParser
from othello.common.command import ShowCommand
from othello.common.config_manager import ConfigManager
from othello.common.i18n_manager import I18nManager
from othello.game_engine.game_rules import GameRules
from othello.game_engine.game_state import GameState
from othello.network.discovery_service import DiscoveryService
from othello.orchestrator.bitboard_ops import BitboardOps
from othello.orchestrator.blitz_controller import BlitzMode
from othello.player.ai_player import AIPlayer
from othello.player.network_player import NetworkPlayer
from othello.player.real_player import RealPlayer
from othello.user_interface.interface_view import InterfaceView


def _(message):
    return I18nManager().gettext(message)


class GameSession:
    """GameSession Class."""

    SAVES_DIR = "game_saves"

    def __init__(self, view: InterfaceView):
        """Initialize the game session, state, and view.

        :param view: The view instance (CLI or GUI) to use for rendering
        and input.

        """
        self.game_state = GameState()
        self.view = view
        self.current_player = "X"  # Blacks start
        self.unsaved_changes = False
        self.discovery_service = DiscoveryService("ClientScanner")
        self.discovery_service.start_listening()
        self.server_log_queue = queue.Queue()

        # we intercept log for send directly to GUI interface
        def _instant_log(msg, block=True, timeout=None):
            if hasattr(self.view, "output_queue"):
                self.view.output_queue.put(("server_log", msg))
            else:
                self.view.display_message(msg)

        self.server_log_queue.put = _instant_log
        # --------------------------------------

        # History stacks
        self.history = []
        self.undo_stack = []
        self.redo_stack = []

        config = ConfigManager().config_parser["defaults"]
        self.settings = dict(config)
        input_file = self.settings.get("input_file")

        loaded = False
        if input_file:
            # Try to load the file specified in arguments
            if self.load_game(input_file):
                loaded = True
            else:
                self.view.display_error(
                    _("Could not load {file}. Starting default game.").format(
                        file=input_file
                    )
                )

        if not loaded:
            self.game_state.initialize_default()

        self._setup_players()
        # Blitz Mode
        self.blitz_mode = None
        if self.settings.get("blitz") == "true":
            timeout = int(self.settings.get("timeout", 30))
            self.blitz_mode = BlitzMode(timeout, self._on_blitz_timeout)
        # Contest Mode

    def _setup_players(self):
        """Setup players (real or AI) based on current configuration."""
        config = ConfigManager().config_parser["defaults"]
        ai_enabled = config.get("ai_enabled", "false").lower() == "true"
        ai_color = config.get("ai_color", "")

        self.players = {"X": RealPlayer("X"), "O": RealPlayer("O")}

        # helps not clearing the game when called by game_reset
        if not hasattr(self, "game_server"):
            self.game_server = None
        if not hasattr(self, "game_client"):
            self.game_client = None

        if ai_enabled:
            if ai_color == "A":
                self.players["X"] = AIPlayer("X")
                self.players["O"] = AIPlayer("O")
                self.view.display_message(
                    _("Both players (Black and White) are AI.")
                )
            elif ai_color == "b":
                self.players["X"] = AIPlayer("X")
                self.view.display_message(_("Black player (X) is an AI."))
            elif ai_color == "w":
                self.players["O"] = AIPlayer("O")
                self.view.display_message(_("White player (O) is an AI."))

    def load_default_board(self, size=8):
        """Initialize the board with 4 pieces in the center."""
        self.game_state.black_board = 0
        self.game_state.white_board = 0
        size = BitboardOps.SIZE
        mid = size // 2

        tl_index = (mid - 1) * size + (mid - 1)
        tr_index = (mid - 1) * size + mid
        bl_index = mid * size + (mid - 1)
        br_index = mid * size + mid

        # Blacks
        self.game_state.black_board = BitboardOps.set_token(
            self.game_state.black_board, tl_index
        )
        self.game_state.black_board = BitboardOps.set_token(
            self.game_state.black_board, br_index
        )

        # Whites
        self.game_state.white_board = BitboardOps.set_token(
            self.game_state.white_board, tr_index
        )
        self.game_state.white_board = BitboardOps.set_token(
            self.game_state.white_board, bl_index
        )

    def _on_blitz_timeout(self, player_color):
        """Callback déclenché par le thread du Blitz quand le temps est à 0."""
        # interupt IA if it's currently thinking
        player_obj = self.players.get(player_color)
        if hasattr(player_obj, "stop_event"):
            player_obj.stop_event.set()

        self.pending_timeout = player_color

        if hasattr(self.view, "input_queue"):
            self.view.input_queue.put(f"__TIMEOUT__ {player_color}")
        else:
            self.view.display_message(
                _("\nNo Time left! {color} loses. Press enter...").format(
                    color=player_color
                )
            )

    def reset_game(self, options: dict[str, str] = None):
        """Resets the game state with new configuration options.

        :param options: Dictionary of options (e.g., {'size': '10'})

        """
        if options is None:
            options = {}

        if options and "size" in options:
            new_size = int(options["size"])
            BitboardOps.set_board_size(new_size)

        self.game_state = GameState()
        self.game_state.initialize_default()
        self.history = []
        self.undo_stack = []
        self.redo_stack = []
        self.unsaved_changes = False
        self.current_player = "X"
        self._lobby_prompt_active = False  # Reset prompt state
        self.network_opponent = None

        if "GUIApp" in str(type(self.view)):
            if (
                getattr(self, "game_client", None)
                and self.game_client.is_connected
            ):
                self.view.output_queue.put(
                    ("set_network_status", "[Online] Lobby")
                )
            else:
                self.view.output_queue.put(("set_network_status", None))

        if hasattr(self, "blitz_mode") and self.blitz_mode:
            self.blitz_mode.stop()

        blitz_active = str(options.get("blitz", "false")).lower() == "true"
        if blitz_active:
            time_limit = float(options.get("timeout", 30.0))
            self.blitz_mode = BlitzMode(time_limit, self._on_blitz_timeout)
        else:
            self.blitz_mode = None

        if hasattr(self, "blitz_mode") and self.blitz_mode:
            self.blitz_mode.start()

        self._setup_players()
        self.view.display_message(_("New game started."))

    def save_game(self, filename: str, comment: str = None) -> bool:
        """Save the game state in an ASCII file.

        :param filename: Path to the save file.
        :param comment: Optional comment to add at the top of the file.

        """
        try:
            os.makedirs(self.SAVES_DIR, exist_ok=True)
            filepath = os.path.join(self.SAVES_DIR, filename)
            current_config = ConfigManager().config_parser["defaults"]
            self.settings.update(dict(current_config))
            self.settings["size"] = str(BitboardOps.SIZE)
            with open(filepath, "w", encoding="utf-8") as file:
                file.write("[settings]\n")
                if comment:
                    file.write(f"# {comment}\n")
                for key, value in self.settings.items():
                    file.write(f"{key}={value}\n")
                file.write("\n")

                self._save_game_state(file)
                file.write("\n")

                self._save_history(file)

            self.view.display_message(
                _("Game saved successfully to {path}").format(path=filepath)
            )
            self.unsaved_changes = False
            return True

        except IOError as error:
            self.view.display_error(
                _("Error saving game: {error}").format(error=error)
            )
            return False

    def _save_game_state(self, file):
        """Write the game section in a file."""
        file.write("[game]\n")
        file.write(f"{self.current_player}\n")
        size = BitboardOps.SIZE
        black_bb = self.game_state.black_board
        white_bb = self.game_state.white_board
        for row in range(size):
            rows = []
            for col in range(size):
                index = row * size + col
                if BitboardOps.get_token(black_bb, index):
                    rows.append("X")
                elif BitboardOps.get_token(white_bb, index):
                    rows.append("O")
                else:
                    rows.append("_")
            file.write(" ".join(rows) + "\n")
        b_count = BitboardOps.popcount(black_bb)
        w_count = BitboardOps.popcount(white_bb)
        file.write(f"X-captures: {b_count}\n")
        file.write(f"O-captures: {w_count}\n")

    def _save_history(self, file):
        """Write the history section in a file."""
        file.write("[history]\n")
        i = 0
        while i < len(self.history):
            move1 = self.history[i]
            move2 = self.history[i + 1] if (i + 1) < len(self.history) else ""
            if move2 and move1[0] == move2[0]:
                # Cas tour passé
                file.write(f"{move1}\n")
                i += 1
            else:
                file.write(f"{move1} {move2}".strip() + "\n")
                i += 2

    def load_game(self, filename: str) -> bool:
        """Load a game state from a file and update the session.

        :param filename: The path to the file.
        :return: True if loading was successful, False otherwise.

        """
        filepath = os.path.join(self.SAVES_DIR, filename)
        if not os.path.exists(filepath):
            self.view.display_error(
                _("File not found: {path}").format(path=filepath)
            )
            return False

        try:
            if not (lines := self._read_clean_lines(filepath)):
                self.view.display_error(_("File is empty or invalid."))
                return False

            sections = self._extract_sections(lines)
            if not all(k in sections for k in ["settings", "game"]):
                self.view.display_error(
                    _(
                        "Invalid file format: Missing "
                        "[settings] or [game] section."
                    )
                )
                return False

            if not self._parse_settings(sections["settings"]):
                return False

            if not self._parse_game_state(sections["game"]):
                return False

            if "history" in sections:
                self._parse_history(sections["history"])

            self.view.display_message(
                _("Game loaded from {path}").format(path=filepath)
            )
            return True

        except Exception as e:
            self.view.display_error(
                _("Error loading game: {error}").format(error=e)
            )
            return False

    def _extract_sections(self, lines: list[str]) -> dict[str, list[str]]:
        """Extracts sections from a list of cleaned lines from a save file.

        :param lines: A list of strings, where each string is a line
            from the file.
        :return: A dictionary mapping section names to a list of lines
        in that section.

        """
        sections = {}
        current_section_name = None
        for line in lines:
            if line.startswith("[") and line.endswith("]"):
                current_section_name = line[1:-1].lower()
                sections[current_section_name] = []
            elif current_section_name:
                sections[current_section_name].append(line)
        return sections

    def _parse_settings(self, settings_lines: list[str]) -> bool:
        """Parse the [settings] section and update config."""
        config_manager = ConfigManager()
        for line in settings_lines:
            if "=" in line:
                key, value = line.split("=", 1)
                config_manager.set(key.strip(), value.strip())

        # After loading settings, especially size, update BitboardOps
        new_size_str = config_manager.config_parser.get(
            "defaults", "size", fallback="8"
        )
        if (new_size := int(new_size_str)) != BitboardOps.SIZE:
            self.view.display_message(
                _("Loaded board size is {size}.").format(size=new_size)
            )
            BitboardOps.set_board_size(new_size)

        self.settings = dict(config_manager.config_parser["defaults"])
        return True

    def _parse_game_state(self, game_lines: list[str]) -> bool:
        """Parse the [game] section and update the game state."""
        if not game_lines:
            self.view.display_error(
                _("Invalid save file: [game] section is empty.")
            )
            return False

        # First line is the current player
        if (current_player := game_lines[0].strip().upper()) not in ("X", "O"):
            self.view.display_error(
                _("Invalid player '{player}' in save file.").format(
                    player=current_player
                )
            )
            return False

        self.current_player = current_player

        # The rest of the lines are the board, until the capture counts
        board_lines = []
        for line in game_lines[1:]:
            if "captures:" in line:
                break
            board_lines.append(line)

        loaded_size = len(board_lines)
        if loaded_size not in (6, 8, 10, 12):
            self.view.display_error(
                _("Invalid board size '{size}' in save file.").format(
                    size=loaded_size
                )
            )
            return False

        if loaded_size != BitboardOps.SIZE:
            self.view.display_message(
                _("Loaded board size is {size}.").format(size=loaded_size)
            )
            BitboardOps.set_board_size(loaded_size)

        black_bb = 0
        white_bb = 0
        for r, row_str in enumerate(board_lines):
            row_items = row_str.replace(" ", "")
            if len(row_items) != loaded_size:
                self.view.display_error(
                    _("Inconsistent row length at row {row}.").format(
                        row=r + 1
                    )
                )
                return False
            for c, char in enumerate(row_items):
                index = r * loaded_size + c
                if char == "X":
                    black_bb |= 1 << index
                elif char == "O":
                    white_bb |= 1 << index

        self.game_state.black_board = black_bb
        self.game_state.white_board = white_bb

        # Reset history for the new game state
        self.history = []
        self.undo_stack = []
        self.redo_stack = []
        self.unsaved_changes = False

        return True

    def _parse_history(self, history_lines: list[str]):
        """Parse history lines and populate the history list."""
        try:
            self.game_state = GameState()
            self.game_state.initialize_default()
            self.current_player = "X"
            self.history = []
            self.undo_stack = []
            self.redo_stack = []
            move_pattern = re.compile(r"([XxOo]\s+[a-zA-Z]\d+)")
            moves_to_play = []

            for line in history_lines:
                found_moves = move_pattern.findall(line)
                for move in found_moves:
                    parts = move.split()
                    normalized_move = f"{parts[0].upper()} {parts[1].lower()}"
                    moves_to_play.append(normalized_move)

            # On REJOUE chaque coup un par un pour mettre à jour le plateau
            for move_str in moves_to_play:
                move_color = move_str.split()[0]

                # --- SYNCHRONISATION (Correction du bug "Passe ton tour") ---
                # If the history shows that it's X's turn, we force
                # the game to X.
                # This handles cases where a player had to pass their turn.
                if self.current_player != move_color:
                    self.current_player = move_color

                # On exécute le coup "pour de vrai" via le CommandParser
                command = CommandParser.parse(move_str)
                if not command.execute(self):
                    self.view.display_error(
                        _("Error: Cannot replay move {move}").format(
                            move=move_str
                        )
                    )
                    return False
            return True
        except Exception as error:
            self.view.display_error(
                _("Critical error reading history: {error}").format(
                    error=error
                )
            )
            return False

    def command_loop(self):
        """Main game loop managing interaction between View and Model.

        Uses Command pattern to handle user input uniformly. Commands execute
        themselves with the game session as context.

        """

        is_running = True

        # Blitz Mode
        if self.blitz_mode:
            self.blitz_mode.start()

        while is_running:
            # ── Interception of GUI commands between polls ──
            # In AI vs AI mode, get_input() is never called:
            # input_queue would never be emptied without this polling.
            # The received command is executed immediately.
            if hasattr(self.view, "input_queue"):
                try:
                    pending_cmd = self.view.input_queue.get_nowait()
                    command = CommandParser.parse(pending_cmd)
                    if not command.execute(self):
                        is_running = False
                        self.view.quit()
                        break
                    continue
                except queue.Empty:
                    pass
            # ─────────────────────────────────────────────────────────────────────────

            if getattr(self, "pending_timeout", None):
                loser = self.pending_timeout
                self.pending_timeout = None  # Reset du flag
                winner = "O" if loser == "X" else "X"

                scores = GameRules.calculate_score(
                    self.game_state.black_board, self.game_state.white_board
                )

                if hasattr(self.view, "game_over"):
                    action = self.view.game_over(winner, scores)
                    if action in ("restart", "lobby"):
                        self.reset_game({})
                        if action == "lobby":
                            if (
                                getattr(self, "game_client", None)
                                and self.game_client.is_connected
                            ):
                                self.game_client.send_message("BACK")
                            if hasattr(self.view, "output_queue"):
                                self.view.output_queue.put(
                                    ("show_lobby", None)
                                )
                        continue
                    elif action == "quit":
                        command = CommandParser.parse("quit")
                        if command.execute(self):
                            continue
                else:
                    self.view.display_message(
                        _(
                            "Score : Black(X): {black} | White(O): {white}"
                        ).format(black=scores["X"], white=scores["O"])
                    )
                is_running = False
                self.view.quit()
                break

            # Check for server logs and forward them to the view
            while not self.server_log_queue.empty():
                try:
                    log_msg = self.server_log_queue.get_nowait()
                    self.view.output_queue.put(("server_log", log_msg))
                except queue.Empty:
                    break

            if client := getattr(self, "game_client", None):
                # Process any pending lobby/server messages
                while not client.message_queue.empty():
                    try:
                        msg = client.message_queue.get_nowait()
                        if msg == "__DISCONNECTED__":
                            self.handle_network_disconnect()
                            # Continue the loop, which will now run
                            # in offline mode
                            continue
                        processed = self.handle_network_message(msg)
                        if processed:
                            continue
                        elif msg.startswith(
                            "OPPONENT_MOVE "
                        ) or msg.startswith("MOVE "):
                            # Put it back in the queue for the NetworkPlayer
                            # to consume
                            self.game_client.message_queue.put(msg)
                            break  # stop pulling non-lobby messages
                        elif msg == "QUIT":
                            command = CommandParser.parse("quit")
                            command.execute(self)
                    except queue.Empty:
                        break
            if client and client.is_connected:
                is_in_match = any(
                    isinstance(p, NetworkPlayer) for p in self.players.values()
                )

                if not is_in_match:
                    try:
                        input_str = None

                        # -- MODE GUI --
                        if "GUIApp" in str(type(self.view)):
                            try:
                                # We read the GUI queue
                                input_str = self.view.input_queue.get_nowait()
                            except queue.Empty:
                                time.sleep(0.1)  # Avoid using 100% of the CPU
                                continue

                        # -- MODE CLI --
                        else:
                            if not getattr(
                                self, "_lobby_prompt_active", False
                            ):
                                print("\nLobby> ", end="", flush=True)
                                self._lobby_prompt_active = True

                            # Polling sys.stdin for 0.1s
                            i, o, e = select.select([sys.stdin], [], [], 0.1)
                            if not i:
                                continue

                            input_str = sys.stdin.readline().strip()
                            self._lobby_prompt_active = False

                        if not input_str:
                            continue

                        command = CommandParser.parse(input_str)
                        if not command.execute(self):
                            is_running = False
                            self.view.quit()
                        else:
                            # wait so that the server can server response
                            time.sleep(0.1)

                    except KeyboardInterrupt:
                        self.view.display_message(
                            _("Interrupted. End of the game.")
                        )
                        is_running = False
                        self.view.quit()
                        break
                    except Exception as error:
                        self.view.display_error(
                            _("An unexpected error occurred: {error}").format(
                                error=error
                            )
                        )
                    continue

            current_player_obj = self.players[self.current_player]
            if self.blitz_mode:
                self.blitz_mode.current_player = self.current_player

            if self.current_player == "X":
                legal_moves = GameRules.get_legal_moves(
                    self.game_state.black_board, self.game_state.white_board
                )
            else:
                legal_moves = GameRules.get_legal_moves(
                    self.game_state.white_board, self.game_state.black_board
                )

            if legal_moves == 0:
                # No legal moves. Check if it's a game-ending state.
                is_gui_view = hasattr(self.view, "game_over")
                is_network = (
                    getattr(self, "game_client", None)
                    and self.game_client.is_connected
                )
                if GameRules.is_game_over(
                    self.game_state.black_board,
                    self.game_state.white_board,
                    quiet=is_gui_view or is_network,
                ):
                    if is_gui_view:
                        # GUI view handles the game over dialog
                        winner = GameRules.determine_winner(
                            self.game_state.black_board,
                            self.game_state.white_board,
                        )
                        scores = GameRules.calculate_score(
                            self.game_state.black_board,
                            self.game_state.white_board,
                        )
                        action = self.view.game_over(winner, scores)
                        if action in ("restart", "lobby"):
                            self.reset_game({})
                            if action == "lobby":
                                if (
                                    getattr(self, "game_client", None)
                                    and self.game_client.is_connected
                                ):
                                    self.game_client.send_message("BACK")
                                if hasattr(self.view, "output_queue"):
                                    self.view.output_queue.put(
                                        ("show_lobby", None)
                                    )
                            continue
                        elif action == "quit":
                            command = CommandParser.parse("quit")
                            if command.execute(self):
                                continue

                    if is_network:
                        self.reset_game({})
                        continue

                    is_running = False
                    self.view.quit()
                    break

                # Not a terminal state, so the player passes their turn
                self.view.display_message(
                    _("No moves for {player}. Turn passed.").format(
                        player=self.current_player
                    )
                )
                self.current_player = (
                    "O" if self.current_player == "X" else "X"
                )
                continue
            _watcher = None
            _watcher_done = None
            try:
                # Use the player interface to get the move or command
                is_ai_player = isinstance(current_player_obj, AIPlayer)
                if is_ai_player:
                    if hasattr(self.view, "set_thinking_indicator"):
                        if "GUIApp" in str(type(self.view)):
                            ShowCommand("board").execute(self)
                        self.view.set_thinking_indicator(True)

                    # ── Reset stop_event + thread guetteur (GUI) ──
                    # stop_event reset before each calculation: without this,
                    # negamax/mcts would immediately return to all
                    # moves following the first quit.
                    current_player_obj.stop_event.clear()

                    if hasattr(self.view, "input_queue"):  # GUI only, not CLI
                        # The watcher monitors input_queue WHILE
                        # get_move() is blocking.
                        # If a priority command (quit / new) arrives,
                        # it sets stop_event to cleanly interrupt the AI,
                        # then puts the
                        # command back in the queue
                        # so the main loop processes it on the
                        # next iteration.
                        _watcher_done = threading.Event()

                        def _interrupt_watcher(
                            player_obj=current_player_obj, done=_watcher_done
                        ):
                            _priority = {"quit", "quit force", "new"}
                            while not done.is_set():
                                try:
                                    cmd = self.view.input_queue.get(
                                        timeout=0.1
                                    )
                                    if cmd in _priority:
                                        # interrupt the AI if it's
                                        # currently thinking
                                        for p in self.players.values():
                                            if hasattr(p, "stop_event"):
                                                p.stop_event.set()
                                        # Re-enter the command for the
                                        # main loop
                                        self.view.input_queue.put(cmd)
                                        return
                                    else:
                                        # Non-priority command: we put it
                                        # back in the queue,
                                        # the main loop will process it
                                        # between two calls.
                                        self.view.input_queue.put(cmd)
                                        time.sleep(0.05)
                                except queue.Empty:
                                    pass

                        _watcher = threading.Thread(
                            target=_interrupt_watcher, daemon=True
                        )
                        _watcher.start()
                    # ─────────────────────────────────────────────────────────────────────

                input_str = current_player_obj.get_move(
                    self.game_state, self.view
                )

                # ── Clean stop of the lookout after get_move() ──
                if _watcher is not None:
                    _watcher_done.set()
                    _watcher.join(timeout=0.3)
                # ─────────────────────────────────────────────────────────────────────

                if is_ai_player:
                    if hasattr(self.view, "set_thinking_indicator"):
                        self.view.set_thinking_indicator(False)

                # --- INTERCEPTION IN MID-GAME ---
                if input_str == "__DISCONNECTED__":
                    self.handle_network_disconnect()
                    continue

                if getattr(
                    self, "pending_timeout", None
                ) or input_str.startswith("__TIMEOUT__"):
                    continue
                # -------------------------------------

                command = CommandParser.parse(input_str)

                if not command.execute(self):
                    if GameRules.is_game_over(
                        self.game_state.black_board,
                        self.game_state.white_board,
                        quiet=True,
                    ):
                        winner = GameRules.determine_winner(
                            self.game_state.black_board,
                            self.game_state.white_board,
                        )
                        scores = GameRules.calculate_score(
                            self.game_state.black_board,
                            self.game_state.white_board,
                        )

                        if hasattr(self.view, "game_over"):
                            action = self.view.game_over(winner, scores)
                            if action in ("restart", "lobby"):
                                self.reset_game({})
                                if action == "lobby":
                                    if (
                                        getattr(self, "game_client", None)
                                        and self.game_client.is_connected
                                    ):
                                        self.game_client.send_message("BACK")
                                    if hasattr(self.view, "output_queue"):
                                        self.view.output_queue.put(
                                            ("show_lobby", None)
                                        )
                                continue
                            elif action == "quit":
                                command = CommandParser.parse("quit")
                                if command.execute(self):
                                    continue

                        is_network = (
                            getattr(self, "game_client", None)
                            and self.game_client.is_connected
                        )
                        if is_network:
                            self.reset_game({})
                            continue

                    is_running = False
                    self.view.quit()
                else:
                    # Rendu du plateau en mode IA vs IA
                    if isinstance(self.players["X"], AIPlayer) and isinstance(
                        self.players["O"], AIPlayer
                    ):
                        # Affiche le plateau via la commande show existante
                        ShowCommand("board").execute(self)
                    elif (
                        getattr(self, "game_client", None)
                        and self.game_client.is_connected
                    ):
                        # RE-CHECK is_in_match to avoid stale state
                        # after processing queue
                        is_in_match = any(
                            isinstance(p, NetworkPlayer)
                            for p in self.players.values()
                        )
                        if is_in_match and "GUIApp" in str(type(self.view)):
                            ShowCommand("board").execute(self)

            except KeyboardInterrupt:
                if (
                    getattr(self, "game_client", None)
                    and not self.game_client.is_connected
                ):
                    continue
                self.handle_network_disconnect()
                self.view.quit()
                break
            except Exception as error:
                self.view.display_error(
                    _("An unexpected error occurred: {error}").format(
                        error=error
                    )
                )
                continue

    def handle_network_message(self, msg: str) -> bool:
        """Centrally handles network messages for consistent display.

        Handles INFO, ERROR, PLAYERS_LIST, etc., across turns.

        Returns True if the message was handled here.

        """
        if msg.startswith("INFO "):
            info_text = msg[5:]
            self.view.display_message(info_text)
            self._lobby_prompt_active = False

            # UX : Extraction du nom de l'adversaire pour le HeaderBar
            if "Game started against" in info_text or "OPPONENT=" in info_text:
                opponent = ""
                if "against " in info_text:
                    raw_opp = (
                        info_text.split("against ")[1].replace("!", "").strip()
                    )
                    opponent = raw_opp.split()[0]
                    for p in raw_opp.split():
                        if p.startswith("PLAYER="):
                            opponent = p.split("=")[1]
                            break
                elif "OPPONENT=" in info_text:
                    raw_opp = info_text.split("OPPONENT=")[1].strip()
                    opponent = raw_opp.split()[0]

                if opponent and "GUIApp" in str(type(self.view)):
                    self.network_opponent = opponent
                    self.view.output_queue.put(
                        ("set_network_status", f"[Online] vs {opponent}")
                    )

            if "abandoned the game" in info_text or "Game over" in info_text:
                winner = None
                for color, p in self.players.items():
                    if isinstance(p, RealPlayer):
                        winner = color
                        break
                if winner:
                    scores = GameRules.calculate_score(
                        self.game_state.black_board,
                        self.game_state.white_board,
                    )
                    if hasattr(self.view, "game_over"):
                        self.view.game_over(winner, scores)
                self.reset_game({})
            return True

        elif msg.startswith("INVITATION_SENT "):
            raw_target = msg[16:].strip()
            target = raw_target.split()[0]
            for p in raw_target.split():
                if p.startswith("PLAYER=") or p.startswith("TO="):
                    target = p.split("=")[1]
                    break

            self.network_opponent = target
            self.view.display_message(
                _("Invitation sent: {target}").format(target=msg[16:])
            )
            self._lobby_prompt_active = False
            return True

        elif msg.startswith("INVITATION_RECEIVED "):
            # extract requester name for display and potential auto-acceptance
            # Format attendu : INVITATION_RECEIVED FROM=Player_1
            # EXPIRES=300s)
            parts = msg.split(" ")
            requester = "Un joueur"
            for p in parts:
                if p.startswith("FROM="):
                    requester = p.split("=")[1]

            self.network_opponent = requester.strip()

            if "GUIApp" in str(type(self.view)):
                # Envoi du signal spécifique à la fenêtre GTK
                self.view.output_queue.put(("invitation_received", requester))
            else:
                # Fallback pour le mode CLI
                self.view.display_message(
                    _("\n*** CHALLENGE RECEIVED ***\n{msg}").format(
                        msg=msg[20:]
                    )
                )
                self.view.display_message(_("Type 'accept' or 'decline'."))

            self._lobby_prompt_active = False
            return True

        elif msg.startswith("INVITATION_ACCEPTED"):
            self.view.display_message(
                _("Invitation accepted! Game starting...")
            )
            return True

        elif msg.startswith("GAME_START"):
            # Simple notification, the role (START X/O) will trigger
            # the actual start
            return True

        elif msg.startswith("OPPONENT="):
            raw_opp = msg[9:].strip()
            opponent = raw_opp.split()[0]
            self.network_opponent = opponent
            if "GUIApp" in str(type(self.view)):
                self.view.output_queue.put(
                    ("set_network_status", f"[Online] vs {opponent}")
                )
            return True

        elif msg.startswith("ERROR "):
            text = msg[6:]
            is_game_end = (
                "Opponent disconnected" in text or "Game aborted" in text
            )

            # If it's a game-ending error, we skip the raw error popup
            # and show the game_over dialog instead (which is more satisfying)
            if not is_game_end:
                self.view.display_error(text)

            self._lobby_prompt_active = False

            # reset lobby if opponent leaves
            if is_game_end:
                winner = None
                for color, p in self.players.items():
                    if isinstance(p, RealPlayer):
                        winner = color
                        break
                if winner:
                    scores = GameRules.calculate_score(
                        self.game_state.black_board,
                        self.game_state.white_board,
                    )
                    if hasattr(self.view, "game_over"):
                        self.view.game_over(winner, scores)
                self.reset_game({})
            return True

        elif msg.startswith("--- ") or msg.startswith("Server: "):
            self.view.display_message("\n" + msg)
            self._lobby_prompt_active = False
            return True

        elif msg.startswith("START "):
            parts = msg.split(" ")
            if len(parts) == 2:
                role = parts[1]
                self.view.display_message(
                    _("\nGame starting! You play as {role}.").format(role=role)
                )
                if "GUIApp" in str(type(self.view)):
                    self.view.output_queue.put(("game_starting", None))

                # Sauvegarde l'adversaire car
                # _setup_network_game déclenche un reset
                saved_opponent = getattr(self, "network_opponent", None)

                if self.game_client:
                    self.game_client.game_session = self
                    self.game_client._setup_network_game(role)

                # Restauration de l'adversaire
                if saved_opponent:
                    self.network_opponent = saved_opponent

                if "GUIApp" in str(type(self.view)):
                    ShowCommand("board").execute(self)
                    if getattr(self, "network_opponent", None):
                        self.view.output_queue.put(
                            (
                                "set_network_status",
                                f"[Online] vs {self.network_opponent}",
                            )
                        )

            return True

        elif msg.startswith("PLAYERS_LIST"):
            self._lobby_prompt_active = False

            if msg == "PLAYERS_LIST No players connected.":
                if "GUIApp" in str(type(self.view)):
                    self.view.output_queue.put(("player_list", []))
                else:
                    self.view.display_message(_("No players connected."))

            elif msg.startswith("PLAYERS_LIST - "):
                player_info = msg.replace("PLAYERS_LIST - ", "").strip()
                if not hasattr(self, "_player_list_buffer"):
                    self._player_list_buffer = []
                self._player_list_buffer.append(player_info)

                if "GUIApp" in str(type(self.view)):
                    self.view.output_queue.put(
                        ("player_list", list(self._player_list_buffer))
                    )
                else:
                    self.view.display_message(player_info)

            elif "Connected Players:" in msg:
                self._player_list_buffer = []
                if "GUIApp" not in str(type(self.view)):
                    self.view.display_message(_("Connected Players:"))
            else:
                detail = msg.replace("PLAYERS_LIST", "").strip()
                if detail:
                    if "GUIApp" in str(type(self.view)):
                        self.view.output_queue.put(("player_detail", detail))
                    else:
                        self.view.display_message(detail)

            return True

        elif msg.startswith("SYNC_BOARD "):
            self.sync_board(msg[11:].strip())
            return True

        elif msg.startswith("SCOREBOARD"):
            self._lobby_prompt_active = False
            # Nettoyer le préfixe pour ne garder que le texte
            line = msg.replace("SCOREBOARD", "").strip()

            if "GUIApp" in str(type(self.view)):
                # Envoyer la ligne seule à la file d'attente
                self.view.output_queue.put(("scoreboard_line", line))
            else:
                self.view.display_message(line)
            return True

        elif msg.startswith("SERVER_STATUS"):
            self._lobby_prompt_active = False
            # Nettoyer le préfixe pour ne garder que le texte
            line = msg.replace("SERVER_STATUS", "").strip()

            if "GUIApp" in str(type(self.view)):
                # Envoi du signal à la file d'attente de la GUI
                self.view.output_queue.put(("server_status_line", line))
            else:
                self.view.display_message(line)
            return True

        elif msg.startswith("PONG"):
            self.view.display_message(msg)
            return True

        elif msg.startswith("NAME_OK "):
            new_name = msg[8:].strip()
            self.view.display_message(
                _("Name changed to: {name}").format(name=new_name)
            )
            self._lobby_prompt_active = False
            return True

        if msg.startswith("GAME_OVER"):
            parts = msg.split()
            winner = parts[1] if len(parts) > 1 else "DRAW"

            is_in_match = getattr(self, "players", None) and any(
                isinstance(p, NetworkPlayer) for p in self.players.values()
            )
            if is_in_match:
                self.view.display_message(
                    _("Game over! Winner is {winner}.").format(winner=winner)
                )
                self.reset_game({})
            return True

        elif msg.startswith("YOUR_ID "):
            # Silently consumed — identity is managed by GameClient
            if "GUIApp" in str(type(self.view)):
                self.view.output_queue.put(
                    ("set_network_status", "[Online] Lobby")
                )
            return True

        return False

    def sync_board(self, sync_data: str):
        """Synchronizes the local board state with server data.

        sync_data should be 'current_player black_bb white_bb'

        """
        parts = sync_data.split(" ")
        if len(parts) < 3:
            return

        try:
            self.current_player = parts[0]
            self.game_state.black_board = int(parts[1])
            self.game_state.white_board = int(parts[2])
            self.view.display_message(
                _("Game synchronized! It is {player}'s turn.").format(
                    player=self.current_player
                )
            )
            player_bb, opponent_bb = self.game_state.get_bitboards(
                self.current_player
            )
            self.view.render(
                self.game_state.get_board_as_string(),
                GameRules.get_legal_moves(player_bb, opponent_bb),
                self.current_player,
                self.unsaved_changes,
            )
            self.unsaved_changes = True
        except (ValueError, IndexError):
            pass

    def handle_network_disconnect(self):
        """Cleans up network state and resets the game to local mode."""
        if (
            getattr(self, "game_client", None)
            and self.game_client.is_connected
        ):
            self.game_client.quit()
        self.game_client = None

        if getattr(self, "game_server", None) and self.game_server.is_running:
            self.game_server.stop_server()
            self.game_server = None

        self.reset_game({})  # Resets players to RealPlayer/AI

    def server_command_loop(self):
        """Input loop for running the dedicated GameServer interactively."""
        is_running = True

        while is_running and self.game_server and self.game_server.is_running:
            try:
                input_str = self.view.get_input("server> ")
                if not input_str:
                    continue
                # For basic inputs like "quit", "players", "scoreboard",
                # "server status"
                command = CommandParser.parse(input_str)
                if not command.execute(self):
                    is_running = False
                    if self.game_server:
                        self.game_server.stop_server()
            except KeyboardInterrupt:
                is_running = False
                if self.game_server:
                    self.game_server.stop_server()
            except Exception as error:
                self.view.display_error(
                    _("An unexpected error occurred: {error}").format(
                        error=error
                    )
                )
                continue

    def _read_clean_lines(self, filepath: str) -> list[str] | None:
        """Read file and return non-empty, non-comment lines.

        :param filepath: Path to the file to load.
        :return: A list or None in case of error.

        """
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                content = file.read()
            # \{[^}]*\} : Cherche tout ce qui est entre { et }
            # (commentaires blocs)
            # #[^\n]* : Cherche tout ce qui est après un # jusqu'à
            # la fin de la ligne
            # Le flag re.DOTALL permet au '.' de matcher aussi les
            # retours à la ligne
            pattern = r"(\{[^}]*\})|(#[^\n]*)"
            content_cleaned = re.sub(pattern, "", content, flags=re.DOTALL)
            lines = []
            for line in content_cleaned.splitlines():
                if stripped := line.strip():
                    lines.append(stripped)
            return lines
        except IOError:
            return None

    def register_move(self, move_str: str):
        """Register the move and actual state.

        Delete redo if new move is done.

        :param move_str: The move.

        """
        # Sauvegarde une COPIE de l'état actuel
        current_state_snapshot = GameState()
        current_state_snapshot.black_board = self.game_state.black_board
        current_state_snapshot.white_board = self.game_state.white_board

        self.undo_stack.append((current_state_snapshot, self.current_player))
        self.history.append(move_str)

        # Le redo est vidé si on joue un nouveau coup
        self.redo_stack.clear()
        self.unsaved_changes = True

    def undo_move(self, n_moves=1):
        """Undo the n last moves.

        :param n_moves: Number of moves to undo.
        :type n_moves: Int.
        :return: True if we can undo n moves, False otherwise.

        """
        for i in range(n_moves):
            if not self.undo_stack:
                self.view.display_message(_("Nothing to undo."))
                return False

            # Récupérer le dernier état
            prev_state, prev_player = self.undo_stack.pop()
            last_move = self.history.pop()

            # Sauvegarder l'état actuel dans le Redo
            current_snapshot = GameState()
            current_snapshot.black_board = self.game_state.black_board
            current_snapshot.white_board = self.game_state.white_board

            # On stocke l'état AVANT le undo dans redo, avec le coup
            # qui avait été joué
            self.redo_stack.append(
                (current_snapshot, last_move, self.current_player)
            )

            # Restaurer l'état
            self.game_state = prev_state
            self.current_player = prev_player
        return True

    def redo_move(self, n_moves=1):
        """Redo the n last moves.

        :param n_moves: Number of moves to redo.
        :type n_moves: Int.
        :return: True if we can redo n moves, False otherwise.

        """
        for i in range(n_moves):
            if not self.redo_stack:
                self.view.display_message(_("Nothing to redo."))
                return False

            # Récupérer l'état futur
            next_state, move_str, next_player = self.redo_stack.pop()

            # Mettre dans Undo (l'état courant devient le passé)
            current_snapshot = GameState()
            current_snapshot.black_board = self.game_state.black_board
            current_snapshot.white_board = self.game_state.white_board
            self.undo_stack.append((current_snapshot, self.current_player))

            # Appliquer l'état futur
            self.game_state = next_state
            self.current_player = next_player
            self.history.append(move_str)
        return True
