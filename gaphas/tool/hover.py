from gi.repository import Gdk, Gtk

from gaphas.cursor import cursor
from gaphas.tool.itemtool import handle_at_point, item_at_point
from gaphas.view import GtkView


def hover_tool(view: GtkView) -> Gtk.EventController:
    """Highlight the currently hovered item."""
    ctrl = (
        Gtk.EventControllerMotion.new(view)
        if Gtk.get_major_version() == 3
        else Gtk.EventControllerMotion.new()
    )
    ctrl.connect("motion", on_motion)
    return ctrl


def on_motion(ctrl, x, y):
    view = ctrl.get_widget()
    pos = (x, y)
    item, handle = handle_at_point(view, pos)
    view.selection.hovered_item = item or next(item_at_point(view, pos), None)  # type: ignore[call-overload]
    set_cursor(view, cursor(item, handle))


def set_cursor(view, cursor_name):
    if Gtk.get_major_version() == 3:
        display = view.get_display()
        cursor = Gdk.Cursor.new_from_name(display, cursor_name)
        view.get_window().set_cursor(cursor)
    else:
        cursor = Gdk.Cursor.new_from_name(cursor_name)
        view.set_cursor(cursor)
