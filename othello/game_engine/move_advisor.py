"""Advice Module."""


def get_advice(board, heuristic, *args, **kwargs):
    """Executes a heuristic function to obtain an evaluation or advice.

    :param board: The bitboard representing the current game state.
    :type board: tuple[int | Any, int | Any]
    :param heuristic: The heuristic function to apply. It must accept
        'board' as its first argument.
    :type heuristic: callable
    :param args: Variable length argument list passed to the heuristic
        function.
    :param kwargs: Arbitrary keyword arguments passed to the heuristic
        function.
    :return: The result returned by the heuristic.

    """
    return heuristic(board, *args, **kwargs)
