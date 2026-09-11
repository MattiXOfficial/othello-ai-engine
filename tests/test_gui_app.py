import queue
import sys
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# On patche gi.require_version dans TOUS les sous-modules avant tout import
with patch("gi.require_version"):
    from othello.user_interface.dialogs import (
        server_dialogs as server_dialogs_module
    )
    import othello.user_interface.dialogs.config_dialog as config_dialog_module
    import othello.user_interface.dialogs.save_dialog as save_dialog_module
    import othello.user_interface.gui_app as gui_module
    import othello.user_interface.othello_window as window_module

    # Injection de la fonction de traduction globale
    for mod in (gui_module, window_module):
        if not hasattr(mod, "_"):
            mod._ = lambda x: x

    from othello.user_interface.dialogs.config_dialog import ConfigDialog
    from othello.user_interface.dialogs.save_dialog import SaveDialog
    from othello.user_interface.dialogs.server_dialogs import HostServerDialog
    from othello.user_interface.dialogs.server_dialogs import JoinServerDialog
    from othello.user_interface.dialogs.server_dialogs import LobbyDialog
    from othello.user_interface.gui_app import GUIApp
    from othello.user_interface.gui_app import OthelloWindow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Chemins des modules utilisés par les patches
_WIN = "othello.user_interface.othello_window"
_CFG = "othello.user_interface.dialogs.config_dialog"
_SAV = "othello.user_interface.dialogs.save_dialog"
_SRV = "othello.user_interface.dialogs.server_dialogs"
_APP = "othello.user_interface.gui_app"


@pytest.fixture(autouse=True)
def reset_singletons():
    from othello.common.config_manager import ConfigManager

    ConfigManager._instance = None
    yield
    ConfigManager._instance = None


def setup_mock_window():
    """Creates a mocked window with the necessary attributes for testing."""
    with patch.object(OthelloWindow, "__init__", return_value=None):
        window = OthelloWindow(None, None, None)
        window.input_queue = queue.Queue()
        window.output_queue = queue.Queue()
        window.status_label = MagicMock()
        window.board_grid = MagicMock()
        window.get_application = MagicMock()
        window.unsaved_changes = False
        window.current_player = "X"
        window.is_my_turn = True
        window.score_label_black = MagicMock()
        window.score_label_white = MagicMock()

        window.add_accel_group = MagicMock()
        window.draggable_piece = MagicMock()
        window.dnd_target_entry = MagicMock()

        # --- Network ---
        window.host_server_dialog = None
        window.join_server_dialog = None
        window.lobby_dialog = None

        return window


def make_lobby(input_queue=None):
    """Retourne un LobbyDialog entièrement mocké (sans GTK réel)."""
    if input_queue is None:
        input_queue = queue.Queue()
    with patch.object(LobbyDialog, "__init__", return_value=None):
        dialog = LobbyDialog(None, input_queue)
    dialog.input_queue = input_queue
    dialog.player_listbox = MagicMock()
    dialog.server_status_label = MagicMock()
    dialog.name_entry = MagicMock()
    dialog.status_toggle = MagicMock()
    dialog.show_all = MagicMock()
    dialog.refresh_timer = None
    return dialog


# ---------------------------------------------------------------------------
# GUIAPP TESTS
# ---------------------------------------------------------------------------


def test_guiapp_methods():
    app = gui_module.GUIApp()
    app.render("XO/..", 1, "X", True)
    assert app.output_queue.get(timeout=1) == (
        "render",
        ("XO/..", 1, "X", True),
    )

    app.display_message("hello")
    assert app.output_queue.get(timeout=1) == ("display_message", "hello")

    app.display_error("err")
    assert app.output_queue.get(timeout=1) == ("display_error", "err")

    app.quit()
    assert app.output_queue.get(timeout=1) == ("quit", None)

    with (
        patch.object(app.input_queue, "get_nowait", side_effect=queue.Empty),
        patch.object(app.input_queue, "get", return_value="my_move"),
    ):
        res = app.get_input("prompt")
        assert app.output_queue.get(timeout=1) == ("get_input", "prompt")
        assert res == "my_move"

    # 1. get_input avec "Player" : force le sync du plateau au premier appel
    res_sync = app.get_input("Player X's turn")
    assert res_sync == "show board"
    assert app._board_synced is True

    # 2. get_input au deuxième appel : le plateau est sync,
    # on lit la file d'attente
    with (
        patch.object(app.input_queue, "get_nowait", side_effect=queue.Empty),
        patch.object(app.input_queue, "get", return_value="X a1"),
    ):
        res_move = app.get_input("Player X's turn")
        assert app.output_queue.get(timeout=1) == (
            "get_input",
            "Player X's turn",
        )
        assert res_move == "X a1"
        assert app._board_synced is False

    # 3. game_over
    with patch.object(app.input_queue, "get", return_value="restart"):
        res_go = app.game_over("White", {"X": 2, "O": 4})
        assert app.output_queue.get(timeout=1) == (
            "game_over",
            ("White", {"X": 2, "O": 4}),
        )
        assert res_go == "restart"

    # 4. set_thinking_indicator
    app.set_thinking_indicator(True)
    assert app.output_queue.get(timeout=1) == ("set_thinking", True)
    app.set_thinking_indicator(False)
    assert app.output_queue.get(timeout=1) == ("set_thinking", False)


@patch(f"{_APP}.OthelloWindow")
def test_guiapp_on_activate(mock_window):
    app = GUIApp()
    app.on_activate(MagicMock())
    mock_window.assert_called_once()


@patch("sys.exit")
def test_guiapp_start(mock_exit):
    app = GUIApp()
    app.app = MagicMock()
    with patch.object(sys, "argv", ["othello"]):
        app.start()
    app.app.run.assert_called_once_with(["othello"])
    mock_exit.assert_called_once()


@patch(f"{_APP}.os")
@patch(f"{_APP}.sys")
def test_guiapp_start_non_verbose(mock_sys, mock_os):
    mock_sys.exit.side_effect = SystemExit

    app = gui_module.GUIApp()

    mock_defaults = MagicMock()
    mock_defaults.getboolean.return_value = False
    app.config_manager.config_parser = {"defaults": mock_defaults}

    app.app = MagicMock()
    app.app.run.return_value = 0

    with pytest.raises(SystemExit):
        app.start()

    assert mock_os.dup.called
    assert mock_os.open.called
    assert mock_os.dup2.called
    assert mock_os.close.called


# ---------------------------------------------------------------------------
# OTHELLOWINDOW INITIALIZATION TESTS
# ---------------------------------------------------------------------------


def test_othello_window_ui_setup():
    """Tests _load_css and _create_header_bar.

    Without calling super().__init__.
    """
    window = setup_mock_window()

    # _load_css : on patche Gtk dans le module othello_window
    with (
        patch(f"{_WIN}.Gtk.CssProvider") as mock_css,
        patch(f"{_WIN}.Gtk.StyleContext") as mock_style,
    ):
        window.get_screen = MagicMock()
        window._load_css()
        mock_css.return_value.load_from_data.assert_called_once()
        mock_style.add_provider_for_screen.assert_called_once()

    # _create_header_bar : on patche tout Gtk dans othello_window
    with patch(f"{_WIN}.Gtk"):
        hb = window._create_header_bar()
        assert hb is not None


def test_othello_window_full_init():
    """Vérifie l'initialisation de la fenêtre en simulant l'héritage GTK."""
    mock_gtk = MagicMock()

    with patch.dict(window_module.__dict__, {"Gtk": mock_gtk}):
        with patch(
            "gi.repository.Gtk.ApplicationWindow.__init__", return_value=None
        ):
            window = OthelloWindow.__new__(OthelloWindow)

            window.set_default_size = MagicMock()
            window.set_titlebar = MagicMock()
            window.add = MagicMock()
            window.connect = MagicMock()
            window.add_accel_group = MagicMock()
            window.get_screen = MagicMock(return_value=MagicMock())

            mock_app = MagicMock()
            out_q = queue.Queue()
            in_q = queue.Queue()

            with (
                patch.object(OthelloWindow, "_load_css"),
                patch.object(OthelloWindow, "_create_header_bar"),
            ):
                window.__init__(mock_app, out_q, in_q)

                assert window.current_player == "X"
                assert window.output_queue == out_q
                assert window.board_grid is not None
                assert window.status_label is not None
                assert window.spinner is not None


def test_othello_window_ui_packing_logic():
    """Vérifie que les widgets sont bien agencés."""
    mock_gtk = MagicMock()

    with patch.dict(window_module.__dict__, {"Gtk": mock_gtk}):
        with (
            patch(
                "gi.repository.Gtk.ApplicationWindow.__init__",
                return_value=None,
            ),
            patch.object(OthelloWindow, "_load_css"),
            patch.object(OthelloWindow, "_create_header_bar"),
        ):
            window = OthelloWindow.__new__(OthelloWindow)

            added_widgets = []

            def fake_add(widget):
                window.added_widget = widget
                added_widgets.append(widget)

            window.add = fake_add
            window.set_default_size = MagicMock()
            window.set_titlebar = MagicMock()
            window.connect = MagicMock()
            window.add_accel_group = MagicMock()
            window.get_screen = MagicMock(return_value=MagicMock())

            window.__init__(None, None, None)

            assert hasattr(window, "added_widget")
            assert window.main_box.pack_start.called


# ---------------------------------------------------------------------------
# RENDER TESTS
# ---------------------------------------------------------------------------


@patch(f"{_WIN}.Gtk")
def test_render_board_full_logic(mock_gtk):
    window = setup_mock_window()
    window.show_all = MagicMock()
    window.board_grid.get_children.return_value = [MagicMock()]

    board_str = "XO/.."
    window.render_board(board_str, legal_moves=0b1000)

    assert window.board_grid.attach.call_count == 4
    assert mock_gtk.Box.call_count >= 2


@patch(f"{_WIN}.Gtk")
def test_render_board_no_rebuild_when_same_size(mock_gtk):
    """render_board ne reconstruit pas la grille.

    Si la taille n'a pas changé.
    """
    window = setup_mock_window()
    window._board_size = 2

    def make_btn():
        btn = MagicMock()
        btn._piece_widget = MagicMock()
        return btn

    window._board_buttons = [
        [make_btn(), make_btn()],
        [make_btn(), make_btn()],
    ]

    window.render_board("XO/OX", legal_moves=0, current_player="O")

    # La grille n'est pas reconstruite
    window.board_grid.get_children.assert_not_called()
    # Pièces X et O appliquées
    window._board_buttons[0][
        0
    ]._piece_widget.get_style_context().add_class.assert_called_with("piece-X")
    window._board_buttons[0][
        1
    ]._piece_widget.get_style_context().add_class.assert_called_with("piece-O")


@patch(f"{_WIN}.Gtk")
def test_render_board_legal_moves_and_empty_cells(mock_gtk):
    """Les cases vides avec legal_moves reçoivent la classe 'legal-move'."""
    window = setup_mock_window()
    window._board_size = 2

    def make_btn():
        btn = MagicMock()
        btn._piece_widget = MagicMock()
        return btn

    btn_00 = make_btn()
    btn_01 = make_btn()
    btn_10 = make_btn()
    btn_11 = make_btn()
    window._board_buttons = [[btn_00, btn_01], [btn_10, btn_11]]

    # Plateau 2x2 tout vide, legal_move sur index 0 (bit 0 = case r=0,c=0)
    window.render_board("../..", legal_moves=0b0001, current_player="X")

    # Case index 0 (r=0, c=0) : legal move → sensitive True, classe legal-move
    btn_00.get_style_context().add_class.assert_called_with("legal-move")
    btn_00.set_sensitive.assert_called_with(True)

    # Case index 1 (r=0, c=1) : pas legal → sensitive False
    btn_01.set_sensitive.assert_called_with(False)


@patch(f"{_WIN}.Gtk")
def test_render_board_updates_score_labels(mock_gtk):
    """render_board met à jour les labels de score."""
    window = setup_mock_window()
    window._board_size = 2

    def make_btn():
        btn = MagicMock()
        btn._piece_widget = MagicMock()
        return btn

    window._board_buttons = [
        [make_btn(), make_btn()],
        [make_btn(), make_btn()],
    ]

    window.render_board("XX/OO", legal_moves=0, current_player="X")

    window.score_label_black.set_markup.assert_called_once()
    window.score_label_white.set_markup.assert_called_once()
    call_black = window.score_label_black.set_markup.call_args[0][0]
    assert "2" in call_black  # 2 pièces X


@patch(f"{_WIN}.Gtk")
def test_render_board_resets_blitz_disabled(mock_gtk):
    """render_board remet _blitz_disabled à False."""
    window = setup_mock_window()
    window._blitz_disabled = True
    window._board_size = 2

    def make_btn():
        btn = MagicMock()
        btn._piece_widget = MagicMock()
        return btn

    window._board_buttons = [
        [make_btn(), make_btn()],
        [make_btn(), make_btn()],
    ]

    window.render_board("XO/OX", legal_moves=0, current_player="X")

    assert window._blitz_disabled is False


# ---------------------------------------------------------------------------
# DIALOG / POPUP TESTS
# ---------------------------------------------------------------------------


def test_save_dialog_ui_init():
    """Tests the initialization of SaveDialog by mocking the GTK backend."""
    with (
        patch.object(
            save_dialog_module.Gtk.Dialog, "__init__", return_value=None
        ),
        patch.object(
            save_dialog_module.Gtk.Dialog, "add_buttons", create=True
        ),
        patch.object(
            save_dialog_module.Gtk.Dialog, "get_content_area", create=True
        ),
        patch.object(
            save_dialog_module.Gtk.Dialog, "set_default_size", create=True
        ),
        patch.object(save_dialog_module.Gtk.Dialog, "show_all", create=True),
        patch(f"{_SAV}.Gtk.Grid"),
        patch(f"{_SAV}.Gtk.Label"),
        patch(f"{_SAV}.Gtk.Entry"),
    ):
        dialog = SaveDialog(None)
        assert dialog.filename_entry is not None


def test_config_dialog_ui_init():
    """Tests the initialization of ConfigDialog by mocking the GTK backend."""
    with (
        patch.object(
            config_dialog_module.Gtk.Dialog, "__init__", return_value=None
        ),
        patch.object(
            config_dialog_module.Gtk.Dialog, "add_buttons", create=True
        ),
        patch.object(
            config_dialog_module.Gtk.Dialog, "get_content_area", create=True
        ),
        patch.object(config_dialog_module.Gtk.Dialog, "show_all", create=True),
        patch(f"{_CFG}.Gtk.Grid"),
        patch(f"{_CFG}.Gtk.Label"),
        patch(f"{_CFG}.Gtk.Switch"),
        patch(f"{_CFG}.Gtk.SpinButton"),
        patch(f"{_CFG}.Gtk.ComboBoxText"),
        patch(f"{_CFG}.Gtk.Adjustment"),
    ):
        dialog = ConfigDialog(None)
        assert "verbose" in dialog.widgets


def test_save_dialog_get_values_logic():
    with patch.object(SaveDialog, "__init__", return_value=None):
        dialog = SaveDialog(None)
        dialog.filename_entry = MagicMock()
        dialog.comment_entry = MagicMock()

        dialog.filename_entry.get_text.return_value = "partie_1"
        dialog.comment_entry.get_text.return_value = "victoire"

        values = dialog.get_values()
        assert values["filename"] == "partie_1"
        assert values["comment"] == "victoire"


def test_config_dialog_get_values_logic():
    with patch.object(ConfigDialog, "__init__", return_value=None):
        dialog = ConfigDialog(None)
        mock_switch = MagicMock(spec=config_dialog_module.Gtk.Switch)
        mock_spin = MagicMock(spec=config_dialog_module.Gtk.SpinButton)
        mock_combo = MagicMock(spec=config_dialog_module.Gtk.ComboBoxText)

        mock_switch.get_active.return_value = True
        mock_spin.get_value_as_int.return_value = 45
        mock_combo.get_active_text.return_value = "10"

        dialog.widgets = {
            "verbose": mock_switch,
            "timeout": mock_spin,
            "size": mock_combo,
        }

        values = dialog.get_values()
        assert values["verbose"] is True
        assert values["timeout"] == 45
        assert values["size"] == "10"


# ---------------------------------------------------------------------------
# CONFIG DIALOG — get_values branches
# ---------------------------------------------------------------------------


def test_config_dialog_get_values_ai_minimax_depth_zero():
    """SpinButton avec valeur 0 pour ai_minimax_depth doit retourner.

    None (mode Auto).
    """
    with patch.object(ConfigDialog, "__init__", return_value=None):
        dialog = ConfigDialog(None)
        mock_spin = MagicMock()
        mock_spin.get_value_as_int.return_value = 0
        dialog.widgets = {"ai_minimax_depth": mock_spin}

        with patch.object(
            config_dialog_module.Gtk, "SpinButton", type(mock_spin)
        ):
            values = dialog.get_values()
        assert values["ai_minimax_depth"] is None


def test_config_dialog_get_values_ai_minimax_depth_nonzero():
    """SpinButton avec valeur > 0 pour ai_minimax_depth retourne la valeur."""
    with patch.object(ConfigDialog, "__init__", return_value=None):
        dialog = ConfigDialog(None)
        mock_spin = MagicMock()
        mock_spin.get_value_as_int.return_value = 4
        dialog.widgets = {"ai_minimax_depth": mock_spin}

        with patch.object(
            config_dialog_module.Gtk, "SpinButton", type(mock_spin)
        ):
            values = dialog.get_values()
        assert values["ai_minimax_depth"] == 4


def test_config_dialog_get_values_ai_time():
    """SpinButton pour ai_time retourne la valeur (float)."""
    with patch.object(ConfigDialog, "__init__", return_value=None):
        dialog = ConfigDialog(None)
        mock_spin = MagicMock(spec=config_dialog_module.Gtk.SpinButton)

        mock_spin.get_value.return_value = 10.0

        dialog.widgets = {"ai_time": mock_spin}

        values = dialog.get_values()
        assert values["ai_time"] == 10.0


def test_config_dialog_get_values_spinbutton_other():
    """SpinButton pour clé inconnue retourne get_value() (float)."""
    with patch.object(ConfigDialog, "__init__", return_value=None):
        dialog = ConfigDialog(None)
        mock_spin = MagicMock()
        mock_spin.get_value.return_value = 3.14
        dialog.widgets = {"other_spin": mock_spin}

        with patch.object(
            config_dialog_module.Gtk, "SpinButton", type(mock_spin)
        ):
            values = dialog.get_values()
        assert values["other_spin"] == 3.14


# ---------------------------------------------------------------------------
# USER ACTION AND MENU TESTING
# ---------------------------------------------------------------------------


def test_simple_menu_actions():
    window = setup_mock_window()

    window.on_new_game(None)
    assert window.input_queue.get() == "new"
    assert window.input_queue.get() == "show time"

    window.on_undo(None)
    assert window.input_queue.get() == "undo"

    window.on_redo(None)
    assert window.input_queue.get() == "redo"

    window.on_pause(None)
    assert window.input_queue.get() == "pause"

    window.on_hint(None)
    assert window.input_queue.get() == "hint"


@patch(f"{_WIN}.Gtk.FileChooserDialog")
def test_on_load_game(mock_dialog_class):
    window = setup_mock_window()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.OK
    mock_dialog.get_filename.return_value = "test.sav"

    window.on_load_game(None)
    assert window.input_queue.get() == "load test.sav"
    mock_dialog.destroy.assert_called_once()


@patch(f"{_WIN}.Gtk.FileChooserDialog")
def test_on_load_game_cancel(mock_dialog_class):
    """Annuler le FileChooser ne met rien dans la queue."""
    window = setup_mock_window()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.CANCEL

    window.on_load_game(None)

    assert window.input_queue.empty()
    mock_dialog.destroy.assert_called_once()


@patch(f"{_WIN}.ConfigDialog")
@patch(f"{_WIN}.ConfigManager")
@patch(f"{_WIN}.BitboardOps")
def test_on_config_action_human_ai(
    mock_bitboard, mock_cm_class, mock_dialog_class
):
    window = setup_mock_window()
    window.display_message = MagicMock()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.OK

    mock_dialog.get_values.return_value = {
        "player-mode": "Human vs AI",
        "size": 10,
        "lang": "fr",
    }

    window.on_config(None)
    assert window.input_queue.get() == "new"
    mock_bitboard.set_board_size.assert_called_with(10)


@patch(f"{_WIN}.ConfigDialog")
@patch(f"{_WIN}.ConfigManager")
@patch(f"{_WIN}.BitboardOps")
def test_on_config_action_human_human(
    mock_bitboard, mock_cm_class, mock_dialog_class
):
    window = setup_mock_window()
    window.display_message = MagicMock()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.OK

    mock_dialog.get_values.return_value = {
        "player-mode": "Human vs Human",
        "size": 8,
        "lang": "en",
    }

    window.on_config(None)
    assert window.input_queue.get() == "new"


@patch(f"{_WIN}.ConfigDialog")
def test_on_config_cancel(mock_dialog_class):
    window = setup_mock_window()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.CANCEL
    window.on_config(None)
    assert window.input_queue.empty()


@patch(f"{_WIN}.ConfigDialog")
@patch(f"{_WIN}.ConfigManager")
@patch(f"{_WIN}.BitboardOps")
def test_on_config_ai_vs_ai(mock_bitboard, mock_cm_class, mock_dialog_class):
    """Mode AI vs AI : ai_enabled=True, ai_color='A'."""
    window = setup_mock_window()
    window.display_message = MagicMock()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.OK
    mock_dialog.get_values.return_value = {
        "player-mode": "AI vs AI",
        "size": 8,
        "lang": "en",
        "ai_mode": "MCTS",
        "ai_mcts_selection": "uct",
        "ai_minimax_scoring": "Function1",
    }
    mock_cm = mock_cm_class.return_value

    window.on_config(None)

    saved = {k: v for call in mock_cm.set.call_args_list for k, v in [call[0]]}
    assert saved.get("ai_enabled") == "True"
    assert saved.get("ai_color") == "A"
    assert saved.get("ai_mode") == "mcts"
    assert saved.get("ai_mcts_selection") == "UCT"
    assert saved.get("ai_minimax_scoring") == "function1"


@patch(f"{_WIN}.ConfigDialog")
@patch(f"{_WIN}.ConfigManager")
@patch(f"{_WIN}.BitboardOps")
def test_on_config_ai_black_vs_human(
    mock_bitboard, mock_cm_class, mock_dialog_class
):
    """Mode AI (Black) vs Human (White) : ai_color='b'."""
    window = setup_mock_window()
    window.display_message = MagicMock()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.OK
    mock_dialog.get_values.return_value = {
        "player-mode": "AI (Black) vs Human (White)",
        "size": 8,
        "lang": "en",
    }
    mock_cm = mock_cm_class.return_value

    window.on_config(None)

    saved = {k: v for call in mock_cm.set.call_args_list for k, v in [call[0]]}
    assert saved.get("ai_color") == "b"


@patch(f"{_WIN}.ConfigDialog")
@patch(f"{_WIN}.ConfigManager")
@patch(f"{_WIN}.BitboardOps")
def test_on_config_human_vs_ai_white(
    mock_bitboard, mock_cm_class, mock_dialog_class
):
    """Mode Human (Black) vs AI (White) : ai_color='w'."""
    window = setup_mock_window()
    window.display_message = MagicMock()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.OK
    mock_dialog.get_values.return_value = {
        "player-mode": "Human (Black) vs AI (White)",
        "size": 8,
        "lang": "en",
    }
    mock_cm = mock_cm_class.return_value

    window.on_config(None)

    saved = {k: v for call in mock_cm.set.call_args_list for k, v in [call[0]]}
    assert saved.get("ai_color") == "w"


@patch(f"{_WIN}.ConfigDialog")
@patch(f"{_WIN}.ConfigManager")
@patch(f"{_WIN}.BitboardOps")
def test_on_config_none_value_removes_option(
    mock_bitboard, mock_cm_class, mock_dialog_class
):
    """Une valeur None dans la config supprime l'option.

    (ai_minimax_depth en mode Auto).
    """
    window = setup_mock_window()
    window.display_message = MagicMock()
    mock_dialog = mock_dialog_class.return_value
    mock_dialog.run.return_value = window_module.Gtk.ResponseType.OK
    mock_dialog.get_values.return_value = {
        "player-mode": "Human vs Human",
        "size": 8,
        "lang": "en",
        "ai_minimax_depth": None,
    }
    mock_cm = mock_cm_class.return_value
    mock_cm.config_parser.has_option.return_value = True

    window.on_config(None)

    mock_cm.config_parser.remove_option.assert_called_with(
        "defaults", "ai_minimax_depth"
    )


@patch(f"{_WIN}.Gtk.AboutDialog")
def test_on_info_action(mock_about_class):
    window = setup_mock_window()
    window.on_info(None)
    mock_about_class.return_value.run.assert_called_once()


@patch(f"{_WIN}.Gtk")
def test_on_quit_scenarios(mock_gtk):
    window = setup_mock_window()

    # Sans changements
    window.on_quit(None)
    assert window.input_queue.get() == "quit"

    # Avec changements -> YES
    window.unsaved_changes = True
    mock_gtk.MessageDialog.return_value.run.return_value = (
        mock_gtk.ResponseType.YES
    )
    with patch.object(window, "on_save_game") as mock_save:
        window.on_quit(None)
        mock_save.assert_called_once()
        assert window.input_queue.get() == "quit force"

    # Avec changements -> NO
    mock_gtk.MessageDialog.return_value.run.return_value = (
        mock_gtk.ResponseType.NO
    )
    window.on_quit(None)
    assert window.input_queue.get() == "quit force"

    # Avec changements -> CANCEL
    mock_gtk.MessageDialog.return_value.run.return_value = (
        mock_gtk.ResponseType.CANCEL
    )
    window.on_quit(None)
    assert window.input_queue.empty()


def test_on_delete_event():
    window = setup_mock_window()
    window.on_quit = MagicMock()
    result = window.on_delete_event(None, None)
    assert result is True
    window.on_quit.assert_called_once()


@patch(f"{_WIN}.SaveDialog")
@patch(f"{_WIN}.Gtk")
def test_on_save_game_branches(mock_gtk, mock_save_dlg):
    window = setup_mock_window()
    window.display_error = MagicMock()
    dlg = mock_save_dlg.return_value
    dlg.run.return_value = mock_gtk.ResponseType.OK

    dlg.get_values.return_value = {"filename": "", "comment": ""}
    window.on_save_game(None)
    window.display_error.assert_called_once()

    dlg.get_values.return_value = {"filename": "game.sav", "comment": "test"}
    window.on_save_game(None)
    assert window.input_queue.get() == 'save game.sav "test"'

    dlg.get_values.return_value = {"filename": "game.sav", "comment": ""}
    window.on_save_game(None)
    assert window.input_queue.get() == "save game.sav"


@patch(f"{_WIN}.SaveDialog")
@patch(f"{_WIN}.Gtk")
def test_on_save_game_cancel_returns_false(mock_gtk, mock_save_dlg):
    """on_save_game retourne False si l'utilisateur annule."""
    window = setup_mock_window()
    dlg = mock_save_dlg.return_value
    dlg.run.return_value = mock_gtk.ResponseType.CANCEL

    result = window.on_save_game(None)

    assert result is False
    assert window.input_queue.empty()


@patch(f"{_WIN}.Gtk")
@patch(f"{_WIN}.Gdk")
def test_keyboard_shortcuts_are_assigned(mock_gdk, mock_gtk):
    """Vérifie que les raccourcis clavier (Ctrl+...).

    Sont bien assignés aux menus.
    """
    window = setup_mock_window()

    mock_gdk.KEY_n = "KEY_N"
    mock_gdk.KEY_l = "KEY_L"
    mock_gdk.KEY_s = "KEY_S"
    mock_gdk.KEY_comma = "KEY_COMMA"
    mock_gdk.KEY_i = "KEY_I"
    mock_gdk.KEY_q = "KEY_Q"
    mock_gdk.KEY_u = "KEY_U"
    mock_gdk.KEY_r = "KEY_R"
    mock_gdk.KEY_p = "KEY_P"
    mock_gdk.KEY_h = "KEY_H"
    mock_gdk.ModifierType.CONTROL_MASK = "CTRL_MASK"

    # appelle la méthode qui construit les menus et attache les raccourcis
    window._create_header_bar()

    # On récupère le mock de MenuItem
    # (qui représente tous les boutons du menu créés)
    mock_menu_item_instance = mock_gtk.MenuItem.return_value

    # call_args_list contient la liste de tous les appels à add_accelerator()
    calls = mock_menu_item_instance.add_accelerator.call_args_list

    # On extrait les paires (Touche, Modificateur) de chaque appel
    # Les arguments sont :
    # (signal_name, accel_group, accel_key, accel_mods, accel_flags)
    # Donc accel_key est à l'index 2 et accel_mods à l'index 3
    assigned_shortcuts = [(call[0][2], call[0][3]) for call in calls]

    # Liste des raccourcis attendus
    expected_shortcuts = [
        ("KEY_N", "CTRL_MASK"),  # New Game
        ("KEY_L", "CTRL_MASK"),  # Load Game
        ("KEY_S", "CTRL_MASK"),  # Save Game
        ("KEY_COMMA", "CTRL_MASK"),  # Config
        ("KEY_I", "CTRL_MASK"),  # Info
        ("KEY_Q", "CTRL_MASK"),  # Quit
        ("KEY_U", "CTRL_MASK"),  # Undo
        ("KEY_R", "CTRL_MASK"),  # Redo
        ("KEY_P", "CTRL_MASK"),  # Pause
        ("KEY_H", "CTRL_MASK"),  # Hint
    ]

    # On vérifie que chaque raccourci prévu a bien été assigné
    for expected in expected_shortcuts:
        assert (
            expected in assigned_shortcuts
        ), f"Le raccourci clavier {expected} est manquant !"


# ---------------------------------------------------------------------------
# QUEUE AND POPUP TESTS
# ---------------------------------------------------------------------------


@patch(f"{_WIN}.Gtk.MessageDialog")
def test_display_message_and_error(mock_msg_dialog):
    window = setup_mock_window()

    window.display_message("Standard info")
    window.status_label.set_text.assert_called_with("Standard info")

    window.display_message("Hint: a4 is good")
    mock_msg_dialog.return_value.run.assert_called_once()

    window.display_error("Boom")
    assert mock_msg_dialog.return_value.run.call_count == 2


@patch(f"{_WIN}.Gtk")
def test_process_output_queue_tasks(mock_gtk):
    window = setup_mock_window()
    window.render_board = MagicMock()
    window.display_message = MagicMock()
    window.display_error = MagicMock()

    window.output_queue.put(("render", ("XO", 1, "O", False)))
    window.output_queue.put(("display_error", "Erreur réseau"))
    window.output_queue.put(("display_message", "Info"))
    window.output_queue.put(("get_input", "Player X's turn"))
    window.output_queue.put(("get_input", "Unknown prompt"))
    window.output_queue.put(("quit", None))

    window.process_output_queue()

    window.render_board.assert_called_with("XO", 1, "O", False)
    window.display_error.assert_called_with("Erreur réseau")
    window.display_message.assert_called_with("Info")

    window.status_label.set_text.assert_any_call("Black's turn to play")
    window.status_label.set_text.assert_any_call("Unknown prompt")
    window.get_application().quit.assert_called_once()


@patch(f"{_WIN}.GLib")
@patch(f"{_WIN}.Gtk")
def test_process_output_queue_no_dialog_open(mock_gtk, mock_glib):
    """server_log et player_list sont ignorés silencieusement.

    Si les dialogs sont fermés.
    """
    window = setup_mock_window()
    window.host_server_dialog = None
    window.join_server_dialog = None
    window.lobby_dialog = None

    window.output_queue.put(("server_log", "should be ignored"))
    window.output_queue.put(("discovered_servers", ["x"]))
    window.output_queue.put(("player_list", ["p"]))

    # Ne doit pas lever d'exception
    window.process_output_queue()


@patch(f"{_WIN}.GLib")
@patch(f"{_WIN}.Gtk")
def test_process_output_queue_extended(mock_gtk, mock_glib):
    window = setup_mock_window()
    window.show_game_over_dialog = MagicMock()
    window.show_lobby_dialog = MagicMock()
    window.spinner = MagicMock()
    window.header_bar = MagicMock()

    window.host_server_dialog = MagicMock()
    window.join_server_dialog = MagicMock()

    mock_lobby = MagicMock()
    window.lobby_dialog = mock_lobby

    # 1. Player O prompt
    window.output_queue.put(("get_input", "Player O"))
    # 2. Unknown prompt
    window.output_queue.put(("get_input", "Something else"))
    # 3. Game over
    window.output_queue.put(("game_over", ("X", {"X": 2, "O": 1})))
    # 4. Set thinking (True et False)
    window.output_queue.put(("set_thinking", True))
    window.output_queue.put(("set_thinking", False))
    # 5. Network actions
    window.output_queue.put(("server_log", "Log message"))
    window.output_queue.put(("discovered_servers", ["Server 1"]))
    window.output_queue.put(("show_lobby", None))
    window.output_queue.put(("player_list", ["Player 1"]))
    window.output_queue.put(("game_starting", None))
    # 6. Network status (True et False)
    window.output_queue.put(("set_network_status", "🟢 Online"))
    window.output_queue.put(("set_network_status", None))

    window.process_output_queue()

    window.status_label.set_text.assert_any_call("White's turn to play")
    window.status_label.set_text.assert_any_call("Something else")
    # show_game_over_dialog est appelée via GLib.idle_add, pas directement
    mock_glib.idle_add.assert_called_with(
        window.show_game_over_dialog, "X", {"X": 2, "O": 1}
    )

    assert window.spinner.start.called
    assert window.spinner.show.called
    assert window.spinner.stop.called
    assert window.spinner.hide.called

    window.host_server_dialog.add_log.assert_called_with("Log message")
    window.join_server_dialog.update_server_list.assert_called_with(
        ["Server 1"]
    )
    assert window.show_lobby_dialog.called

    mock_lobby.update_player_list.assert_called_with(["Player 1"])
    assert mock_lobby.destroy.called
    assert window.lobby_dialog is None

    window.header_bar.set_subtitle.assert_any_call("🟢 Online")
    window.header_bar.set_subtitle.assert_any_call(None)
    assert window.is_online is False


# ---------------------------------------------------------------------------
# BOARD CLICK AND DRAG-AND-DROP TESTS
# ---------------------------------------------------------------------------


@patch(f"{_WIN}.Gtk")
def test_on_board_click_logic(mock_gtk):
    window = setup_mock_window()
    window.current_player = "O"
    window.is_my_turn = True
    mock_widget = MagicMock()
    mock_widget.get_children.return_value = []
    window.on_board_button_clicked(mock_widget, 3, 4)
    assert window.input_queue.get(timeout=1) == "O d5"


def test_on_board_button_clicked_verrous():
    window = setup_mock_window()
    mock_widget = MagicMock()

    # 1. Pas mon tour -> doit ignorer (return)
    window.is_my_turn = False
    window.on_board_button_clicked(mock_widget, 0, 0)
    assert window.input_queue.empty()

    # 2. Mon tour mais en ligne -> Pas d'affichage optimiste
    window.is_my_turn = True
    window.is_online = True
    window.on_board_button_clicked(mock_widget, 0, 0)
    assert mock_widget.add.called is False
    assert window.input_queue.get(timeout=1) == "X a1"
    assert window.is_my_turn is False


@patch(f"{_WIN}.Gdk")
@patch(f"{_WIN}.cairo")
@patch(f"{_WIN}.Gtk")
def test_drag_and_drop_methods(mock_gtk, mock_cairo, mock_gdk):
    window = setup_mock_window()
    mock_context = MagicMock()
    mock_widget = MagicMock()
    mock_selection = MagicMock()

    # on_drag_begin (Black)
    window.current_player = "X"
    window.on_drag_begin(mock_widget, mock_context)
    mock_gtk.drag_set_icon_surface.assert_called_once()

    # on_drag_begin (White)
    window.current_player = "O"
    window.on_drag_begin(mock_widget, mock_context)
    assert mock_gtk.drag_set_icon_surface.call_count == 2

    # on_drag_data_get
    window.on_drag_data_get(mock_widget, mock_context, mock_selection, 0, 0)
    mock_selection.set.assert_called_once()

    # on_drag_data_received (Succès)
    window.is_my_turn = True
    mock_selection.get_data.return_value = b"piece"
    window.on_drag_data_received(
        mock_widget, mock_context, 0, 0, mock_selection, 0, 0, (2, 3)
    )
    mock_context.finish.assert_called_with(True, False, 0)
    assert window.input_queue.get(timeout=1) == "O c4"

    # on_drag_data_received (Échec mauvais data)
    mock_selection.get_data.return_value = b"other"
    window.on_drag_data_received(
        mock_widget, mock_context, 0, 0, mock_selection, 0, 0, (2, 3)
    )
    mock_context.finish.assert_called_with(False, False, 0)

    # on_drag_data_received (Échec info != 0)
    window.on_drag_data_received(
        mock_widget, mock_context, 0, 0, mock_selection, 1, 0, (2, 3)
    )
    mock_context.finish.assert_called_with(False, False, 0)


# ---------------------------------------------------------------------------
# GAME OVER DIALOG TESTS
# ---------------------------------------------------------------------------


@patch(f"{_WIN}.Gtk.MessageDialog")
def test_show_game_over_dialog(mock_msg_dialog):
    window = setup_mock_window()

    mock_msg_dialog.return_value.run.return_value = (
        window_module.Gtk.ResponseType.OK
    )
    window.show_game_over_dialog("Black", {"X": 10, "O": 5})
    assert window.input_queue.get(timeout=1) == "restart"

    mock_msg_dialog.return_value.run.return_value = (
        window_module.Gtk.ResponseType.CLOSE
    )
    window.show_game_over_dialog("Black", {"X": 10, "O": 5})
    assert window.input_queue.get(timeout=1) == "quit"

    window.is_online = True
    mock_msg_dialog.return_value.run.return_value = (
        window_module.Gtk.ResponseType.OK
    )
    window.show_game_over_dialog("Black", {"X": 10, "O": 5})
    assert window.input_queue.get(timeout=1) == "lobby"


# ---------------------------------------------------------------------------
# NETWORK DIALOGS TESTS — HostServerDialog
# ---------------------------------------------------------------------------


def test_host_server_dialog():
    input_queue = queue.Queue()
    with patch.object(HostServerDialog, "__init__", return_value=None):
        dialog = HostServerDialog(None, input_queue)
        dialog.input_queue = input_queue

        dialog.start_button = MagicMock()
        dialog.stop_button = MagicMock()
        dialog.log_buffer = MagicMock()
        dialog.log_view = MagicMock()
        dialog.status_indicator = MagicMock()
        dialog.port_entry = MagicMock()
        dialog.port_entry.get_text.return_value = "8080"

        dialog.on_start_server(None)
        assert input_queue.get(timeout=1) == "server start 8080"
        dialog.start_button.set_sensitive.assert_called_with(False)
        dialog.stop_button.set_sensitive.assert_called_with(True)
        dialog.status_indicator.set_markup.assert_called_once()

        dialog.status_indicator.set_markup.reset_mock()
        dialog.on_stop_server(None)
        assert input_queue.get(timeout=1) == "server stop"
        dialog.start_button.set_sensitive.assert_called_with(True)
        dialog.stop_button.set_sensitive.assert_called_with(False)
        dialog.status_indicator.set_markup.assert_called_once()

        dialog.add_log("Network init OK")
        dialog.log_buffer.insert.assert_called_once()
        dialog.log_view.get_vadjustment.assert_called_once()


# ---------------------------------------------------------------------------
# NETWORK DIALOGS TESTS — JoinServerDialog
# ---------------------------------------------------------------------------


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}.Gtk.ListBoxRow")
@patch(f"{_SRV}.GLib")
def test_join_server_dialog(mock_glib, mock_listbox_row, mock_label):
    input_queue = queue.Queue()
    with patch.object(JoinServerDialog, "__init__", return_value=None):
        dialog = JoinServerDialog(None, input_queue)
        dialog.input_queue = input_queue

        dialog.server_listbox = MagicMock()
        dialog.manual_entry = MagicMock()
        dialog.refresh_timer = 12345
        dialog.refresh_label = MagicMock()
        dialog.show_all = MagicMock()

        dialog.request_server_list()
        assert input_queue.get(timeout=1) == "server list"

        dialog.update_server_list(["127.0.0.1:12345"])
        assert dialog.server_listbox.add.called

        dialog.manual_entry.get_text.return_value = "192.168.1.1:8000"
        assert dialog.get_selected_server() == "192.168.1.1:8000"

        dialog.manual_entry.get_text.return_value = ""
        mock_row = MagicMock()
        mock_row.get_child().get_label.return_value = "10.0.0.2:1234"
        dialog.server_listbox.get_selected_row.return_value = mock_row
        assert dialog.get_selected_server() == "10.0.0.2:1234"

        with patch.object(server_dialogs_module.Gtk.Dialog, "destroy"):
            dialog.destroy()
            mock_glib.source_remove.assert_called_with(12345)


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}.Gtk.ListBoxRow")
@patch(f"{_SRV}.GLib")
def test_join_server_dialog_empty_list(
    mock_glib, mock_listbox_row, mock_label
):
    """update_server_list avec liste vide affiche.

    Un message 'No servers found'.
    """
    input_queue = queue.Queue()
    with patch.object(JoinServerDialog, "__init__", return_value=None):
        dialog = JoinServerDialog(None, input_queue)
        dialog.server_listbox = MagicMock()
        dialog.server_listbox.get_children.return_value = []
        dialog.refresh_label = MagicMock()
        dialog.show_all = MagicMock()

        dialog.update_server_list([])

        # Une seule row ajoutée : le message "No servers found"
        assert dialog.server_listbox.add.call_count == 1


@patch(f"{_SRV}.GLib")
def test_join_server_dialog_get_selected_server_none(mock_glib):
    """get_selected_server retourne None.

    Si rien n'est sélectionné et pas de saisie manuelle.
    """
    input_queue = queue.Queue()
    with patch.object(JoinServerDialog, "__init__", return_value=None):
        dialog = JoinServerDialog(None, input_queue)
        dialog.manual_entry = MagicMock()
        dialog.manual_entry.get_text.return_value = ""
        dialog.server_listbox = MagicMock()
        dialog.server_listbox.get_selected_row.return_value = None

        assert dialog.get_selected_server() is None


@patch(f"{_SRV}.GLib")
def test_join_server_dialog_destroy_no_timer(mock_glib):
    """Destroy() sans timer actif ne provoque pas d'erreur."""
    input_queue = queue.Queue()
    with patch.object(JoinServerDialog, "__init__", return_value=None):
        dialog = JoinServerDialog(None, input_queue)
        dialog.refresh_timer = None

        with patch.object(server_dialogs_module.Gtk.Dialog, "destroy"):
            dialog.destroy()

        mock_glib.source_remove.assert_not_called()


@patch(f"{_SRV}.GLib")
def test_join_server_dialog_destroy_with_active_timer(mock_glib):
    """Destroy() avec un timer actif doit appeler source_remove."""
    input_queue = queue.Queue()
    with patch.object(JoinServerDialog, "__init__", return_value=None):
        dialog = JoinServerDialog(None, input_queue)
        dialog.refresh_timer = 7777

    with patch.object(server_dialogs_module.Gtk.Dialog, "destroy"):
        dialog.destroy()

    mock_glib.source_remove.assert_called_once_with(7777)
    assert dialog.refresh_timer is None


# ---------------------------------------------------------------------------
# NETWORK DIALOGS TESTS — LobbyDialog
# ---------------------------------------------------------------------------


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}.Gtk.ListBoxRow")
@patch(f"{_SRV}.GLib")
def test_lobby_dialog(mock_glib, mock_listbox_row, mock_label):
    input_queue = queue.Queue()
    with patch.object(LobbyDialog, "__init__", return_value=None):
        dialog = LobbyDialog(None, input_queue)
        dialog.input_queue = input_queue

        dialog.player_listbox = MagicMock()
        dialog.refresh_timer = 999
        dialog.show_all = MagicMock()

        dialog.request_player_list()
        assert input_queue.get(timeout=1) == "players"

        dialog.update_player_list(["Player_1 [idle]", "Player_2 [idle]"])
        assert dialog.player_listbox.add.called

        mock_row = MagicMock()
        mock_row.get_child().get_label.return_value = "Player_2 [idle]"
        dialog.player_listbox.get_selected_row.return_value = mock_row
        assert dialog.get_selected_player() == "Player_2"

        with patch.object(server_dialogs_module.Gtk.Dialog, "destroy"):
            dialog.destroy()
            mock_glib.source_remove.assert_called_with(999)


@patch(f"{_SRV}.GLib")
def test_lobby_dialog_destroy_no_timer(mock_glib):
    """LobbyDialog.destroy() sans timer actif ne provoque pas d'erreur."""
    input_queue = queue.Queue()
    with patch.object(LobbyDialog, "__init__", return_value=None):
        dialog = LobbyDialog(None, input_queue)
        dialog.refresh_timer = None

        with patch.object(server_dialogs_module.Gtk.Dialog, "destroy"):
            dialog.destroy()

        mock_glib.source_remove.assert_not_called()


@patch(f"{_SRV}.GLib")
def test_lobby_dialog_destroy_with_active_timer(mock_glib):
    """LobbyDialog.destroy() avec timer actif doit appeler source_remove."""
    dialog = make_lobby()
    dialog.refresh_timer = 8888

    with patch.object(server_dialogs_module.Gtk.Dialog, "destroy"):
        dialog.destroy()

    mock_glib.source_remove.assert_called_once_with(8888)
    assert dialog.refresh_timer is None


def test_lobby_request_player_list_sends_both_commands():
    """request_player_list doit envoyer 'players' ET 'server status'."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)

    result = dialog.request_player_list()

    commands = []
    while not input_queue.empty():
        commands.append(input_queue.get_nowait())

    assert "players" in commands
    assert "server status" in commands
    # Doit retourner True pour que GLib continue le timer
    assert result is True


def test_lobby_update_server_status():
    """update_server_status doit appeler set_markup avec le texte en gras."""
    dialog = make_lobby()
    dialog.update_server_status("Connected — 3 clients")
    dialog.server_status_label.set_markup.assert_called_once_with(
        "<b> Connected — 3 clients</b>"
    )


def test_lobby_on_scoreboard_clicked():
    """on_scoreboard_clicked envoie la commande 'scoreboard'."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)

    dialog.on_scoreboard_clicked(None)

    assert input_queue.get(timeout=1) == "scoreboard"


def test_lobby_on_cancel_clicked():
    """on_cancel_clicked envoie 'cancel' et demande un refresh."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)

    dialog.on_cancel_clicked(None)

    commands = []
    while not input_queue.empty():
        commands.append(input_queue.get_nowait())

    assert "cancel" in commands
    # request_player_list est appelé juste après → "players" doit aussi être là
    assert "players" in commands


def test_lobby_on_status_toggled_away():
    """Bouton enfoncé (active=True) → envoie 'away' et change le label."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)

    mock_toggle = MagicMock()
    mock_toggle.get_active.return_value = True  # bouton enfoncé → Absent

    dialog.on_status_toggled(mock_toggle)

    assert input_queue.get(timeout=1) == "away"
    mock_toggle.set_label.assert_called_once_with("Status: Away")


def test_lobby_on_status_toggled_back():
    """Bouton relâché (active=False) → envoie 'back' et change le label."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)

    mock_toggle = MagicMock()
    mock_toggle.get_active.return_value = False  # bouton relâché → En ligne

    dialog.on_status_toggled(mock_toggle)

    assert input_queue.get(timeout=1) == "back"
    mock_toggle.set_label.assert_called_once_with("Status: Online")


def test_lobby_on_change_name_clicked_simple_name():
    """Pseudo sans espace → commande 'name <pseudo>' envoyée directement."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)
    dialog.name_entry.get_text.return_value = "Alice"

    dialog.on_change_name_clicked(None)

    assert input_queue.get(timeout=1) == "name Alice"
    dialog.name_entry.set_text.assert_called_once_with("")


def test_lobby_on_change_name_clicked_name_with_spaces():
    r"""Pseudo avec espaces → commande 'name \"<pseudo>\"' avec guillemets."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)
    dialog.name_entry.get_text.return_value = "Grand Maître"

    dialog.on_change_name_clicked(None)

    assert input_queue.get(timeout=1) == 'name "Grand Maître"'
    dialog.name_entry.set_text.assert_called_once_with("")


def test_lobby_on_change_name_clicked_empty_name():
    """Pseudo vide → aucune commande envoyée."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)
    dialog.name_entry.get_text.return_value = "   "  # espaces uniquement

    dialog.on_change_name_clicked(None)

    assert input_queue.empty()
    dialog.name_entry.set_text.assert_not_called()


def test_lobby_get_selected_player_none():
    """get_selected_player retourne None si aucune ligne sélectionnée."""
    dialog = make_lobby()
    dialog.player_listbox.get_selected_row.return_value = None

    assert dialog.get_selected_player() is None


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}.Gtk.ListBoxRow")
def test_lobby_update_player_list_string_format(mock_row, mock_label):
    """update_player_list accepte une string multi-lignes."""
    dialog = make_lobby()
    dialog.player_listbox.get_children.return_value = []

    dialog.update_player_list("Alice [idle]\nBob [playing]")

    # 2 joueurs → 2 rows ajoutées
    assert dialog.player_listbox.add.call_count == 2


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}.Gtk.ListBoxRow")
def test_lobby_update_player_list_dict_format(mock_row, mock_label):
    """update_player_list accepte un dictionnaire {nom: statut}."""
    dialog = make_lobby()
    dialog.player_listbox.get_children.return_value = []

    dialog.update_player_list({"Alice": "idle", "Bob": "playing"})

    assert dialog.player_listbox.add.call_count == 2


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}.Gtk.ListBoxRow")
def test_lobby_update_player_list_tuple_format(mock_row, mock_label):
    """update_player_list accepte une liste de tuples (nom, statut)."""
    dialog = make_lobby()
    dialog.player_listbox.get_children.return_value = []

    dialog.update_player_list([("Alice", "idle"), ("Bob", "playing")])

    assert dialog.player_listbox.add.call_count == 2


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}.Gtk.ListBoxRow")
def test_lobby_update_player_list_empty(mock_row, mock_label):
    """update_player_list avec liste vide affiche.

    Un message 'No other players'.
    """
    dialog = make_lobby()
    dialog.player_listbox.get_children.return_value = []

    dialog.update_player_list([])

    # 1 seule row : le message vide
    assert dialog.player_listbox.add.call_count == 1


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}.Gtk.ListBoxRow")
def test_lobby_update_player_list_cleans_previous_children(
    mock_row, mock_label
):
    """update_player_list supprime les anciennes rows avant d'en ajouter."""
    dialog = make_lobby()
    old_child = MagicMock()
    dialog.player_listbox.get_children.return_value = [old_child]

    dialog.update_player_list(["Alice [idle]"])

    old_child.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# WINDOW NETWORK ACTIONS TESTS
# ---------------------------------------------------------------------------


@patch(f"{_WIN}.HostServerDialog")
def test_on_host_server_actions(mock_host_dialog):
    window = setup_mock_window()

    window.on_host_server(None)
    assert window.host_server_dialog is not None
    mock_host_dialog.return_value.show.assert_called_once()

    window.on_host_dialog_close(
        window.host_server_dialog, window_module.Gtk.ResponseType.CLOSE
    )
    assert window.input_queue.get(timeout=1) == "server stop"
    assert window.host_server_dialog is None


@patch(f"{_WIN}.HostServerDialog")
def test_on_host_server_already_open(mock_host_dialog):
    """Si le dialog est déjà ouvert, on appelle present() sans recréer."""
    window = setup_mock_window()
    existing = MagicMock()
    window.host_server_dialog = existing

    window.on_host_server(None)

    mock_host_dialog.assert_not_called()
    existing.present.assert_called_once()


@patch(f"{_WIN}.JoinServerDialog")
def test_on_join_server_actions(mock_join_dialog):
    window = setup_mock_window()
    window.display_error = MagicMock()

    window.on_join_server(None)
    mock_dialog_instance = mock_join_dialog.return_value

    mock_dialog_instance.get_selected_server.return_value = "127.0.0.1:8000"
    window.on_join_dialog_response(
        mock_dialog_instance, window_module.Gtk.ResponseType.OK
    )
    assert window.input_queue.get(timeout=1) == "join 127.0.0.1:8000"
    assert window.join_server_dialog is None

    window.on_join_server(None)
    mock_dialog_instance.get_selected_server.return_value = ""
    window.on_join_dialog_response(
        mock_dialog_instance, window_module.Gtk.ResponseType.OK
    )
    window.display_error.assert_called_once()
    assert window.join_server_dialog is None


@patch(f"{_WIN}.JoinServerDialog")
def test_on_join_server_already_open(mock_join_dialog):
    """Si le dialog est déjà ouvert, on appelle present() sans recréer."""
    window = setup_mock_window()
    existing = MagicMock()
    window.join_server_dialog = existing

    window.on_join_server(None)

    mock_join_dialog.assert_not_called()
    existing.present.assert_called_once()


@patch(f"{_WIN}.JoinServerDialog")
def test_on_join_dialog_response_cancel(mock_join_dialog):
    """Réponse CANCEL : pas de commande envoyée, dialog détruit."""
    window = setup_mock_window()
    mock_dialog_instance = mock_join_dialog.return_value

    window.on_join_dialog_response(
        mock_dialog_instance, window_module.Gtk.ResponseType.CANCEL
    )

    assert window.input_queue.empty()
    mock_dialog_instance.destroy.assert_called_once()
    assert window.join_server_dialog is None


@patch(f"{_WIN}.LobbyDialog")
def test_on_lobby_server_actions(mock_lobby_dialog):
    window = setup_mock_window()
    window.display_error = MagicMock()

    window.show_lobby_dialog()
    mock_dialog_instance = mock_lobby_dialog.return_value

    mock_dialog_instance.get_selected_player.return_value = "Player_2"
    window.on_lobby_dialog_response(
        mock_dialog_instance, window_module.Gtk.ResponseType.OK
    )
    assert window.input_queue.get(timeout=1) == "new Player_2"
    assert window.lobby_dialog is None

    window.show_lobby_dialog()
    mock_dialog_instance.get_selected_player.return_value = None
    window.on_lobby_dialog_response(
        mock_dialog_instance, window_module.Gtk.ResponseType.OK
    )
    window.display_error.assert_called_once()
    assert window.lobby_dialog is not None


@patch(f"{_WIN}.LobbyDialog")
def test_show_lobby_dialog_already_open(mock_lobby_dialog):
    """Si le lobby est déjà ouvert, on appelle present() sans recréer."""
    window = setup_mock_window()
    existing = MagicMock()
    window.lobby_dialog = existing

    window.show_lobby_dialog()

    mock_lobby_dialog.assert_not_called()
    existing.present.assert_called_once()


def test_on_disconnect():
    window = setup_mock_window()
    window.display_message = MagicMock()

    window.on_disconnect(None)
    assert window.input_queue.get(timeout=1) == "quit"
    window.display_message.assert_called_with("Disconnected.")


# ---------------------------------------------------------------------------
# REQUEST_TIME_UPDATE — queue non vide → pas d'envoi
# ---------------------------------------------------------------------------


def test_request_time_update_queue_not_empty():
    """Si la queue d'input n'est pas vide, on n'envoie pas 'show time'."""
    window = setup_mock_window()
    window._blitz_disabled = False
    window.is_my_turn = True
    window.input_queue.put("some pending command")

    window.request_time_update()

    # La queue contient toujours l'élément original, rien d'autre ajouté
    assert window.input_queue.get(timeout=1) == "some pending command"
    assert window.input_queue.empty()


# ---------------------------------------------------------------------------
# UPDATE_TIMERS — joueur O actif
# ---------------------------------------------------------------------------


def test_update_timers_from_text_player_o_active():
    """Quand c'est le tour de O, son timer est en gras."""
    window = setup_mock_window()
    window.time_label_black = MagicMock()
    window.time_label_white = MagicMock()
    window.current_player = "O"

    window.update_timers_from_text("Remaining Time : X (01:00)- O (02:30)")

    call_white = window.time_label_white.set_markup.call_args[0][0]
    call_black = window.time_label_black.set_markup.call_args[0][0]
    assert "bold" in call_white
    assert "02:30" in call_white
    assert "bold" not in call_black
    assert "01:00" in call_black


# ---------------------------------------------------------------------------
# BUFFER_SERVER_STATUS — remplacement du timer existant
# ---------------------------------------------------------------------------


@patch(f"{_WIN}.GLib")
def test_buffer_server_status_replaces_existing_timer(mock_glib):
    """buffer_server_status annule le timer précédent.

    Avant d'en créer un nouveau.
    """
    window = setup_mock_window()
    window._server_status_buffer = []
    window._server_status_timer = 42  # Timer fictif déjà en cours

    window.buffer_server_status("Connected Clients: 2")

    mock_glib.source_remove.assert_called_with(42)
    mock_glib.timeout_add.assert_called()


# ---------------------------------------------------------------------------
# ADDITIONAL TESTS FOR SERVER DIALOGS
# ---------------------------------------------------------------------------


@patch(f"{_SRV}.Gdk")
@patch(f"{_SRV}.Gtk")
def test_server_dialogs_apply_css(mock_gtk, mock_gdk):
    """Teste l'injection globale du CSS."""
    server_dialogs_module._apply_css()
    mock_gtk.CssProvider.return_value.load_from_data.assert_called_once()
    mock_gtk.StyleContext.add_provider_for_screen.assert_called_once()


def test_server_dialogs_add_style():
    """Teste l'ajout de classes CSS multiples."""
    mock_widget = MagicMock()
    server_dialogs_module._add_style(mock_widget, "class1", "class2")
    mock_ctx = mock_widget.get_style_context.return_value
    mock_ctx.add_class.assert_any_call("class1")
    mock_ctx.add_class.assert_any_call("class2")


@patch(f"{_SRV}.Gtk.Label")
@patch(f"{_SRV}._add_style")
def test_server_dialogs_make_section_label(mock_add_style, mock_label):
    """Teste la création de labels de section."""
    server_dialogs_module._make_section_label("Test Section")
    mock_label.return_value.set_markup.assert_called_with(
        "<b>Test Section</b>"
    )
    mock_add_style.assert_called_with(mock_label.return_value, "section-title")


def test_host_server_dialog_init():
    """Teste la construction de l'interface du HostServerDialog."""
    with (
        patch.object(
            server_dialogs_module.Gtk.Dialog, "__init__", return_value=None
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "add_buttons", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "get_content_area", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "set_default_size", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "show_all", create=True
        ),
        patch(f"{_SRV}._apply_css"),
    ):
        dialog = HostServerDialog(None, queue.Queue())
        assert dialog.start_button is not None
        assert dialog.stop_button is not None
        assert dialog.log_view is not None
        assert dialog.port_entry is not None


def test_join_server_dialog_init():
    """Teste la construction de l'interface du JoinServerDialog."""
    with (
        patch.object(
            server_dialogs_module.Gtk.Dialog, "__init__", return_value=None
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "add_buttons", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "get_content_area", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "set_default_size", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "show_all", create=True
        ),
        patch(f"{_SRV}.GLib.timeout_add_seconds", return_value=123),
        patch.object(
            JoinServerDialog, "request_server_list", return_value=True
        ),
        patch(f"{_SRV}._apply_css"),
    ):
        dialog = JoinServerDialog(None, queue.Queue())
        assert dialog.server_listbox is not None
        assert dialog.refresh_timer == 123


def test_lobby_dialog_init():
    """Teste la construction de l'interface du LobbyDialog."""
    with (
        patch.object(
            server_dialogs_module.Gtk.Dialog, "__init__", return_value=None
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "add_buttons", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "get_content_area", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "set_default_size", create=True
        ),
        patch.object(
            server_dialogs_module.Gtk.Dialog, "show_all", create=True
        ),
        patch(f"{_SRV}.GLib.timeout_add_seconds", return_value=456),
        patch.object(LobbyDialog, "request_player_list", return_value=True),
        patch(f"{_SRV}._apply_css"),
    ):
        dialog = LobbyDialog(None, queue.Queue())
        assert dialog.player_listbox is not None
        assert dialog.refresh_timer == 456


@patch(f"{_SRV}.Gtk.MessageDialog")
def test_lobby_on_info_clicked_no_player(mock_msg_dialog):
    """Tester le clic sur Player Info sans joueur sélectionné"""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)
    dialog.player_listbox.get_selected_row.return_value = None
    dialog.get_toplevel = MagicMock()

    dialog.on_info_clicked(None)

    mock_msg_dialog.return_value.run.assert_called_once()
    mock_msg_dialog.return_value.destroy.assert_called_once()
    assert input_queue.empty()


def test_lobby_on_info_clicked_with_player():
    """Tester le clic sur Player Info avec un joueur sélectionné."""
    input_queue = queue.Queue()
    dialog = make_lobby(input_queue)
    mock_row = MagicMock()
    mock_row.get_child().get_label.return_value = "Player_1 [idle]"
    dialog.player_listbox.get_selected_row.return_value = mock_row

    dialog.on_info_clicked(None)

    assert input_queue.get(timeout=1) == "players Player_1"


@patch(f"{_SRV}.Gtk.ListBoxRow")
@patch(f"{_SRV}.Gtk.Label")
def test_lobby_update_player_list_tuple_format_short(mock_label, mock_row):
    """Tester le format de tuple court/invalide pour update_player_list."""
    dialog = make_lobby()
    dialog.player_listbox.get_children.return_value = []

    # On passe un tuple à un seul élément et un string simple
    dialog.update_player_list([("Alice",), "Bob"])

    assert dialog.player_listbox.add.call_count == 2
