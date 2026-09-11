"""SaveDialog module."""

import sys

import gi

if "sphinx" not in sys.modules:
    gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from othello.common.i18n_manager import I18nManager


def _(message):
    return I18nManager().gettext(message)


class SaveDialog(Gtk.Dialog):
    """A dialog for getting a filename and an optional comment for saving.

    This dialog allows the user to input a filename and an optional comment
    when saving a game.
    """

    def __init__(self, parent):
        """Initializes the SaveDialog.

        Args:
            parent (Gtk.Window): The parent window for this dialog.
        """
        super().__init__(title=_("Save Game"), transient_for=parent, flags=0)

        self.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Save"),
            Gtk.ResponseType.OK,
        )

        self.set_default_size(350, 150)

        content_area = self.get_content_area()
        grid = Gtk.Grid(
            column_spacing=10, row_spacing=10, margin=20, halign=Gtk.Align.FILL
        )
        content_area.add(grid)

        # Filename entry
        label_filename = Gtk.Label(label="Filename:", halign=Gtk.Align.START)
        grid.attach(label_filename, 0, 0, 1, 1)
        self.filename_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.filename_entry, 1, 0, 1, 1)

        # Comment entry
        label_comment = Gtk.Label(label="Comment:", halign=Gtk.Align.START)
        grid.attach(label_comment, 0, 1, 1, 1)
        self.comment_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.comment_entry, 1, 1, 1, 1)

        self.show_all()

    def get_values(self):
        """Retrieves the text from the filename and comment entry fields.

        Returns:
            dict: A dictionary containing the 'filename' and 'comment' strings.
        """
        return {
            "filename": self.filename_entry.get_text(),
            "comment": self.comment_entry.get_text(),
        }
