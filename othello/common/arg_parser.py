"""ArgParser Module."""

import argparse
import random

from othello import __version__
from othello.common.config_manager import ConfigManager
from othello.common.i18n_manager import I18nManager


def _(message):
    return I18nManager().gettext(message)


class ArgParser:
    """ArgParser Class."""

    def __init__(self):
        self.config_mgr = ConfigManager()
        self.parser = argparse.ArgumentParser(
            description=_("Othello Game"), prog="othello"
        )
        self._setup_args()

    def _setup_args(self):
        """Define the available command-line arguments and their options."""
        # General options
        self.parser.add_argument(
            "-V",
            "--version",
            action="version",
            version=f"%(prog)s {__version__}",
        )
        self.parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help=_("Increase verbosity"),
        )
        self.parser.add_argument(
            "-d", "--debug", action="store_true", help=_("Show debug messages")
        )

        # Game options
        self.parser.add_argument(
            "-b", "--blitz", action="store_true", help=_("Enable blitz mode")
        )
        self.parser.add_argument(
            "-t",
            "--time",
            type=int,
            help=_("Time limit in minutes for blitz mode"),
        )
        self.parser.add_argument(
            "-g", "--gui", action="store_true", help=_("Launch GUI")
        )
        self.parser.add_argument(
            "-c", "--contest", action="store_true", help=_("Contest mode")
        )
        self.parser.add_argument(
            "-s",
            "--size",
            type=int,
            choices=[6, 8, 10, 12],
            default=None,
            help=_("Board size (6, 8, 10 or 12). Default = 8."),
        )

        # AI options
        self.parser.add_argument(
            "-a",
            "--ai",
            nargs="?",
            const="default",
            choices=["b", "w", "A", "default"],
            help=_("Enable AI for a color (or all)"),
        )
        self.parser.add_argument(
            "--ai-time", type=float, help=_("AI thinking time in seconds")
        )
        self.parser.add_argument(
            "--ai-mode",
            choices=["minimax", "iterative", "mcts"],
            help=_("AI algorithm mode"),
        )
        self.parser.add_argument(
            "--ai-mcts-selection",
            choices=["UCT", "ML", "DL"],
            default="UCT",
            help=_("MCTS Selection algorithm"),
        )
        self.parser.add_argument(
            "--ai-minimax-depth", type=int, help=_("Minimax depth")
        )
        self.parser.add_argument(
            "--ai-minimax-scoring",
            choices=["function1", "function2", "function3"],
            help=_("Minimax scoring function"),
        )

        # Contest/Load file
        self.parser.add_argument(
            "file",
            nargs="?",
            help=_("File to load (game save or contest file)"),
        )

        # Server
        self.parser.add_argument(
            "--server",
            action="store_true",
            help=_("Start as server mode"),
        )
        self.parser.add_argument(
            "-p",
            "--port",
            nargs="?",
            const="12345",
            help=_("Port to use for server (default: 12345)"),
        )
        self.parser.add_argument(
            "--daemon",
            action="store_true",
            help=_("Run server in daemon mode"),
        )
        self.parser.add_argument(
            "-l",
            "--lang",
            type=str,
            choices=["en", "fr"],
            help=_("Choose language"),
        )

    def parse(self, args=None):
        """Parse command-line arguments and update the configuration.

        Updates the defaults in ConfigManager based on the provided arguments.
        :param args: List of arguments to parse
        :type args: list (optional, defaults to sys.argv).
        :return: The parsed arguments namespace.

        """
        args = self.parser.parse_args(args)
        config = self.config_mgr.config_parser["defaults"]

        if args.verbose:
            config["verbose"] = "true"
        if args.debug:
            config["debug"] = "true"
        if args.blitz:
            config["blitz"] = "true"
            config["timeout"] = (
                str(args.time) if args.time is not None else "30"
            )

        if args.time is not None:
            if not args.blitz:
                print(
                    _(
                        "Warning : Option '--time' ignored because "
                        "Blitz Mode (--blitz) is not enabled."
                    )
                )

        if args.gui:
            config["gui"] = "true"

        if args.size is not None:
            config["size"] = str(args.size)

        if args.ai is not None:
            config["ai_enabled"] = "true"
            if args.ai == "default":
                config["ai_color"] = random.choice(["b", "w"])
            elif args.ai == "A":
                config["ai_color"] = "A"
            else:
                config["ai_color"] = args.ai

        if args.ai_time is not None:
            config["ai_time"] = str(args.ai_time)

        if args.ai_mode is not None:
            config["ai_mode"] = args.ai_mode

        if args.ai_mcts_selection is not None:
            config["ai_mcts_selection"] = args.ai_mcts_selection

        if args.ai_minimax_depth is not None:
            config["ai_minimax_depth"] = str(args.ai_minimax_depth)

        if args.ai_minimax_scoring is not None:
            config["ai_minimax_scoring"] = args.ai_minimax_scoring

        if args.file:
            config["input_file"] = args.file
        else:
            config.pop("input_file", None)

        if args.server or args.port:
            config["server_mode"] = "true"
            if args.port:
                config["server_port"] = str(args.port)
            elif not config.get("server_port"):
                config["server_port"] = "12345"

        if args.daemon:
            config["daemon"] = "true"

        if args.contest:
            config["contest"] = "true"

        if args.lang:
            config["lang"] = str(args.lang)

        return args
