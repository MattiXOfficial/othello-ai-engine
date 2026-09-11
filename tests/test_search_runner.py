import threading
import time
from unittest.mock import MagicMock
from unittest.mock import patch

from othello.player.search_runner import SearchRunner


def setup_mock_ai():
    """Helper pour configurer le mock de l'IA.

    Avec les attributs nécessaires.
    """
    ai = MagicMock()
    ai.color = "X"
    ai.shared_best_move = None
    ai.move_lock = threading.Lock()
    ai.stop_event = threading.Event()
    ai.ai_mode = "minimax"
    ai.ai_minimax_depth = 1
    ai.debug = False
    ai.random_move.return_value = "X z9"
    return ai


def test_search_runner_completes_normally():
    """Le search se termine normalement avant le timeout."""
    ai = setup_mock_ai()
    state = MagicMock()

    def _mock_search_task():
        # Simule un search ultra rapide
        with ai.move_lock:
            ai.shared_best_move = "X a1"

    with patch.object(
        SearchRunner, "_search_task", side_effect=_mock_search_task
    ):
        runner = SearchRunner(ai, state)
        # On donne un timeout large
        move = runner.run(timeout=0.5)

    assert move == "X a1"
    assert not ai.stop_event.is_set()


def test_search_runner_cooperative_stop_triggered():
    ai = setup_mock_ai()
    state = MagicMock()

    def slow_search():
        # 1. On attend un peu pour dépasser le timeout initial de run()
        time.sleep(0.2)
        # 2. On donne un coup pour sortir de la boucle
        # 'while shared_best_move is None'
        with ai.move_lock:
            ai.shared_best_move = "X b2"
        # 3. On reste en vie pour forcer le code à appeler stop_event.set()
        time.sleep(0.5)

    with patch.object(SearchRunner, "_search_task", side_effect=slow_search):
        runner = SearchRunner(ai, state)
        # Timeout très court pour forcer l'expiration immédiate
        # après le premier join
        move = runner.run(timeout=0.05)

    assert (
        ai.stop_event.is_set()
    ), "Le timeout est passé et le thread est tjs en vie, "
    "stop_event doit être True"
    assert move == "X b2"


def test_search_runner_fallback_to_random():
    ai = setup_mock_ai()
    ai.random_move.return_value = "X random"
    state = MagicMock()

    # On crée un mock de thread
    mock_thread = MagicMock(spec=threading.Thread)

    # Correction CRUCIALE : side_effect avec une liste finit par StopIteration.
    # On utilise une petite fonction lambda ou on gère la liste différemment.
    # Ici, on simule : le thread est vivant 2 fois, puis meurt.
    mock_thread.is_alive.side_effect = [True, True, False, False, False, False]

    with patch("threading.Thread", return_value=mock_thread):
        runner = SearchRunner(ai, state)
        # On s'assure que shared_best_move reste None pour forcer le fallback
        ai.shared_best_move = None

        move = runner.run(timeout=0.01)

    assert move == "X random"
    ai.random_move.assert_called()


def test_search_task_routes_to_minimax():
    # 1. Préparation du mock de l'IA
    ai = MagicMock()
    ai.ai_mode = "minimax"
    ai.ai_minimax_depth = 3
    ai.ai_minimax_scoring = "heuristic_v1"
    ai.color = "X"
    ai.debug = False

    # Snapshot du plateau
    state = MagicMock()

    # 2. Initialisation du Runner
    runner = SearchRunner(ai, state)

    # 3. Exécution de la tâche de recherche (on l'appelle manuellement ici)
    runner._search_task()

    # 4. Vérifications
    # On vérifie que la méthode minimax de l'IA a été appelée
    # avec la profondeur 3
    ai.minimax.assert_called_once_with(
        state,
        ai.color,
        depth=3,
        alpha=float("-inf"),
        beta=float("inf"),
        scoring_func_name="heuristic_v1",
        debug=False,
    )
    # On s'assure que les autres modes n'ont pas été lancés
    ai.it_deepening.assert_not_called()
    ai.mcts.assert_not_called()


def test_search_task_routes_to_mcts():
    ai = MagicMock()
    ai.ai_mode = "mcts"
    ai.ai_minimax_depth = None  # Pas de profondeur pour MCTS
    ai.color = "O"
    ai.debug = True

    state = MagicMock()
    runner = SearchRunner(ai, state)

    runner._search_task()

    # Vérifie que MCTS est appelé avec un grand nombre d'itérations
    ai.mcts.assert_called_once()
    args, kwargs = ai.mcts.call_args
    assert kwargs["n_iter"] > 10000
    assert kwargs["debug"] is True


def test_search_task_random_fallback_updates_shared_move():
    ai = MagicMock()
    ai.ai_mode = "random"  # Mode inconnu ou random
    ai.color = "X"
    ai.move_lock = MagicMock()  # Pour vérifier l'usage du lock
    # On définit ce que renvoie la fonction random
    ai.random_move.return_value = "X c3"

    state = MagicMock()
    runner = SearchRunner(ai, state)

    # On simule l'entrée dans le context manager du lock
    with patch.object(ai.move_lock, "__enter__"):
        runner._search_task()

    # Vérifie que le move a été écrit dans la variable partagée
    assert ai.shared_best_move == "X c3"


def test_search_task_routes_to_iterative():
    # 1. Setup
    ai = MagicMock()
    ai.ai_mode = "iterative"
    ai.ai_minimax_depth = (
        10  # Devrait être ignoré par it_deepening qui gère son temps
    )
    ai.ai_minimax_scoring = "corner_strategy"
    ai.color = "O"
    ai.debug = True

    state = MagicMock()
    runner = SearchRunner(ai, state)

    # 2. Action
    runner._search_task()

    # 3. Assertions
    ai.it_deepening.assert_called_once_with(
        state,
        ai.color,
        None,  # Le paramètre de temps interne
        float("-inf"),  # Alpha
        float("inf"),  # Beta
        "corner_strategy",
        debug=True,
    )


def test_search_runner_no_infinite_loop():
    """Test que run() se termine même si aucun coup n'est trouvé.

    En simulant la fin du thread.
    """
    ai = MagicMock()
    ai.debug = False
    ai.shared_best_move = None
    ai.move_lock = threading.Lock()
    ai.stop_event = threading.Event()
    ai.random_move.return_value = "X fallback"

    state = MagicMock()
    runner = SearchRunner(ai, state)

    # On crée un mock de thread
    mock_thread = MagicMock(spec=threading.Thread)

    # CRUCIAL : is_alive doit finir par renvoyer False pour casser
    # la boucle 'while self.thread.is_alive()' dans ton code.
    # On simule : vivant pendant 3 checks, puis mort.
    mock_thread.is_alive.side_effect = [True, True, True, False, False, False]

    with patch("threading.Thread", return_value=mock_thread):
        # On patche _async_raise pour éviter des erreurs sur le mock
        with patch("othello.player.search_runner._async_raise"):
            move = runner.run(timeout=0.01)

    # Vérifications
    assert move == "X fallback"
    ai.random_move.assert_called()


def test_trigger_error_print():
    """Exécute la branche d'erreur dans _search_task."""
    ai = MagicMock()
    ai.ai_mode = "minimax"
    ai.minimax.side_effect = Exception("Force crash")

    runner = SearchRunner(ai, MagicMock())

    # Exécute la tâche, l'exception est catchée et printée
    runner._search_task()

    assert True
