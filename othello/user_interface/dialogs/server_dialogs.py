"""Network dialogs: HostServerDialog, JoinServerDialog, LobbyDialog."""

import sys

import gi

if "sphinx" not in sys.modules:
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk
from othello.common.i18n_manager import I18nManager


def _(message):
    return I18nManager().gettext(message)


# ---------------------------------------------------------------------------
# Global CSS for all network dialogs
# ---------------------------------------------------------------------------
_CSS = """
/* --- Main action buttons --- */.

.btn-start {
    background: #2ecc71;
    color: #fff;
    font-weight: bold;
    border-radius: 6px;
    padding: 6px 18px;
    border: none;
}
.btn-start:hover { background: #27ae60; }
.btn-start:disabled { background: #95d5b2; color: #e0e0e0; }

.btn-stop {
    background: #e74c3c;
    color: #fff;
    font-weight: bold;
    border-radius: 6px;
    padding: 6px 18px;
    border: none;
}
.btn-stop:hover { background: #c0392b; }
.btn-stop:disabled { background: #f1a9a0; color: #e0e0e0; }

.btn-action {
    background: #3498db;
    color: #fff;
    font-weight: bold;
    border-radius: 6px;
    padding: 5px 14px;
    border: none;
}
.btn-action:hover { background: #2980b9; }

.btn-warning {
    background: #e67e22;
    color: #fff;
    font-weight: bold;
    border-radius: 6px;
    padding: 5px 14px;
    border: none;
}
.btn-warning:hover { background: #d35400; }

/* --- Log terminal --- */
.log-view {
    font-family: monospace;
    font-size: 12px;
    background: #1e1e2e;
    color: #cdd6f4;
}

/* --- Server status indicator --- */
.status-bar {
    background: #2c3e50;
    color: #ecf0f1;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
}
.status-online  { color: #2ecc71; font-weight: bold; }
.status-offline { color: #e74c3c; font-weight: bold; }
.status-away    { color: #f39c12; font-weight: bold; }

/* --- Section titles --- */
.section-title {
    font-weight: bold;
    font-size: 13px;
    color: #2c3e50;
}

/* --- ListBox --- */
.styled-list {
    border: 1px solid #bdc3c7;
    border-radius: 6px;
}
.styled-list row {
    padding: 6px 10px;
}
.styled-list row:selected {
    background: #3498db;
    color: #fff;
}

/* --- Section separator --- */
.frame-section {
    border: 1px solid #dfe6e9;
    border-radius: 8px;
    padding: 6px;
}

/* --- Status toggle --- */
.toggle-online {
    background: #2ecc71;
    color: #fff;
    font-weight: bold;
    border-radius: 6px;
    padding: 5px 14px;
    border: none;
}
.toggle-online:checked { background: #e74c3c; }
"""


def _apply_css():
    """Injects the CSS provider into the default screen (idempotent)."""
    provider = Gtk.CssProvider()
    provider.load_from_data(_CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def _add_style(widget, *css_classes):
    """Adds CSS classes to a widget.

    Args:
        widget (Gtk.Widget): The widget to style.
        *css_classes (str): The CSS classes to add.
    """
    ctx = widget.get_style_context()
    for cls in css_classes:
        ctx.add_class(cls)


def _make_section_label(text):
    """Creates a styled section label.

    Args:
        text (str): The text of the label.

    Returns:
        Gtk.Label: A Gtk.Label widget.
    """
    lbl = Gtk.Label()
    lbl.set_markup(f"<b>{text}</b>")
    lbl.set_halign(Gtk.Align.START)
    _add_style(lbl, "section-title")
    return lbl


# ===========================================================================
# HostServerDialog
# ===========================================================================
class HostServerDialog(Gtk.Dialog):
    """A dialog for managing the game server."""

    def __init__(self, parent, input_queue):
        """Initializes the HostServerDialog.

        Args:
            parent (Gtk.Window): The parent window.
            input_queue (queue.Queue): The queue to send user commands to.
        """
        _apply_css()
        super().__init__(
            title=_("Host a Game Server"), transient_for=parent, flags=0
        )
        self.input_queue = input_queue
        self.add_buttons(_("_Close"), Gtk.ResponseType.CLOSE)
        self.set_default_size(560, 440)

        self.log_buffer = Gtk.TextBuffer()

        content_area = self.get_content_area()
        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=14
        )
        content_area.add(root)

        # --- Header ---
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_lbl = Gtk.Label()
        title_lbl.set_markup(
            _("<span size='large' weight='bold'>Server Control</span>")
        )
        title_lbl.set_halign(Gtk.Align.START)
        header.pack_start(title_lbl, True, True, 0)

        # Status indicator (small colored label)
        self.status_indicator = Gtk.Label(label=_("[STOPPED]"))
        _add_style(self.status_indicator, "status-offline")
        header.pack_end(self.status_indicator, False, False, 0)
        root.pack_start(header, False, False, 0)

        root.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
            False,
            False,
            0,
        )

        # --- Port Entry ---
        port_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        port_label = Gtk.Label(label=_("Port:"))
        port_label.set_halign(Gtk.Align.START)
        port_box.pack_start(port_label, False, False, 0)

        self.port_entry = Gtk.Entry()
        self.port_entry.set_placeholder_text(
            _("e.g., 12345 (leave blank for default)")
        )
        self.port_entry.set_hexpand(True)
        port_box.pack_start(self.port_entry, True, True, 0)
        root.pack_start(port_box, False, False, 0)

        # --- Control buttons ---
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        self.start_button = Gtk.Button(label=_("  Start Server  "))
        _add_style(self.start_button, "btn-start")
        self.start_button.connect("clicked", self.on_start_server)
        btn_box.pack_start(self.start_button, True, True, 0)

        self.stop_button = Gtk.Button(label=_("  Stop Server  "))
        _add_style(self.stop_button, "btn-stop")
        self.stop_button.connect("clicked", self.on_stop_server)
        self.stop_button.set_sensitive(False)
        btn_box.pack_start(self.stop_button, True, True, 0)

        root.pack_start(btn_box, False, False, 0)

        # --- Log area ---
        root.pack_start(_make_section_label(_("Server Log")), False, False, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_shadow_type(Gtk.ShadowType.IN)

        self.log_view = Gtk.TextView()
        self.log_view.set_buffer(self.log_buffer)
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_left_margin(8)
        self.log_view.set_right_margin(8)
        self.log_view.set_top_margin(6)
        self.log_view.set_bottom_margin(6)
        _add_style(self.log_view, "log-view")
        scrolled_window.add(self.log_view)
        root.pack_start(scrolled_window, True, True, 0)

        self.show_all()

    def on_start_server(self, widget):
        """Handle the 'Start Server' button click.

        Args:
            widget (Gtk.Button): The button that was clicked.
        """
        port = self.port_entry.get_text().strip()
        command = "server start"
        if port:
            command += f" {port}"
        self.input_queue.put(command)
        self.start_button.set_sensitive(False)
        self.stop_button.set_sensitive(True)
        self.status_indicator.set_markup(
            _("<span weight='bold' foreground='#2ecc71'>[RUNNING]</span>")
        )

    def on_stop_server(self, widget):
        """Handle the 'Stop Server' button click.

        Args:
            widget (Gtk.Button): The button that was clicked.
        """
        self.input_queue.put("server stop")
        self.start_button.set_sensitive(True)
        self.stop_button.set_sensitive(False)
        self.status_indicator.set_markup(
            _("<span weight='bold' foreground='#e74c3c'>[STOPPED]</span>")
        )

    def add_log(self, message):
        """Add a message to the log view.

        Args:
            message (str): The message to add to the log.
        """
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, message + "\n")
        adj = self.log_view.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())


# ===========================================================================
# JoinServerDialog
# ===========================================================================
class JoinServerDialog(Gtk.Dialog):
    """A dialog for joining a game server."""

    def __init__(self, parent, input_queue):
        """Initializes the JoinServerDialog.

        Args:
            parent (Gtk.Window): The parent window.
            input_queue (queue.Queue): The queue to send user commands to.
        """
        _apply_css()
        super().__init__(title=_("Join a Game"), transient_for=parent, flags=0)
        self.input_queue = input_queue
        self.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Join"),
            Gtk.ResponseType.OK,
        )
        self.set_default_size(440, 360)

        content_area = self.get_content_area()
        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=14
        )
        content_area.add(root)

        # Title
        title_lbl = Gtk.Label()
        title_lbl.set_markup(
            _("<span size='large' weight='bold'>Connect to a Server</span>")
        )
        title_lbl.set_halign(Gtk.Align.START)
        root.pack_start(title_lbl, False, False, 0)
        root.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
            False,
            False,
            0,
        )

        # --- Discovered servers ---
        discovered_frame = Gtk.Frame()
        discovered_frame.set_label(_("  Discovered Servers on the Network  "))
        discovered_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        discovered_inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8
        )
        discovered_frame.add(discovered_inner)

        # Refresh row
        refresh_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        self.refresh_label = Gtk.Label(label=_("Scanning..."))
        self.refresh_label.set_halign(Gtk.Align.START)
        refresh_row.pack_start(self.refresh_label, True, True, 0)

        refresh_btn = Gtk.Button(label=_("Refresh"))
        _add_style(refresh_btn, "btn-action")
        refresh_btn.connect("clicked", lambda _: self.request_server_list())
        refresh_row.pack_end(refresh_btn, False, False, 0)
        discovered_inner.pack_start(refresh_row, False, False, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_vexpand(True)
        scrolled_window.set_shadow_type(Gtk.ShadowType.IN)
        scrolled_window.set_min_content_height(120)

        self.server_listbox = Gtk.ListBox()
        self.server_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        _add_style(self.server_listbox, "styled-list")
        scrolled_window.add(self.server_listbox)
        discovered_inner.pack_start(scrolled_window, True, True, 0)
        root.pack_start(discovered_frame, True, True, 0)

        # --- Manual entry ---
        manual_frame = Gtk.Frame()
        manual_frame.set_label(_("  Or enter an address manually  "))
        manual_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        manual_inner = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin=10
        )
        manual_frame.add(manual_inner)

        addr_label = Gtk.Label(label=_("Address:"))
        addr_label.set_halign(Gtk.Align.START)
        manual_inner.pack_start(addr_label, False, False, 0)

        self.manual_entry = Gtk.Entry(
            placeholder_text=_("e.g. 192.168.1.10:12345")
        )
        self.manual_entry.set_hexpand(True)
        manual_inner.pack_start(self.manual_entry, True, True, 0)
        root.pack_start(manual_frame, False, False, 0)

        self.show_all()

        self.refresh_timer = GLib.timeout_add_seconds(
            10, self.request_server_list
        )
        self.request_server_list()

    def request_server_list(self):
        """Request the server list from the game session.

        Returns:
            bool: Always True to keep the timer running.
        """
        self.input_queue.put("server list")
        self.refresh_label.set_text(_("Scanning..."))
        return True

    def update_server_list(self, servers):
        """Populate the listbox with server entries.

        Args:
            servers (list): A list of server address strings.
        """
        for child in self.server_listbox.get_children():
            child.destroy()

        if not servers:
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=_("No servers found on the network."))
            lbl.set_halign(Gtk.Align.CENTER)
            lbl.set_margin_top(10)
            lbl.set_margin_bottom(10)
            lbl.set_markup(_("<i>No servers found on the network.</i>"))
            row.add(lbl)
            self.server_listbox.add(row)
            self.refresh_label.set_text(_("No servers found."))
        else:
            for server_str in servers:
                row = Gtk.ListBoxRow()
                lbl = Gtk.Label(label=server_str)
                lbl.set_halign(Gtk.Align.START)
                lbl.set_margin_start(8)
                row.add(lbl)
                self.server_listbox.add(row)
            self.refresh_label.set_markup(
                _("<b>{count} server(s) found</b>").format(count=len(servers))
            )

        self.show_all()

    def get_selected_server(self):
        """Get the selected server address, prioritizing manual entry.

        Returns:
            str or None: The selected server address,
            or None if no server is selected.
        """
        manual_addr = self.manual_entry.get_text().strip()
        if manual_addr:
            return manual_addr
        selected_row = self.server_listbox.get_selected_row()
        if selected_row:
            return selected_row.get_child().get_label()
        return None

    def destroy(self):
        """Override destroy to stop the timer."""
        if self.refresh_timer:
            GLib.source_remove(self.refresh_timer)
            self.refresh_timer = None
        super().destroy()


# ===========================================================================
# LobbyDialog
# ===========================================================================
class LobbyDialog(Gtk.Dialog):
    """A dialog for the pre-game lobby."""

    def __init__(self, parent, input_queue):
        """Initializes the LobbyDialog.

        Args:
            parent (Gtk.Window): The parent window.
            input_queue (queue.Queue): The queue to send user commands to.
        """
        _apply_css()
        super().__init__(title=_("Lobby"), transient_for=parent, flags=0)
        self.input_queue = input_queue
        self.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Challenge"),
            Gtk.ResponseType.OK,
        )
        self.set_default_size(760, 480)

        content_area = self.get_content_area()
        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14
        )
        content_area.add(root)

        # ── Top bar: title + server status ──────────────────────────────────
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        title_lbl = Gtk.Label()
        title_lbl.set_markup(
            _("<span size='large' weight='bold'>Online Lobby</span>")
        )
        title_lbl.set_halign(Gtk.Align.START)
        top_bar.pack_start(title_lbl, False, False, 0)

        self.server_status_label = Gtk.Label(
            label=_("Server status: Refreshing...")
        )
        self.server_status_label.set_halign(Gtk.Align.END)
        _add_style(self.server_status_label, "status-bar")
        top_bar.pack_end(self.server_status_label, False, False, 0)

        root.pack_start(top_bar, False, False, 0)
        root.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
            False,
            False,
            2,
        )

        # ── Two-column body ─────────────────────────────────────────────────
        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        root.pack_start(columns, True, True, 0)

        # ── LEFT COLUMN ─────────────────────────────────────────────────────
        left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        left_col.set_size_request(280, -1)
        columns.pack_start(left_col, False, False, 0)

        # Identity frame
        identity_frame = Gtk.Frame()
        identity_frame.set_label(_("  My Identity  "))
        identity_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        identity_inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=12
        )
        identity_frame.add(identity_inner)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_lbl = Gtk.Label(label=_("Nickname:"))
        name_lbl.set_width_chars(9)
        name_row.pack_start(name_lbl, False, False, 0)
        self.name_entry = Gtk.Entry(placeholder_text=_("New nickname..."))
        self.name_entry.set_hexpand(True)
        name_row.pack_start(self.name_entry, True, True, 0)
        self.name_button = Gtk.Button(label=_("Apply"))
        _add_style(self.name_button, "btn-action")
        self.name_button.connect("clicked", self.on_change_name_clicked)
        name_row.pack_start(self.name_button, False, False, 0)
        identity_inner.pack_start(name_row, False, False, 0)

        self.status_toggle = Gtk.ToggleButton(label=_("Status: Online"))
        _add_style(self.status_toggle, "toggle-online")
        self.status_toggle.connect("toggled", self.on_status_toggled)
        identity_inner.pack_start(self.status_toggle, False, False, 0)

        left_col.pack_start(identity_frame, False, False, 0)

        # Actions frame
        actions_frame = Gtk.Frame()
        actions_frame.set_label(_("  Actions  "))
        actions_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        actions_inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12
        )
        actions_frame.add(actions_inner)

        score_button = Gtk.Button(label=_("View Scoreboard"))
        _add_style(score_button, "btn-action")
        score_button.connect("clicked", self.on_scoreboard_clicked)
        actions_inner.pack_start(score_button, False, False, 0)

        info_button = Gtk.Button(label=_("Player Info"))
        _add_style(info_button, "btn-action")
        info_button.connect("clicked", self.on_info_clicked)
        actions_inner.pack_start(info_button, False, False, 0)

        self.cancel_button = Gtk.Button(label=_("Cancel Challenge"))
        _add_style(self.cancel_button, "btn-warning")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        actions_inner.pack_start(self.cancel_button, False, False, 0)

        left_col.pack_start(actions_frame, False, False, 0)

        # Vertical separator between columns
        columns.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
            False,
            False,
            0,
        )

        # ── RIGHT COLUMN: player list ────────────────────────────────────────
        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        columns.pack_start(right_col, True, True, 0)

        players_frame = Gtk.Frame()
        players_frame.set_label(_("  Online Players  "))
        players_frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        players_inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12
        )
        players_frame.add(players_inner)

        hint = Gtk.Label()
        hint.set_markup(
            _("<i><small>Select a player, then click Challenge.</small></i>")
        )
        hint.set_halign(Gtk.Align.START)
        players_inner.pack_start(hint, False, False, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_vexpand(True)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_shadow_type(Gtk.ShadowType.IN)
        self.player_listbox = Gtk.ListBox()
        self.player_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        _add_style(self.player_listbox, "styled-list")
        scrolled_window.add(self.player_listbox)
        players_inner.pack_start(scrolled_window, True, True, 0)

        right_col.pack_start(players_frame, True, True, 0)

        self.show_all()

        self.refresh_timer = GLib.timeout_add_seconds(
            10, self.request_player_list
        )
        self.request_player_list()

    # ------------------------------------------------------------------

    def on_info_clicked(self, widget):
        """Request information about the selected player.

        Args:
            widget (Gtk.Button): The button that was clicked.
        """
        selected_player = self.get_selected_player()
        if selected_player:
            self.input_queue.put(f"players {selected_player}")
        else:
            # Display a warning if no player is selected
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text=_("No player selected"),
            )
            dialog.format_secondary_text(
                _(
                    "Please select a player from "
                    "the list before requesting info."
                )
            )
            dialog.run()
            dialog.destroy()

    def update_server_status(self, text):
        """Update the server status bar.

        Args:
            text (str): The new status text.
        """
        self.server_status_label.set_markup(f"<b> {text}</b>")

    def on_cancel_clicked(self, widget):
        """Cancel a pending challenge.

        Args:
            widget (Gtk.Button): The button that was clicked.
        """
        self.input_queue.put("cancel")
        self.request_player_list()

    def on_status_toggled(self, widget):
        """Toggle between Online and Away.

        Args:
            widget (Gtk.ToggleButton): The toggle button that was toggled.
        """
        if widget.get_active():
            widget.set_label(_("Status: Away"))
            self.input_queue.put("away")
        else:
            widget.set_label(_("Status: Online"))
            self.input_queue.put("back")
        self.request_player_list()

    def on_scoreboard_clicked(self, widget):
        """Request the scoreboard.

        Args:
            widget (Gtk.Button): The button that was clicked.
        """
        self.input_queue.put("scoreboard")

    def on_change_name_clicked(self, widget):
        """Send a name-change command to the server.

        Args:
            widget (Gtk.Button): The button that was clicked.
        """
        new_name = self.name_entry.get_text().strip()
        if new_name:
            if " " in new_name:
                new_name = f'"{new_name}"'
            self.input_queue.put(f"name {new_name}")
            self.name_entry.set_text("")
            self.request_player_list()

    def request_player_list(self):
        """Request the player list from the game session.

        Returns:
            bool: Always True to keep the timer running.
        """
        self.input_queue.put("players")
        self.input_queue.put("server status")
        return True

    def update_player_list(self, players):
        """Populate the listbox with player entries.

        Args:
            players (list or dict or str): A list of players.
                Can be a list of tuples, a dictionary of name:status,
                or a newline-separated string.
        """
        normalized_players = []

        if players:
            if isinstance(players, str):
                normalized_players = [
                    p.strip() for p in players.split("\n") if p.strip()
                ]
            elif isinstance(players, dict):
                normalized_players = [
                    f"{name} [{status}]" for name, status in players.items()
                ]
            elif isinstance(players, (list, tuple)):
                for p in players:
                    if isinstance(p, (tuple, list)) and len(p) >= 2:
                        normalized_players.append(f"{p[0]} [{p[1]}]")
                    else:
                        normalized_players.append(str(p))

        for child in self.player_listbox.get_children():
            child.destroy()

        if not normalized_players:
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label()
            lbl.set_markup(_("<i>No other players in the lobby.</i>"))
            lbl.set_margin_top(10)
            lbl.set_margin_bottom(10)
            lbl.set_halign(Gtk.Align.CENTER)
            row.add(lbl)
            self.player_listbox.add(row)
        else:
            for player_str in normalized_players:
                row = Gtk.ListBoxRow()
                lbl = Gtk.Label(label=player_str)
                lbl.set_halign(Gtk.Align.START)
                lbl.set_margin_start(8)
                row.add(lbl)
                self.player_listbox.add(row)

        self.show_all()

    def get_selected_player(self):
        """Get the ID of the selected player.

        Returns:
            str or None: The selected player's name,
            or None if no player is selected.
        """
        selected_row = self.player_listbox.get_selected_row()
        if selected_row:
            label_text = selected_row.get_child().get_label()
            return label_text.split(" ")[0]
        return None

    def destroy(self):
        """Override destroy to stop the timer."""
        if self.refresh_timer:
            GLib.source_remove(self.refresh_timer)
            self.refresh_timer = None
        super().destroy()
