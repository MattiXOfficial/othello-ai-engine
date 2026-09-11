"""Orchestrator Module."""

import os
import sys
import threading
import time

from othello.common.arg_parser import ArgParser
from othello.common.config_manager import ConfigManager
from othello.common.i18n_manager import I18nManager
from othello.network.game_server import GameServer
from othello.orchestrator.bitboard_ops import BitboardOps
from othello.orchestrator.contest_controller import ContestMode
from othello.orchestrator.game_session import GameSession
from othello.user_interface.cli_shell import CLIShell
from othello.user_interface.gui_app import GUIApp


def _(message):
    return I18nManager().gettext(message)


class Orchestrator:
    """AppOrchestrator Class."""

    def __init__(self):
        """Initialize the orchestrator, load configuration and parse arguments.

        Sets up the configuration manager, argument parser, and i18n manager.
        Configures the board size based on settings. Instantiates and starts
        the appropriate view (CLI or GUI).

        """
        self.invalid_config = False
        self.config_manager = ConfigManager()
        if not self.config_manager.valid_options_check():
            print(_("Error: Invalid config file. Proceeding with defaults."))
            self.config_manager.reset_to_defaults()
            self.invalid_config = True

        self.arg_parser = ArgParser()
        self.parsed_args = self.arg_parser.parse()

        # if not self.invalid_config:
        #     self.config_manager.save_config()

        self.config = self.config_manager.config_parser["defaults"]
        cli_lang = getattr(self.parsed_args, "lang", None)
        chosen_lang = cli_lang if cli_lang else self.config.get("lang")
        self.i18n = I18nManager(lang=chosen_lang)
        try:
            board_size = int(self.config.get("size", 8))
        except ValueError:
            board_size = 8
        BitboardOps.set_board_size(board_size)
        if self.config.get("contest") != "true":
            print(
                _("Game configured for board size: {size}*{size}.").format(
                    size=board_size
                )
            )

        # Instantiate the appropriate view based on configuration
        if self.parsed_args.gui:
            self.view = GUIApp()
        else:
            # Default to CLI
            self.view = CLIShell(
                commands=[
                    "help",
                    "quit",
                    "save",
                    "load",
                    "undo",
                    "redo",
                    "new",
                    "pause",
                    "hint",
                    "show",
                    "set",
                    "server",
                    "join",
                    "ping",
                ]
            )

    def run(self):
        """Start the main application loop.

        Determines the execution mode (GUI, Console, Contest) from the
        configuration and launches the appropriate controller.

        """
        if self.config["verbose"] == "true":
            print(_("Running in verbose mode"))

        if self.config.get("server_mode") == "true":
            try:
                port = int(self.config.get("server_port", 12345))
            except ValueError:
                port = 12345

            is_daemon = self.config.get("daemon") == "true"
            server = GameServer(port=port)

            if not is_daemon:
                server.start_server(is_daemon=False)
                print(
                    _(
                        "Server running in interactive mode. "
                        "Type 'quit' to stop."
                    )
                )
                session = GameSession(view=self.view)
                session.game_server = server
                session.server_command_loop()
            else:
                try:
                    if os.fork() > 0:
                        sys.exit(0)
                except OSError as e:
                    sys.stderr.write(f"Fork #1 failed: {e}\n")
                    sys.exit(1)

                os.setsid()

                try:
                    pid = os.fork()  # merci guermouche pour les fork
                    if pid > 0:
                        print(
                            _(
                                "Daemon successfully started on port {port} "
                                "with PID: {pid}"
                            ).format(port=port, pid=pid)
                        )
                        print(
                            _(
                                "Check 'server.log' for output. "
                                "To stop it, do "
                                "`pkill -f 'othello -server'` and if it's not "
                                "working `kill {pid}`"
                            ).format(pid=pid)
                        )
                        sys.exit(0)
                except OSError as e:
                    sys.stderr.write(f"Fork #2 failed: {e}\n")
                    sys.exit(1)

                sys.stdout.flush()
                sys.stderr.flush()
                with open("/dev/null", "r") as f:
                    os.dup2(f.fileno(), sys.stdin.fileno())
                with open("server.log", "a") as f:
                    os.dup2(f.fileno(), sys.stdout.fileno())
                    os.dup2(f.fileno(), sys.stderr.fileno())

                server.start_server(is_daemon=True)
                try:
                    while server.is_running:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
                finally:
                    server.stop_server()
            return

        session = GameSession(view=self.view)

        if self.config.get("contest") == "true":
            contest_mode = ContestMode(session)
            contest_mode.start()
            return  # Quitte run pour ne pas lancer la GUI/CLI standard

        if self.parsed_args.gui:
            game_thread = threading.Thread(
                target=session.command_loop, daemon=True
            )
            game_thread.start()
            self.view.start()
        else:
            self.view.start()
            session.command_loop()
