"""Blitz Controller Module."""

import threading
import time

from othello.common.i18n_manager import I18nManager
from othello.orchestrator.interface_gamemode import GameMode


def _(message):
    return I18nManager().gettext(message)


class BlitzMode(GameMode):
    """Blitz Mode Class using a background thread."""

    def __init__(self, time_limit_minutes, timeout_callback):
        self.time_limit = time_limit_minutes * 60.0
        self.remaining_time = {"X": self.time_limit, "O": self.time_limit}
        self.current_player = "X"
        self.is_paused = False
        self.timeout_callback = timeout_callback

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._timer_loop, daemon=True)

    def start(self):
        """Init & start the gamemode."""
        print(
            _("Blitz Mode : {time} minutes per player.").format(
                time=self.time_limit / 60
            )
        )
        self._thread.start()

    def handle_turn(self, player: str, move: str):
        """Handle the specific logic of the mode during the player's turn."""
        if move not in ["save", "help", "show"]:
            self.current_player = "O" if player == "X" else "X"

    def check_end_condition(self):
        """Check if end conditions of the mode are okay."""
        return self.remaining_time["X"] <= 0 or self.remaining_time["O"] <= 0

    def pause(self):
        """Pause or resume the timer."""
        self.is_paused = not self.is_paused
        print(_("Game resumed.") if not self.is_paused else _("Game paused."))

    def stop(self):
        """Stop the timer thread cleanly."""
        self._stop_event.set()

    def _timer_loop(self):
        """Background thread updating the time every 0.1 seconds."""
        last_time = time.time()
        while not self._stop_event.is_set():
            time.sleep(0.1)
            now = time.time()
            elapsed = now - last_time
            last_time = now
            if not self.is_paused:
                self.remaining_time[self.current_player] -= elapsed

                if self.check_end_condition():
                    self.remaining_time[self.current_player] = 0
                    self.timeout_callback(self.current_player)
                    self._stop_event.set()
