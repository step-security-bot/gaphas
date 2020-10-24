"""A Canvas owns a set of Items and acts as a container for both the items and
a constraint solver.

Connections
===========

Getting Connection Information
==============================
To get connected item to a handle::

    c = canvas.get_connection(handle)
    if c is not None:
        print c.connected
        print c.port
        print c.constraint


To get all connected items (i.e. items on both sides of a line)::

    classes = (i.connected for i in canvas.get_connections(item=line))


To get connecting items (i.e. all lines connected to a class)::

    lines = (c.item for c in canvas.get_connections(connected=item))
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cairo

from gaphas import matrix, solver, tree
from gaphas.connections import Connections
from gaphas.decorators import AsyncIO, nonrecursive
from gaphas.state import observed, reversible_method, reversible_pair

if TYPE_CHECKING:
    from gaphas.item import Item


class Context:
    """Context used for updating and drawing items in a drawing canvas.

    >>> c=Context(one=1,two='two')
    >>> c.one
    1
    >>> c.two
    'two'
    >>> try: c.one = 2
    ... except: 'got exc'
    'got exc'
    """

    def __init__(self, **kwargs):
        self.__dict__.update(**kwargs)

    def __setattr__(self, key, value):
        raise AttributeError("context is not writable")


def instant_cairo_context():
    """A simple Cairo context, not attached to any window."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 0, 0)
    return cairo.Context(surface)


def default_update_context(item, cairo=instant_cairo_context()):
    return Context(cairo=cairo)


class Canvas:
    """Container class for items."""

    def __init__(self, create_update_context=default_update_context):
        self._create_update_context = create_update_context
        self._tree: tree.Tree[Item] = tree.Tree()
        self._connections = Connections(solver.Solver())

        self._dirty_items = set()
        self._dirty_matrix_items = set()

        self._registered_views = set()

    solver = property(lambda s: s._connections.solver)

    connections = property(lambda s: s._connections)

    @observed
    def add(self, item, parent=None, index=None):
        """Add an item to the canvas.

        >>> c = Canvas()
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> len(c._tree.nodes)
        1
        >>> i._canvas is c
        True
        """
        assert item not in self._tree.nodes, f"Adding already added node {item}"
        self._tree.add(item, parent, index)

        item._set_canvas(self)

        self.request_update(item)

    @observed
    def _remove(self, item):
        """Remove is done in a separate, @observed, method so the undo system
        can restore removed items in the right order."""
        item._set_canvas(None)
        self._tree.remove(item)
        self._update_views(removed_items=(item,))
        self._dirty_items.discard(item)
        self._dirty_matrix_items.discard(item)

    def remove(self, item):
        """Remove item from the canvas.

        >>> c = Canvas()
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> c.remove(i)
        >>> c._tree.nodes
        []
        >>> i._canvas
        """
        for child in reversed(self.get_children(item)):
            self.remove(child)
        self.remove_connections_to_item(item)
        self._remove(item)

    reversible_pair(
        add,
        _remove,
        bind1={
            "parent": lambda self, item: self.get_parent(item),
            "index": lambda self, item: self._tree.get_siblings(item).index(item),
        },
    )

    @observed
    def reparent(self, item, parent, index=None):
        """Set new parent for an item."""
        self._tree.move(item, parent, index)

    reversible_method(
        reparent,
        reverse=reparent,
        bind={
            "parent": lambda self, item: self.get_parent(item),
            "index": lambda self, item: self._tree.get_siblings(item).index(item),
        },
    )

    def get_all_items(self):
        """Get a list of all items.

        >>> c = Canvas()
        >>> c.get_all_items()
        []
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> c.get_all_items() # doctest: +ELLIPSIS
        [<gaphas.item.Item ...>]
        """
        return self._tree.nodes

    def get_root_items(self):
        """Return the root items of the canvas.

        >>> c = Canvas()
        >>> c.get_all_items()
        []
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> ii = item.Item()
        >>> c.add(ii, i)
        >>> c.get_root_items() # doctest: +ELLIPSIS
        [<gaphas.item.Item ...>]
        """
        return self._tree.get_children(None)

    def get_parent(self, item):
        """See `tree.Tree.get_parent()`.

        >>> c = Canvas()
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> ii = item.Item()
        >>> c.add(ii, i)
        >>> c.get_parent(i)
        >>> c.get_parent(ii) # doctest: +ELLIPSIS
        <gaphas.item.Item ...>
        """
        return self._tree.get_parent(item)

    def get_ancestors(self, item):
        """See `tree.Tree.get_ancestors()`.

        >>> c = Canvas()
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> ii = item.Item()
        >>> c.add(ii, i)
        >>> iii = item.Item()
        >>> c.add(iii, ii)
        >>> list(c.get_ancestors(i))
        []
        >>> list(c.get_ancestors(ii)) # doctest: +ELLIPSIS
        [<gaphas.item.Item ...>]
        >>> list(c.get_ancestors(iii)) # doctest: +ELLIPSIS
        [<gaphas.item.Item ...>, <gaphas.item.Item ...>]
        """
        return self._tree.get_ancestors(item)

    def get_children(self, item):
        """See `tree.Tree.get_children()`.

        >>> c = Canvas()
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> ii = item.Item()
        >>> c.add(ii, i)
        >>> iii = item.Item()
        >>> c.add(iii, ii)
        >>> list(c.get_children(iii))
        []
        >>> list(c.get_children(ii)) # doctest: +ELLIPSIS
        [<gaphas.item.Item ...>]
        >>> list(c.get_children(i)) # doctest: +ELLIPSIS
        [<gaphas.item.Item ...>]
        """
        return self._tree.get_children(item)

    def get_all_children(self, item):
        """See `tree.Tree.get_all_children()`.

        >>> c = Canvas()
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> ii = item.Item()
        >>> c.add(ii, i)
        >>> iii = item.Item()
        >>> c.add(iii, ii)
        >>> list(c.get_all_children(iii))
        []
        >>> list(c.get_all_children(ii)) # doctest: +ELLIPSIS
        [<gaphas.item.Item ...>]
        >>> list(c.get_all_children(i)) # doctest: +ELLIPSIS
        [<gaphas.item.Item ...>, <gaphas.item.Item ...>]
        """
        return self._tree.get_all_children(item)

    def connect_item(
        self, item, handle, connected, port, constraint=None, callback=None
    ):
        self._connections.connect_item(
            item, handle, connected, port, constraint, callback
        )

    def disconnect_item(self, item, handle=None):
        self._connections.disconnect_item(item, handle)

    def remove_connections_to_item(self, item):
        self._connections.remove_connections_to_item(item)

    def reconnect_item(self, item, handle, port=None, constraint=None):
        """Update an existing connection.

        This is used to provide a new constraint to the connection.
        ``item`` and ``handle`` are the keys to the to-be-updated
        connection.
        """
        self._connections.reconnect_item(item, handle, port, constraint)

    def get_connection(self, handle):
        return self._connections.get_connection(handle)

    def get_connections(self, item=None, handle=None, connected=None, port=None):
        return self._connections.get_connections(item, handle, connected, port)

    def sort(self, items):
        """Sort a list of items in the order in which they are traversed in the
        canvas (Depth first).

        >>> c = Canvas()
        >>> from gaphas import item
        >>> i1 = item.Line()
        >>> c.add(i1)
        >>> i2 = item.Line()
        >>> c.add(i2)
        >>> i3 = item.Line()
        >>> c.add (i3)
        >>> c.update() # ensure items are indexed
        >>> s = c.sort([i2, i3, i1])
        >>> s[0] is i1 and s[1] is i2 and s[2] is i3
        True
        """
        return self._tree.order(items)

    def get_matrix_i2c(self, item: Item) -> matrix.Matrix:
        """Get the Item to Canvas matrix for ``item``.

        item:
            The item who's item-to-canvas transformation matrix should
            be found
        calculate:
            True will allow this function to actually calculate it,
            instead of raising an `AttributeError` when no matrix is
            present yet. Note that out-of-date matrices are not
            recalculated.
        """
        m = item.matrix

        parent = self._tree.get_parent(item)
        if parent is not None:
            m = m.multiply(self.get_matrix_i2c(parent))
        return m

    @observed
    def request_update(self, item, update=True, matrix=True):
        """Set an update request for the item.

        >>> c = Canvas()
        >>> from gaphas import item
        >>> i = item.Item()
        >>> ii = item.Item()
        >>> c.add(i)
        >>> c.add(ii, i)
        >>> len(c._dirty_items)
        0
        >>> c.update_now()
        >>> len(c._dirty_items)
        0
        """
        if update:
            self._dirty_items.add(item)
        if matrix:
            self._dirty_matrix_items.add(item)

        self.update()

    reversible_method(request_update, reverse=request_update)

    def request_matrix_update(self, item):
        """Schedule only the matrix to be updated."""
        self.request_update(item, update=False, matrix=True)

    def require_update(self):
        """Returns ``True`` or ``False`` depending on if an update is needed.

        >>> c=Canvas()
        >>> c.require_update()
        False
        >>> from gaphas import item
        >>> i = item.Item()
        >>> c.add(i)
        >>> c.require_update()
        False

        Since we're not in a GTK+ mainloop, the update is not scheduled
        asynchronous. Therefore ``require_update()`` returns ``False``.
        """
        return bool(self._dirty_items)

    @AsyncIO(single=True)
    def update(self):
        """Update the canvas, if called from within a gtk-mainloop, the update
        job is scheduled as idle job."""
        self.update_now()

    def _pre_update_items(self, items):
        create_update_context = self._create_update_context
        contexts = {}
        for item in items:
            context = create_update_context(item)
            item.pre_update(context)
            contexts[item] = context
        return contexts

    def _post_update_items(self, items, contexts):
        create_update_context = self._create_update_context
        for item in items:
            context = contexts.get(item)
            if not context:
                context = create_update_context(item)
            item.post_update(context)

    @nonrecursive
    def update_now(self):
        """Perform an update of the items that requested an update."""
        sort = self.sort

        def dirty_items_with_ancestors():
            for item in self._dirty_items:
                yield item
                yield from self._tree.get_ancestors(item)

        dirty_items = list(reversed(sort(dirty_items_with_ancestors())))

        try:
            # allow programmers to perform tricks and hacks before item
            # full update (only called for items that requested a full update)
            contexts = self._pre_update_items(dirty_items)

            dirty_matrix_items = set(self._dirty_matrix_items)
            self._dirty_matrix_items.clear()

            # solve all constraints
            self.solver.solve()

            # no matrix can change during constraint solving
            assert (
                not self._dirty_matrix_items
            ), f"No matrices may have been marked dirty ({self._dirty_matrix_items})"

            # item's can be marked dirty due to external constraints solving
            if len(dirty_items) != len(self._dirty_items):
                dirty_items = list(reversed(sort(self._dirty_items)))

            # keep it here, since we need up to date matrices for the solver
            for d in dirty_matrix_items:
                d.matrix_i2c.set(*self.get_matrix_i2c(d))

            # ensure constraints are still true after normalization
            self.solver.solve()

            # item's can be marked dirty due to normalization and solving
            if len(dirty_items) != len(self._dirty_items):
                dirty_items = list(reversed(sort(self._dirty_items)))

            self._dirty_items.clear()

            self._post_update_items(dirty_items, contexts)

        except Exception as e:
            logging.error("Error while updating canvas", exc_info=e)

        assert (
            len(self._dirty_items) == 0 and len(self._dirty_matrix_items) == 0
        ), f"dirty: {self._dirty_items}; matrix: {self._dirty_matrix_items}"

        self._update_views(dirty_items, dirty_matrix_items)

    def register_view(self, view):
        """Register a view on this canvas.

        This method is called when setting a canvas on a view and should
        not be called directly from user code.
        """
        self._registered_views.add(view)

    def unregister_view(self, view):
        """Unregister a view on this canvas.

        This method is called when setting a canvas on a view and should
        not be called directly from user code.
        """
        self._registered_views.discard(view)

    def _update_views(self, dirty_items=(), dirty_matrix_items=(), removed_items=()):
        """Send an update notification to all registered views."""
        for v in self._registered_views:
            v.request_update(dirty_items, dirty_matrix_items, removed_items)


# Additional tests in @observed methods
__test__ = {
    "Canvas.add": Canvas.add,
    "Canvas.remove": Canvas.remove,
    "Canvas.request_update": Canvas.request_update,
}
