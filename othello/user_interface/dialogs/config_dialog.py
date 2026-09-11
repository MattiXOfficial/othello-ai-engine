"""ConfigDialog module."""

import sys

import gi

if "sphinx" not in sys.modules:
    gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from othello.common.config_manager import ConfigManager
from othello.common.i18n_manager import I18nManager


def _(message):
    return I18nManager().gettext(message)


class ConfigDialog(Gtk.Dialog):
    """A dialog for managing game configuration.

    This dialog provides various options to configure the game,
    including board size, player modes (Human vs AI), AI algorithm settings,
    and language.
    """

    def __init__(self, parent):
        super().__init__(
            title=_("Configuration"), transient_for=parent, flags=0
        )
        self.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Save"),
            Gtk.ResponseType.OK,
        )

        self.config_manager = ConfigManager()
        self.widgets = {}

        grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin=20)
        self.get_content_area().add(grid)

        config = self.config_manager.config_parser["defaults"]
        row = 0

        def add_row(label, widget, is_switch=False):
            """Helper function to add a labeled widget to the grid.

            Args:
                label (str): The text label for the widget.
                widget (Gtk.Widget): The GTK widget to add.
                is_switch (bool): True if the widget is a Gtk.Switch,
                                  to adjust alignment.
            """
            nonlocal row
            label_widget = Gtk.Label(label=label)
            label_widget.set_halign(Gtk.Align.START)

            # Prevent switches from stretching horizontally
            if is_switch:
                widget.set_halign(Gtk.Align.END)
                widget.set_valign(Gtk.Align.CENTER)

            grid.attach(label_widget, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            row += 1

        # Verbose (bool)
        widget = Gtk.Switch()
        widget.set_active(config.getboolean("verbose", False))
        self.widgets["verbose"] = widget
        add_row(_("Verbose:"), widget, is_switch=True)

        # Debug (bool)
        widget = Gtk.Switch()
        widget.set_active(config.getboolean("debug", False))
        self.widgets["debug"] = widget
        add_row(_("Debug:"), widget, is_switch=True)

        # Blitz (bool)
        widget = Gtk.Switch()
        widget.set_active(config.getboolean("blitz", False))
        self.widgets["blitz"] = widget
        add_row(_("Blitz:"), widget, is_switch=True)

        # Timeout (int)
        adj = Gtk.Adjustment(
            value=int(config.getfloat("timeout", 30)),
            lower=1,
            upper=3600,
            step_incr=1,
            page_incr=10,
            page_size=0,
        )
        widget = Gtk.SpinButton()
        widget.set_adjustment(adj)
        self.widgets["timeout"] = widget
        add_row(_("Timeout (m):"), widget)

        # Board Size (choice)
        widget = Gtk.ComboBoxText()
        allowed_sizes = ["6", "8", "10", "12"]
        for size in allowed_sizes:
            widget.append_text(size)
        if (current_size := config.get("size", "8")) in allowed_sizes:
            widget.set_active(allowed_sizes.index(current_size))
        self.widgets["size"] = widget
        add_row(_("Board Size:"), widget)

        # Player Mode (choice)
        # Options for player modes, translated for display.
        widget = Gtk.ComboBoxText()
        player_modes = [
            _("Human vs Human"),
            _("Human (Black) vs AI (White)"),
            _("AI (Black) vs Human (White)"),
            _("AI vs AI"),
        ]
        for mode in player_modes:
            widget.append_text(mode)

        ai_enabled = config.getboolean("ai_enabled", False)
        ai_color = config.get("ai_color", "")
        current_mode_index = 0  # Default to Human vs Human
        if ai_enabled:
            if ai_color == "w":
                current_mode_index = 1
            elif ai_color == "b":
                current_mode_index = 2
            elif ai_color == "A":
                current_mode_index = 3
        widget.set_active(current_mode_index)
        self.widgets["player-mode"] = widget
        add_row(_("Player Mode:"), widget)

        # AI Algorithm (choice)
        widget = Gtk.ComboBoxText()
        ai_modes = [_("Minimax"), _("Iterative"), _("MCTS")]
        for mode in ai_modes:
            widget.append_text(mode)
        current_ai_mode = config.get("ai_mode", "minimax")

        internal_ai_modes = ["minimax", "iterative", "mcts"]
        try:
            current_mode_index_ai = internal_ai_modes.index(
                current_ai_mode.lower()
            )
            widget.set_active(current_mode_index_ai)
        except ValueError:
            widget.set_active(0)

        self.widgets["ai_mode"] = widget
        add_row(_("AI Algorithm:"), widget)

        # AI thinking time (int)
        adj = Gtk.Adjustment(
            value=int(config.getfloat("ai_time", 5.0)),
            lower=0.1,
            upper=3600.0,
            step_incr=0.5,
            page_incr=5.0,
            page_size=0,
        )
        widget = Gtk.SpinButton()
        widget.set_adjustment(adj)
        widget.set_digits(1)
        self.widgets["ai_time"] = widget
        add_row(_("AI thinking time (s):"), widget)

        # MCTS Selection (choice) - Acronyms (UCT, ML, DL) are not translated
        widget = Gtk.ComboBoxText()
        mcts_selections = ["UCT", "ML", "DL"]
        for selection in mcts_selections:
            widget.append_text(selection)
        current_mcts_selection = config.get("ai_mcts_selection", "UCT")
        try:
            current_mcts_index = [m.upper() for m in mcts_selections].index(
                current_mcts_selection.upper()
            )
            widget.set_active(current_mcts_index)
        except ValueError:
            widget.set_active(0)
        self.widgets["ai_mcts_selection"] = widget
        add_row(_("MCTS Selection:"), widget)

        try:
            depth_val = int(config.getfloat("ai_minimax_depth", 0))
        except ValueError:
            depth_val = 0

        adj = Gtk.Adjustment(
            value=depth_val,
            lower=0,  # 0 permet le mode "Auto"
            upper=10,  # 0 allows "Auto" mode
            step_incr=1,
            page_incr=1,
            page_size=0,
        )
        widget = Gtk.SpinButton()
        widget.set_adjustment(adj)
        self.widgets["ai_minimax_depth"] = widget
        add_row(_("Minimax Depth (0 = Auto):"), widget)

        # Minimax Scoring (choice)
        # Options for Minimax scoring functions.
        widget = Gtk.ComboBoxText()
        minimax_scorings = ["function1", "function2", "function3"]
        for scoring in minimax_scorings:
            widget.append_text(scoring)
        current_minimax_scoring = config.get("ai_minimax_scoring", "function1")
        try:
            current_scoring_index = [
                m.lower() for m in minimax_scorings
            ].index(current_minimax_scoring.lower())
            widget.set_active(current_scoring_index)
        except ValueError:
            widget.set_active(0)
        self.widgets["ai_minimax_scoring"] = widget
        add_row(_("Minimax Scoring:"), widget)

        # Language (choice)
        widget = Gtk.ComboBoxText()
        langs = ["en", "fr"]
        for lang in langs:
            widget.append_text(lang)
        if (current_lang := config.get("lang", "en")) in langs:
            widget.set_active(langs.index(current_lang))
        self.widgets["lang"] = widget
        add_row(_("Language:"), widget)

        self.show_all()

    def get_values(self):
        """Retrieves the current values from all widgets in the dialog.

        Returns:
            dict: A dictionary where keys are widget identifiers and values
                  are their current settings.
        """
        values = {}
        for key, widget in self.widgets.items():
            if isinstance(widget, Gtk.Switch):
                values[key] = widget.get_active()
            elif isinstance(widget, Gtk.SpinButton):
                if key in ["timeout", "ai_minimax_depth"]:
                    val = widget.get_value_as_int()
                    if key == "ai_minimax_depth" and val == 0:
                        values[key] = None
                    else:
                        values[key] = val
                elif key == "ai_time":
                    values[key] = widget.get_value()
                else:
                    values[key] = widget.get_value()
            elif isinstance(widget, Gtk.ComboBoxText):
                if key == "ai_mode":
                    active_text = widget.get_active_text()
                    if active_text == _("Minimax"):
                        values[key] = "minimax"
                    elif active_text == _("Iterative"):
                        values[key] = "iterative"
                    elif active_text == _("MCTS"):
                        values[key] = "mcts"
                else:
                    values[key] = widget.get_active_text()
        return values
