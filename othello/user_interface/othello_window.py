"""OthelloWindow module."""

import queue
import sys

import cairo
import gi

if "sphinx" not in sys.modules:
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")


from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk

from othello.common.config_manager import ConfigManager
from othello.common.i18n_manager import I18nManager
from othello.orchestrator.bitboard_ops import BitboardOps
from othello.user_interface.dialogs.config_dialog import ConfigDialog
from othello.user_interface.dialogs.save_dialog import SaveDialog
from othello.user_interface.dialogs.server_dialogs import HostServerDialog
from othello.user_interface.dialogs.server_dialogs import JoinServerDialog
from othello.user_interface.dialogs.server_dialogs import LobbyDialog


def _(message):
    """Translate the given message."""
    return I18nManager().gettext(message)


class OthelloWindow(Gtk.ApplicationWindow):
    """OthelloWindow class."""

    def __init__(self, app, output_queue, input_queue):
        """Initialize the Othello window.

        Args:
            app: The GTK application instance.
            output_queue: Queue for receiving messages from the game engine.
            input_queue: Queue for sending commands to the game engine.
        """
        super().__init__(title=_("Othello"), application=app)
        self.output_queue = output_queue
        self.input_queue = input_queue
        self.current_player = "X"
        self.unsaved_changes = False
        self.is_online = False
        self.is_my_turn = False
        self.set_default_size(500, 600)
        self.host_server_dialog = None
        self.join_server_dialog = None
        self.lobby_dialog = None

        self._load_css()

        self.header_bar = self._create_header_bar()
        self.set_titlebar(self.header_bar)

        self.main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10
        )
        self.add(self.main_box)

        # Centering box for the board
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        center_box.set_valign(Gtk.Align.CENTER)
        center_box.set_halign(Gtk.Align.CENTER)
        self.main_box.pack_start(center_box, True, True, 0)

        # --- Scoreboard (UX Improvement) ---
        self.score_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=20
        )
        self.score_box.set_halign(Gtk.Align.CENTER)
        self.score_box.set_margin_bottom(10)

        self.score_label_black = Gtk.Label()
        self.score_label_black.set_markup(
            _("<span font='14' weight='bold'>Black: 2</span>")
        )
        self.score_box.pack_start(self.score_label_black, True, True, 0)

        self.time_label_black = Gtk.Label()
        self.time_label_black.set_markup("<span font='12'> --:--</span>")
        self.score_box.pack_start(self.time_label_black, True, True, 0)

        self.time_label_white = Gtk.Label()
        self.time_label_white.set_markup("<span font='12'> --:--</span>")
        self.score_box.pack_start(self.time_label_white, True, True, 0)

        self.score_label_white = Gtk.Label()
        self.score_label_white.set_markup(_("<span font='14'>White: 2</span>"))
        self.score_box.pack_start(self.score_label_white, True, True, 0)
        center_box.pack_start(self.score_box, False, False, 0)

        self.board_grid = Gtk.Grid()
        self.board_grid.get_style_context().add_class("board-grid")
        center_box.pack_start(self.board_grid, True, True, 0)

        # Add a widget to drag pieces from
        self.piece_source_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=10
        )
        self.piece_source_box.set_halign(Gtk.Align.CENTER)
        source_label = Gtk.Label(label=_("Drag from here:"))
        self.piece_source_box.pack_start(source_label, False, False, 0)

        self.draggable_piece = Gtk.Box()
        self.draggable_piece.set_size_request(40, 40)
        style_context = self.draggable_piece.get_style_context()
        style_context.add_class("piece")

        # Wrap the piece in an EventBox to capture drag events
        event_box = Gtk.EventBox()
        event_box.add(self.draggable_piece)

        self.piece_source_box.pack_start(event_box, False, False, 0)
        self.main_box.pack_start(self.piece_source_box, False, True, 0)

        status_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=10
        )
        status_box.set_halign(Gtk.Align.CENTER)
        self.main_box.pack_start(status_box, False, True, 0)

        self.status_label = Gtk.Label(label=_("Welcome to Othello!"))
        status_box.pack_start(self.status_label, False, True, 0)

        self.spinner = Gtk.Spinner()
        status_box.pack_start(self.spinner, False, True, 0)

        # DND setup for the source piece
        self.dnd_target_entry = Gtk.TargetEntry.new(
            "text/plain", Gtk.TargetFlags.SAME_APP, 0
        )
        event_box.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [self.dnd_target_entry],
            Gdk.DragAction.COPY,
        )
        event_box.connect("drag-begin", self.on_drag_begin)
        event_box.connect("drag-data-get", self.on_drag_data_get)

        self.connect("delete-event", self.on_delete_event)
        self._blitz_disabled = False
        GLib.idle_add(self.process_output_queue)
        GLib.timeout_add_seconds(1, self.request_time_update)

    def on_delete_event(self, widget, event):
        """Handle the window close button event.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
            event (Gdk.Event): The event that triggered the signal.

        Returns:
            bool: True to prevent the default handler
            from destroying the window.
        """
        self.on_quit(widget)
        return True  # Prevent the default handler from destroying the window

    def _load_css(self):
        """Load the CSS for the Othello window."""
        css = b"""
        .board-grid {
            background-color: #008000;
        }
        .board-button {
            background-image: none;
            background-color: #008000;
            border: 1px solid #004000;
            border-radius: 0;
            min-height: 50px;
            min-width: 50px;
        }
        .board-button:hover {
            background-color: #00A000;
        }
        .legal-move {
            background-color: #00A000;
        }
        .legal-move:hover {
            background-color: #00C000;
        }
        .piece {
            border-radius: 25px;
            min-height: 40px;
            min-width: 40px;
            margin: 5px;
        }
        .piece-X {
            background-color: black;
            border: 1px solid #404040;
        }
        .piece-O {
            background-color: white;
            border: 1px solid #a0a0a0;
        }
"""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _create_header_bar(self):
        """Create the header bar for the Othello window."""
        header_bar = Gtk.HeaderBar()
        header_bar.set_show_close_button(True)
        header_bar.props.title = _("Othello")

        accel_group = Gtk.AccelGroup()
        self.add_accel_group(accel_group)

        # Container for menu buttons
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        Gtk.StyleContext.add_class(box.get_style_context(), "linked")
        header_bar.pack_start(box)

        # File Menu
        file_button = Gtk.MenuButton(label=_("File"))
        box.add(file_button)
        file_menu = Gtk.Menu()
        file_button.set_popup(file_menu)

        new_game_item = Gtk.MenuItem(label=_("New Game"))
        new_game_item.connect("activate", self.on_new_game)
        new_game_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_n,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_menu.append(new_game_item)

        load_item = Gtk.MenuItem(label=_("Load Game"))
        load_item.connect("activate", self.on_load_game)
        load_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_l,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_menu.append(load_item)

        save_item = Gtk.MenuItem(label=_("Save Game"))
        save_item.connect("activate", self.on_save_game)
        save_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_s,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_menu.append(save_item)

        config_item = Gtk.MenuItem(label=_("Configuration"))
        config_item.connect("activate", self.on_config)
        config_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_comma,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_menu.append(config_item)

        info_item = Gtk.MenuItem(label=_("Info"))
        info_item.connect("activate", self.on_info)
        info_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_i,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_menu.append(info_item)

        file_menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label=_("Quit"))
        quit_item.connect("activate", self.on_quit)
        quit_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_q,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        file_menu.append(quit_item)

        # Game Menu
        game_button = Gtk.MenuButton(label=_("Game"))
        box.add(game_button)
        game_menu = Gtk.Menu()
        game_button.set_popup(game_menu)

        undo_item = Gtk.MenuItem(label=_("Undo"))
        undo_item.connect("activate", self.on_undo)
        undo_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_u,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        undo_item.set_sensitive(True)
        game_menu.append(undo_item)

        redo_item = Gtk.MenuItem(label=_("Redo"))
        redo_item.connect("activate", self.on_redo)
        redo_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_r,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        redo_item.set_sensitive(True)
        game_menu.append(redo_item)

        pause_item = Gtk.MenuItem(label=_("Pause"))
        pause_item.connect("activate", self.on_pause)
        pause_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_p,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        pause_item.set_sensitive(True)
        game_menu.append(pause_item)

        hint_item = Gtk.MenuItem(label=_("Hint"))
        hint_item.connect("activate", self.on_hint)
        hint_item.add_accelerator(
            "activate",
            accel_group,
            Gdk.KEY_h,
            Gdk.ModifierType.CONTROL_MASK,
            Gtk.AccelFlags.VISIBLE,
        )
        hint_item.set_sensitive(True)
        game_menu.append(hint_item)

        # Network Menu
        network_button = Gtk.MenuButton(label=_("Network"))
        box.add(network_button)
        network_menu = Gtk.Menu()
        network_button.set_popup(network_menu)

        host_item = Gtk.MenuItem(label=_("Host Server"))
        host_item.connect("activate", self.on_host_server)
        network_menu.append(host_item)

        join_item = Gtk.MenuItem(label=_("Join Server"))
        join_item.connect("activate", self.on_join_server)
        network_menu.append(join_item)

        lobby_item = Gtk.MenuItem(label=_("Lobby"))
        lobby_item.connect("activate", self.on_show_lobby_menu)
        network_menu.append(lobby_item)

        disconnect_item = Gtk.MenuItem(label=_("Disconnect"))
        disconnect_item.connect("activate", self.on_disconnect)
        network_menu.append(disconnect_item)

        file_menu.show_all()
        game_menu.show_all()
        network_menu.show_all()

        return header_bar

    # -------------------------------------------------------------------------
    # Network handlers
    # -------------------------------------------------------------------------

    def on_show_lobby_menu(self, widget):
        """Handle the 'Lobby' menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        if getattr(self, "is_server_connected", False):
            self.show_lobby_dialog()
        else:
            self.display_error(
                _("You must be connected to a server to open a lobby.")
            )

    def on_host_server(self, widget):
        """Handle the "Host Server" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        if not self.host_server_dialog:
            self.host_server_dialog = HostServerDialog(self, self.input_queue)
            self.host_server_dialog.connect(
                "response", self.on_host_dialog_close
            )
            self.host_server_dialog.show()
        else:
            self.host_server_dialog.present()

    def on_host_dialog_close(self, dialog, response_id):
        """Clean up the host server dialog.

        Args:
            dialog (Gtk.Dialog): The dialog that emitted the signal.
            response_id (int): The response ID from the dialog.
        """
        self.host_server_dialog.destroy()
        self.host_server_dialog = None
        # Ensure the server is stopped when the dialog is closed
        self.input_queue.put("server stop")

    def on_join_server(self, widget):
        """Handle the "Join Server" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        if not self.join_server_dialog:
            self.join_server_dialog = JoinServerDialog(self, self.input_queue)
            self.join_server_dialog.connect(
                "response", self.on_join_dialog_response
            )
            self.join_server_dialog.show()
        else:
            self.join_server_dialog.present()

    def on_join_dialog_response(self, dialog, response_id):
        """Handle response from the join server dialog.

        Args:
            dialog (Gtk.Dialog): The dialog that emitted the signal.
            response_id (int): The response ID from the dialog.
        """
        if response_id == Gtk.ResponseType.OK:
            selected_server = dialog.get_selected_server()
            if selected_server:
                self.input_queue.put(f"join {selected_server}")
            else:
                self.display_error(
                    _("No server selected or manually entered.")
                )

        dialog.destroy()
        self.join_server_dialog = None

    def show_lobby_dialog(self):
        """Show the pre-game lobby dialog."""
        if not self.lobby_dialog:
            self.lobby_dialog = LobbyDialog(self, self.input_queue)
            self.lobby_dialog.connect(
                "response", self.on_lobby_dialog_response
            )
            self.lobby_dialog.show()
        else:
            self.lobby_dialog.present()

    def on_lobby_dialog_response(self, dialog, response_id):
        """Handle response from the lobby dialog.

        Args:
            dialog (Gtk.Dialog): The dialog that emitted the signal.
            response_id (int): The response ID from the dialog.
        """
        if response_id == Gtk.ResponseType.OK:
            selected_player = dialog.get_selected_player()
            if selected_player:
                self.input_queue.put(f"new {selected_player}")
                dialog.destroy()
                self.lobby_dialog = None
                return
            else:
                self.display_error(_("No player selected."))
                # Re-show dialog if no player was selected
                # but challenge was clicked
                self.show_lobby_dialog()
                return

        dialog.destroy()
        self.lobby_dialog = None

    def on_disconnect(self, widget):
        """Handle the "Disconnect" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        self.input_queue.put("quit")
        self.is_my_turn = False
        self.display_message(_("Disconnected."))

    # -------------------------------------------------------------------------
    # File / game handlers
    # -------------------------------------------------------------------------

    def on_new_game(self, widget):
        """Handle the "New Game" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        self.input_queue.put("new")
        self.input_queue.put("show time")

    def on_load_game(self, widget):
        """Handle the "Load Game" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        dialog = Gtk.FileChooserDialog(
            title=_("Please choose a file"),
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Open"),
            Gtk.ResponseType.OK,
        )
        if dialog.run() == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            self.input_queue.put(f"load {filename}")
        dialog.destroy()

    def on_save_game(self, widget):
        """Handle the "Save Game" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        save_dialog = SaveDialog(self)
        response = save_dialog.run()

        saved_submitted = (
            False  # Flag to track if the user submitted a save command
        )

        if response == Gtk.ResponseType.OK:
            values = save_dialog.get_values()
            filename = values["filename"]
            comment = values["comment"]

            if not filename:
                self.display_error(_("Filename cannot be empty."))
            else:
                save_command = f"save {filename}"
                if comment:
                    # The CLI parser splits by space, so we handle
                    # multi-word comments
                    # by passing them as a single quoted argument.
                    save_command += f' "{comment}"'
                self.input_queue.put(save_command)
                saved_submitted = True

        save_dialog.destroy()
        return saved_submitted

    def on_config(self, widget):
        """Handle the "Config" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        dialog = ConfigDialog(self)
        if dialog.run() == Gtk.ResponseType.OK:
            config_manager = ConfigManager()
            new_config = dialog.get_values()

            # Handle player mode
            if "player-mode" in new_config:
                mode = new_config.pop("player-mode")
                if mode == _("Human vs Human"):
                    new_config["ai_enabled"] = False
                    new_config["ai_color"] = ""
                elif mode == _("Human (Black) vs AI (White)"):
                    new_config["ai_enabled"] = True
                    new_config["ai_color"] = "w"
                elif mode == _("AI (Black) vs Human (White)"):
                    new_config["ai_enabled"] = True
                    new_config["ai_color"] = "b"
                elif mode == _("AI vs AI"):
                    new_config["ai_enabled"] = True
                    new_config["ai_color"] = "A"

            if "ai_mode" in new_config:
                new_config["ai_mode"] = new_config["ai_mode"].lower()
            if "ai_mcts_selection" in new_config:
                new_config["ai_mcts_selection"] = new_config[
                    "ai_mcts_selection"
                ].upper()
            if "ai_minimax_scoring" in new_config:
                new_config["ai_minimax_scoring"] = new_config[
                    "ai_minimax_scoring"
                ].lower()

            # Save all settings
            for key, value in new_config.items():
                if value is None:
                    # If the value is None (e.g., Auto Mode for depth),
                    # we completely remove the line
                    # from the configuration file.
                    if config_manager.config_parser.has_option(
                        "defaults", key
                    ):
                        config_manager.config_parser.remove_option(
                            "defaults", key
                        )
                else:
                    config_manager.set(key, str(value))

            # pylint: disable=import-outside-toplevel

            I18nManager(lang=new_config.get("lang"))
            # pylint: enable=import-outside-toplevel

            # Apply board size change and restart game
            if (
                new_size := int(new_config.get("size", BitboardOps.SIZE))
            ) != BitboardOps.SIZE:
                BitboardOps.set_board_size(new_size)

            self.input_queue.put("new")
            self.input_queue.put("show time")
            # pylint: disable=undefined-variable
            self.display_message(
                _("Configuration saved. Game has been restarted.")
            )
            # pylint: enable=undefined-variable

        dialog.destroy()

    def on_info(self, widget):
        """Handle the "Info" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        about_dialog = Gtk.AboutDialog()
        about_dialog.set_transient_for(self)
        about_dialog.set_program_name(_("Othello"))
        about_dialog.set_version("0.1.0")
        about_dialog.set_authors(
            [
                "Gregory Bonzon",
                "Remi Boussion",
                "Gabriel Ringuet",
                "Matthieu Vigier-Lafosse",
                "Arthur Voisin",
            ]
        )
        about_dialog.run()
        about_dialog.destroy()

    def on_quit(self, widget):
        """Handle the "Quit" menu item.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        if not self.unsaved_changes:
            self.input_queue.put("quit")
            return

        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=_("Unsaved Changes"),
        )
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        dialog.format_secondary_text(
            _("Do you want to save the game before quitting?")
        )
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            if self.on_save_game(widget):
                self.input_queue.put("quit force")
        elif response == Gtk.ResponseType.NO:
            self.input_queue.put("quit force")
        # if CANCEL, do nothing.

    # -------------------------------------------------------------------------
    # Game action handlers
    # -------------------------------------------------------------------------

    def on_undo(self, widget):
        """Handle undo menu item activation.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        self.input_queue.put("undo")

    def on_redo(self, widget):
        """Handle redo menu item activation.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        self.input_queue.put("redo")

    def on_pause(self, widget):
        """Handle pause menu item activation.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        self.input_queue.put("pause")

    def on_hint(self, widget):
        """Handle hint menu item activation.

        Args:
            widget (Gtk.Widget): The widget that emitted the signal.
        """
        self.input_queue.put("hint")

    # -------------------------------------------------------------------------
    # Output queue processing
    # -------------------------------------------------------------------------

    def process_output_queue(self):
        """Process messages from the game thread."""
        try:
            latest_render = None
            pending_game_over = None
            max_messages_per_tick = 30  # Limit to avoid blocking the GTK loop
            processed = 0

            while (
                not self.output_queue.empty()
                and processed < max_messages_per_tick
            ):
                task, data = self.output_queue.get_nowait()
                processed += 1

                if task == "render":
                    # Save only the latest state
                    # to render it only once
                    latest_render = data
                elif task == "display_message":
                    if isinstance(data, str) and data.startswith(
                        "Remaining Time"
                    ):
                        self.update_timers_from_text(data)
                    elif isinstance(data, str) and (
                        "--- Player Info:" in data
                        or (
                            hasattr(self, "_player_info_timer")
                            and self._player_info_timer
                        )
                    ):
                        self.buffer_player_info(data)
                    else:
                        self.display_message(data)
                elif task == "display_error":
                    if (
                        isinstance(data, str)
                        and _("Blitz is not enabled.") in data
                    ):
                        self._blitz_disabled = True
                        self.time_label_black.hide()
                        self.time_label_white.hide()
                    else:
                        self.is_my_turn = False
                        self.display_error(data)
                elif task == "get_input":
                    self.is_my_turn = True
                    prompt = data
                    # pylint: disable=undefined-variable
                    if "X" in prompt:
                        self.status_label.set_text(_("Black's turn to play"))
                    elif "O" in prompt:
                        self.status_label.set_text(_("White's turn to play"))
                    else:
                        self.status_label.set_text(_(prompt))
                    # pylint: enable=undefined-variable
                elif task == "quit":
                    self.get_application().quit()
                elif task == "game_over":
                    self.is_my_turn = False
                    # Store game over information to
                    # display them after rendering
                    pending_game_over = data
                elif task == "set_thinking":
                    is_thinking = data
                    if is_thinking:
                        self.status_label.set_text(_("AI is thinking..."))
                        self.spinner.start()
                        self.spinner.show()
                    else:
                        self.spinner.stop()
                        self.spinner.hide()
                elif task == "server_log":
                    if self.host_server_dialog:
                        self.host_server_dialog.add_log(data)
                elif task == "discovered_servers":
                    if self.join_server_dialog:
                        self.join_server_dialog.update_server_list(data)
                elif task == "show_lobby":
                    self.is_server_connected = True
                    self.is_my_turn = (
                        False  # Ensure no timer requests are sent
                    )
                    self.show_lobby_dialog()
                elif task == "player_list":
                    if self.lobby_dialog:
                        self.lobby_dialog.update_player_list(data)
                elif task == "player_detail":
                    self.buffer_player_info(data)
                elif task == "game_starting":
                    self.is_my_turn = False  # Precautious reset
                    if self.lobby_dialog:
                        self.lobby_dialog.destroy()
                        self.lobby_dialog = None
                elif task == "set_network_status":
                    if data:
                        self.header_bar.set_subtitle(data)
                        self.is_online = True
                        self.is_server_connected = True
                    else:
                        self.header_bar.set_subtitle(None)
                        self.is_online = False
                        self.is_server_connected = False
                elif task == "invitation_received":
                    self.show_invitation_dialog(data)
                elif task == "scoreboard_line":
                    self.buffer_scoreboard(data)
                elif task == "server_status_line":
                    self.buffer_server_status(data)

            # Update visual display (last played piece)
            if latest_render is not None:
                (
                    board_str,
                    legal_moves,
                    current_player,
                    unsaved_changes,
                ) = latest_render
                self.render_board(
                    board_str, legal_moves, current_player, unsaved_changes
                )

            # Display game over popup if necessary
            # (after updating the board)
            if pending_game_over is not None:
                winner, scores = pending_game_over
                # GLib.idle_add tells GTK:
                # "Show this popup in the next idle cycle,
                # meaning once you have finished drawing
                # the board update above."
                GLib.idle_add(self.show_game_over_dialog, winner, scores)

        except queue.Empty:
            pass
        return True  # Keep the timeout running

    # -------------------------------------------------------------------------
    # Board interactions
    # -------------------------------------------------------------------------

    def on_board_button_clicked(self, widget, col, row):
        """Handle board button click.

        Args:
            widget (Gtk.Button): The button that was clicked.
            col (int): The column index of the clicked button.
            row (int): The row index of the clicked button.
        """
        if not getattr(self, "is_my_turn", False):
            return

        self.is_my_turn = False

        if not getattr(self, "is_online", False):
            # --- Optimistic UI Update (Optimized Version) ---
            piece_style = widget._piece_widget.get_style_context()
            if piece_style.has_class("piece-X"):
                piece_style.remove_class("piece-X")
            if piece_style.has_class("piece-O"):
                piece_style.remove_class("piece-O")

            piece_style.add_class(f"piece-{self.current_player}")
            widget._piece_widget.show()
            widget.set_sensitive(False)  # Prevent re-clicking
            # --- End Optimistic UI Update ---

        # Disable all board interactions to prevent multiple
        # moves before engine update
        for row_btns in getattr(self, "_board_buttons", []):
            for btn in row_btns:
                btn.set_sensitive(False)

        move = f"{self.current_player} {chr(ord('a') + col)}{row + 1}"
        self.input_queue.put(move)

    def on_drag_begin(self, widget, context):
        """Set a drag icon.

        Args:
            widget (Gtk.Widget): The widget that is the source of the drag.
            context (Gdk.DragContext): The drag context.
        """
        # Create a Cairo surface for the drag icon
        surface = cairo.ImageSurface(cairo.Format.ARGB32, 40, 40)
        ctx = cairo.Context(surface)
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_rgba(0, 0, 0, 0)  # Transparent background
        ctx.paint()

        # Draw the Othello piece
        ctx.set_operator(cairo.OPERATOR_OVER)
        if self.current_player == "X":
            ctx.set_source_rgb(0, 0, 0)  # Black
        else:
            ctx.set_source_rgb(1, 1, 1)  # White

        # Circle parameters
        x, y, radius = 20, 20, 18
        ctx.arc(x, y, radius, 0, 2 * 3.14159)
        ctx.fill()

        # Draw a small border to match the CSS
        if self.current_player == "X":
            ctx.set_source_rgba(0.25, 0.25, 0.25, 0.8)  # #404040
        else:
            ctx.set_source_rgba(0.62, 0.62, 0.62, 0.8)  # #a0a0a0
        ctx.set_line_width(1)
        ctx.arc(x, y, radius, 0, 2 * 3.14159)
        ctx.stroke()

        # Use the surface as the drag icon
        Gtk.drag_set_icon_surface(context, surface)

    def on_drag_data_get(
        self, widget, context, selection_data, info, timestamp
    ):
        """Provide drag data.

        Args:
            widget (Gtk.Widget): The widget that is the source of the drag.
            context (Gdk.DragContext): The drag context.
            selection_data (Gtk.SelectionData): The selection data to fill.
            info (int): The target type ID.
            timestamp (int): The timestamp of the event.
        """
        selection_data.set(Gdk.Atom.intern("text/plain", False), 8, b"piece")

    def on_drag_data_received(
        self, widget, context, x, y, selection_data, info, timestamp, coords
    ):
        """Handle dropped data.

        Args:
            widget (Gtk.Widget): The widget that is the destination
            of the drop.
            context (Gdk.DragContext): The drag context.
            x (int): The x-coordinate of the drop.
            y (int): The y-coordinate of the drop.
            selection_data (Gtk.SelectionData): The received selection data.
            info (int): The target type ID.
            timestamp (int): The timestamp of the event.
            coords (tuple): The (column, row) coordinates of the drop target.
        """
        if info == 0:
            data = selection_data.get_data()
            if data and data.decode() == "piece":
                col, row = coords
                self.on_board_button_clicked(widget, col, row)
                context.finish(True, False, timestamp)
            else:
                context.finish(False, False, timestamp)
        else:
            context.finish(False, False, timestamp)

    # -------------------------------------------------------------------------
    # Board rendering
    # -------------------------------------------------------------------------

    def _rebuild_board_grid(self, size: int):
        """Build the grid widgets only once to optimize performance.

        Args:
            size (int): The size of the board (e.g., 8 for an 8x8 board).
        """
        for child in self.board_grid.get_children():
            child.destroy()

        self._board_buttons = []
        for r in range(size):
            row_buttons = []
            for c in range(size):
                button = Gtk.Button()
                button.get_style_context().add_class("board-button")

                # Create the piece container only once
                piece_widget = Gtk.Box()
                piece_widget.get_style_context().add_class("piece")
                button.add(piece_widget)

                # Store a direct reference to the piece to access it
                # quickly later
                button._piece_widget = piece_widget

                # Permanently connect click and Drag & Drop
                button.connect("clicked", self.on_board_button_clicked, c, r)
                button.drag_dest_set(
                    Gtk.DestDefaults.ALL,
                    [self.dnd_target_entry],
                    Gdk.DragAction.COPY,
                )
                button.connect(
                    "drag-data-received",
                    self.on_drag_data_received,
                    (c, r),
                )

                self.board_grid.attach(button, c, r, 1, 1)
                row_buttons.append(button)
            self._board_buttons.append(row_buttons)

        self._board_size = size
        self.board_grid.show_all()

    def render_board(
        self,
        board_str: str,
        legal_moves: int = 0,
        current_player: str = "X",
        unsaved_changes: bool = False,
    ):
        """Render the board (optimized version).

        Args:
            board_str (str): String representation of the board.
            legal_moves (int): Bitboard of legal moves.
            current_player (str): The current player ('X' or 'O').
            unsaved_changes (bool): Whether there are unsaved changes.
        """
        self.current_player = current_player
        self.unsaved_changes = unsaved_changes
        self._blitz_disabled = False
        # --- Update Scoreboard ---
        score_x = board_str.count("X")
        score_o = board_str.count("O")

        style_active = "font='14' weight='bold' foreground='#000000'"
        style_inactive = "font='14' foreground='#555555'"

        fmt_x = style_active if current_player == "X" else style_inactive
        fmt_o = style_active if current_player == "O" else style_inactive

        self.score_label_black.set_markup(
            _("<span {fmt}>Black: {score}</span>").format(
                fmt=fmt_x, score=score_x
            )
        )
        self.score_label_white.set_markup(
            _("<span {fmt}>White: {score}</span>").format(
                fmt=fmt_o, score=score_o
            )
        )

        # Update draggable piece color
        style_context = self.draggable_piece.get_style_context()
        for css_class in style_context.list_classes():
            if "piece-" in css_class:
                style_context.remove_class(css_class)
        style_context.add_class(f"piece-{self.current_player}")

        rows = board_str.split("/")
        size = len(rows)

        # 1. Check if the grid needs to be built
        if getattr(self, "_board_size", 0) != size:
            self._rebuild_board_grid(size)

        # 2. Update visual state without destroying widgets
        for r, row_str in enumerate(rows):
            for c, piece in enumerate(row_str):
                button = self._board_buttons[r][c]
                btn_style = button.get_style_context()
                piece_style = button._piece_widget.get_style_context()

                # Clean up old CSS classes
                if btn_style.has_class("legal-move"):
                    btn_style.remove_class("legal-move")
                if piece_style.has_class("piece-X"):
                    piece_style.remove_class("piece-X")
                if piece_style.has_class("piece-O"):
                    piece_style.remove_class("piece-O")

                # Application du nouvel état
                if piece in ("X", "O"):
                    piece_style.add_class(f"piece-{piece}")
                    button._piece_widget.show()
                    # Prevent clicking on an occupied cell
                    button.set_sensitive(False)
                else:
                    # Hide the piece if the cell is empty
                    button._piece_widget.hide()
                    index = r * size + c
                    if (legal_moves >> index) & 1:
                        btn_style.add_class("legal-move")
                        button.set_sensitive(True)
                    else:
                        button.set_sensitive(False)

    # -------------------------------------------------------------------------
    # Message / error display
    # -------------------------------------------------------------------------

    def display_message(self, message):
        """Display a message, showing hints in a dialog.

        Args:
            message (str): The message to display.
        """
        is_hint = (
            message.startswith("Hint:") or
            message.startswith(_("Hint:")) or
            message.startswith(_("Hint: ")) or
            message.startswith("Indice")
        )
        if is_hint:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text=_("Suggestion"),
            )
            dialog.format_secondary_text(message)
            dialog.run()
            dialog.destroy()
        else:
            self.status_label.set_text(message)

    def display_error(self, message):
        """Display an error in a dialog.

        Args:
            message (str): The error message to display.
        """
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=_("Error"),
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def show_game_over_dialog(self, winner, scores):
        """Show game over dialog with restart option.

        Args:
            winner (str): The winner of the game ('X', 'O', or 'DRAW').
            scores (dict): A dictionary with the final scores for 'X' and 'O'.
        """
        msg = _(
            "Winner: {winner}\nBlack (X): {black_score}"
            "\nWhite (O): {white_score}"
        ).format(
            winner=winner, black_score=scores["X"], white_score=scores["O"]
        )
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text=_("Game Over"),
        )
        dialog.format_secondary_text(msg)
        if getattr(self, "is_online", False):
            dialog.add_button(_("Quit"), Gtk.ResponseType.CLOSE)
            dialog.add_button(_("Return to Lobby"), Gtk.ResponseType.OK)
        else:
            dialog.add_button(_("Quit"), Gtk.ResponseType.CLOSE)
            dialog.add_button(_("New Game"), Gtk.ResponseType.OK)

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            self.input_queue.put(
                "lobby" if getattr(self, "is_online", False) else "restart"
            )
        else:
            self.input_queue.put("quit")

    def request_time_update(self):
        """Ask the time."""
        if not getattr(self, "_blitz_disabled", False):
            # Only ask if there are no pending requests
            # in the input queue
            if getattr(self, "is_my_turn", False) and self.input_queue.empty():
                self.input_queue.put("show time")
        return True  # Return True so that timeout_add continues to execute

    def update_timers_from_text(self, text):
        """Parse the result of the command 'show time' and update UI.

        Args:
            text (str): The string containing time information from the engine.
        """
        self.time_label_black.show()
        self.time_label_white.show()

        is_paused = "(Paused)" in text
        status = _("Paused ") if is_paused else " "

        try:
            # Extract "04:10" and "05:00" from "Remaining Time :
            # X (04:10)- O (05:00)"
            x_part = text.split("X (")[1].split(")")[0]
            o_part = text.split("O (")[1].split(")")[0]

            style_active = "font='12' weight='bold' foreground='#000000'"
            style_inactive = "font='12' foreground='#555555'"

            fmt_x = (
                style_active if self.current_player == "X" else style_inactive
            )
            fmt_o = (
                style_active if self.current_player == "O" else style_inactive
            )

            self.time_label_black.set_markup(
                f"<span {fmt_x}>{status}{x_part}</span>"
            )
            self.time_label_white.set_markup(
                f"<span {fmt_o}>{status}{o_part}</span>"
            )
        except IndexError:
            pass

    def show_invitation_dialog(self, requester_name):
        """Displays a dialog box to accept or decline a challenge.

        Args:
            requester_name (str): The name of the player who sent the
                invitation.
        """
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=_("New challenge!"),
        )

        dialog.format_secondary_text(
            _(
                "{requester_name} challenges you to a game. Do you accept?"
            ).format(requester_name=requester_name)
        )

        # We must also translate the buttons' text!
        dialog.add_button(_("Decline"), Gtk.ResponseType.NO)
        dialog.add_button(_("Accept"), Gtk.ResponseType.YES)

        # Show the dialog box and wait for the user's response
        response = dialog.run()
        dialog.destroy()

        # Send the corresponding command to the game engine
        if response == Gtk.ResponseType.YES:
            self.input_queue.put("accept")
        else:
            self.input_queue.put("decline")

    def buffer_scoreboard(self, line):
        """Accumulate the lines on the scoreboard and displays

        the popup at the end.
        Args:
        line (str): A line of the scoreboard from the server.
        """
        if not hasattr(self, "_score_buffer"):
            self._score_buffer = []

        # Detect the start of a new transmission
        if "--- Scoreboard ---" in line or "No stats available." in line:
            self._score_buffer = [line]
        else:
            self._score_buffer.append(line)

        # Reset a 200 milliseconds timer.
        # If no new lines are received, trigger the display!
        if hasattr(self, "_score_timer") and self._score_timer:
            GLib.source_remove(self._score_timer)
        self._score_timer = GLib.timeout_add(200, self.show_scoreboard_dialog)

    def show_scoreboard_dialog(self):
        """Displays the complete scoreboard in a dialog box."""
        self._score_timer = None  # Timer cleanup

        full_text = "\n".join(self._score_buffer)

        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=_("Server Scoreboard"),
        )

        dialog.format_secondary_text(full_text)

        dialog.run()
        dialog.destroy()

        return False

    def buffer_server_status(self, line):
        """Accumulates the server status lines.

        Used to update the indicator.

        Args:
            line (str): A line of the server status from the server.
        """
        if not hasattr(self, "_server_status_buffer"):
            self._server_status_buffer = []

        # Detect the start of a new transmission
        if "---" in line and "Status ---" in line:
            self._server_status_buffer = [line]
        else:
            self._server_status_buffer.append(line)

        # 200ms timer to wait for the end of the network transmission
        if hasattr(self, "_server_status_timer") and self._server_status_timer:
            GLib.source_remove(self._server_status_timer)
        self._server_status_timer = GLib.timeout_add(
            200, self.update_server_status_display
        )

    def update_server_status_display(self):
        """Updates the Lobby visual indicator with the received data."""

        self._server_status_timer = None

        clients = "?"
        games = "?"

        # Extract relevant numbers from the received lines
        for line in self._server_status_buffer:
            if "Connected Clients:" in line:
                clients = line.split(":")[1].strip()
            elif "Active Games:" in line:
                games = line.split(":")[1].strip()

        # Formatting the text for the visual indicator
        display_text = _(
            "[+] Connected players: {clients}   "
            "|   ⚔️ Games in progress: {games}"
        ).format(clients=clients, games=games)

        # If the lobby is open, update the label live
        if self.lobby_dialog:
            self.lobby_dialog.update_server_status(display_text)

        return False  # Stop the GLib timer loop

    def buffer_player_info(self, line):
        """Collect a player's information lines.

        Args:
            line (str): A line of player information from the server.
        """
        if not hasattr(self, "_player_info_buffer"):
            self._player_info_buffer = []

        # Clean up any potential newline (added by game_session)
        clean_line = line.lstrip("\n")

        # Detect the start of a new transmission
        if "--- Player Info:" in clean_line:
            self._player_info_buffer = [clean_line]
        else:
            self._player_info_buffer.append(clean_line)

        # Reset the 200 milliseconds timer
        if hasattr(self, "_player_info_timer") and self._player_info_timer:
            GLib.source_remove(self._player_info_timer)
        self._player_info_timer = GLib.timeout_add(
            200, self.show_player_info_dialog
        )

    def show_player_info_dialog(self):
        """Displays the complete player info in a dialog box."""
        self._player_info_timer = None  # Timer cleanup

        full_text = "\n".join(self._player_info_buffer)

        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=_("Player Information"),
        )

        dialog.format_secondary_text(full_text)
        dialog.run()
        dialog.destroy()

        self._player_info_buffer = []
        return False
