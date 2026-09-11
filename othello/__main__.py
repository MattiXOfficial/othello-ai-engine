"""Program Entry."""

import sys

from othello import __version__
from othello.orchestrator.app_orchestrator import Orchestrator


def main():
    """Starting point of the program."""
    print(f"Othello PDP 2026 version : {__version__}")
    orchestrator = Orchestrator()
    orchestrator.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
