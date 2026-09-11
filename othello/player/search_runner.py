"""Module defining the SearchRunner class and utilities for controlling AI
searches with strict
time.

constraints in Othello.

"""

import ctypes
import threading

from othello.common.i18n_manager import I18nManager


def _(message):
    return I18nManager().gettext(message)


class SearchTimeout(BaseException):
    """Custom exception used to forcibly interrupt an AI search thread."""


def _async_raise(tid, exctype):
    """Inject an asynchronous exception into a running Python thread."""
    if not isinstance(exctype, type):
        exctype = type(exctype)

    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(tid), ctypes.py_object(exctype)
    )

    if res == 0:
        raise ValueError("Invalid thread id")
    elif res > 1:
        # rollback logic if multiple threads were suspiciously matched
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


class SearchRunner:
    """Encapsulates an AI search execution.

    Within a managed background thread.
    """

    def __init__(self, ai_player, game_state):
        self.ai = ai_player
        self.state = game_state
        self.thread = None

    def _search_task(self):
        """The core thread target function executing the AI."""
        try:
            # Depth resolution logic for bounded evaluations
            if self.ai.ai_minimax_depth is not None:
                depth = self.ai.ai_minimax_depth
            elif self.ai.ai_time is not None and self.ai.ai_mode == "minimax":
                depth = self.ai.predict_depth(
                    self.state, self.ai.color, self.ai.ai_time
                )
            else:
                depth = 5

            # Route to the configured algorithm method
            if self.ai.ai_mode == "minimax":
                self.ai.minimax(
                    self.state,
                    self.ai.color,
                    depth=depth,
                    alpha=float("-inf"),
                    beta=float("inf"),
                    scoring_func_name=self.ai.ai_minimax_scoring,
                    debug=self.ai.debug,
                )

            elif self.ai.ai_mode == "iterative":
                self.ai.it_deepening(
                    self.state,
                    self.ai.color,
                    None,
                    float("-inf"),
                    float("inf"),
                    self.ai.ai_minimax_scoring,
                    debug=self.ai.debug,
                )

            elif self.ai.ai_mode == "mcts":
                self.ai.mcts(
                    self.state,
                    self.ai.color,
                    n_iter=10
                    # Voluntarily massive; intended to be pruned by timeout
                    ** 9,
                    debug=self.ai.debug,
                )

            else:
                # Random fallback bypasses search overheads
                move = self.ai.random_move(
                    (self.state.white_board, self.state.black_board),
                    self.ai.color,
                )
                with self.ai.move_lock:
                    self.ai.shared_best_move = move

        except SearchTimeout:
            # Expected interception route when _async_raise fires.
            pass
        except Exception as e:
            print(_("[ERROR] search thread crashed: {error}").format(error=e))

    def run(self, timeout):
        """Launch the threaded search and enforce the specified timeout.

        The shutdown protocol is carefully staged to handle C-level ML/DL
        module hang ups:
        1. Wait for `timeout` to expire.
        2. Block until at least one valid move is secured to avoid returning
        empty plays.
        3. Attempt a "Cooperative soft-stop" via `stop_event` flag to allow
        current loops to break.
        4. Wait a grace period (0.2s) for clean exit.
        5. If still alive (stuck in C bindings ignoring loops),
        use `_async_raise` for a kill.

        :param timeout: Time threshold to allocate
            to the search thread (in seconds).
        :type timeout: float
        :return: The best move encoded as a string (e.g. "X e4").
        :rtype: str

        """
        with self.ai.move_lock:
            self.ai.shared_best_move = None

        # Reset the cooperative boolean flag
        self.ai.stop_event.clear()

        self.thread = threading.Thread(target=self._search_task)
        self.thread.start()

        # Step 1: Wait up to the formal limit
        self.thread.join(timeout)

        # Step 2: Prevent premature abortion before finding
        # at least one valid play.
        # This while-loop securely loops and prevents
        # timeout execution until populated.
        while self.thread.is_alive():
            with self.ai.move_lock:
                if self.ai.shared_best_move is not None:
                    break
            self.thread.join(0.01)

        # Step 3: Formal Timeout Enforcement
        if self.thread.is_alive():
            if self.ai.debug:
                print(_("[DEBUG] Timeout reached → cooperative stop signaled"))

            # Cooperative Kill: Flags python bytecode loops to manually break
            self.ai.stop_event.set()

            # Step 4: Grace period for cooperative abort to unwind the stack
            self.thread.join(0.2)

            # Step 5: Brutal Kill
            if self.thread.is_alive():
                if self.ai.debug:
                    print(
                        _(
                            "[DEBUG] "
                            "Cooperative stop failed → brutal killing thread"
                        )
                    )

                with self.ai.move_lock:
                    try:
                        _async_raise(self.thread.ident, SearchTimeout)
                    except Exception as e:
                        print(
                            _("[ERROR] kill failed: {error}").format(error=e)
                        )

                self.thread.join()

        # Safely retrieve the highest confidence move known upon termination
        with self.ai.move_lock:
            if self.ai.shared_best_move is None:
                if self.ai.debug:
                    print(_("[DEBUG] fallback random move"))
                return self.ai.random_move(
                    (self.state.white_board, self.state.black_board),
                    self.ai.color,
                )

            return self.ai.shared_best_move
