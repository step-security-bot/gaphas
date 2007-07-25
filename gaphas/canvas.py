"""
A Canvas owns a set of Items and acts as a container for both the items
and a constraint solver.
"""

__version__ = "$Revision$"
# $HeadURL$

import cairo
from cairo import Matrix
from gaphas import tree
from gaphas import solver
from gaphas.decorators import nonrecursive, async, PRIORITY_HIGH_IDLE
from state import observed, reversible_method, reversible_pair
from gaphas.sort import Sorter


class Context(object):
    """
    Context used for updating and drawing items in a drawing canvas.

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
        raise AttributeError, 'context is not writable'


class Canvas(object):
    """
    Container class for items.

    Attributes:
     - projector: canvas constraint projector between item and canvas
       coordinates
     - sorter: items sorter in order used to add items to canvas
     - _canvas_constraints: constraints set between canvas items
    """

    def __init__(self):
        self._tree = tree.Tree()
        self._solver = solver.Solver()
        self._dirty_items = set()
        self._dirty_matrix_items = set()

        self._registered_views = set()
        self._canvas_constraints = {}

        self._sorter = Sorter(self)
        #self._sorter = tree.TreeSorter(self._tree)

    sorter = property(lambda s: s._sorter)
    
    solver = property(lambda s: s._solver)

    @observed
    def add(self, item, parent=None):
        """
        Add an item to the canvas

            >>> c = Canvas()
            >>> from gaphas import item
            >>> i = item.Item()
            >>> c.add(i)
            >>> len(c._tree.nodes)
            1
            >>> i._canvas is c
            True
        """
        assert item not in self._tree.nodes, 'Adding already added node %s' % item
        item.canvas = self
        self._tree.add(item, parent)
        item._sort_key = self.sorter.get_key()
        self._canvas_constraints[item] = {}

        # TODO: enable for TreeSorter
        #self._sorter.reindex()

        for v in self._registered_views:
            v.update_matrix(item)

        self.request_update(item)
        self._update_views((item,))


    @observed
    def _remove(self, item):
        """
        Remove is done in a separate, @observed, method so the undo system
        can restore removed items in the right order.
        """
        item.canvas = None
        self._tree.remove(item)
        self.remove_connections_to_item(item)
        del self._canvas_constraints[item]
        self._update_views((item,))
        self._dirty_items.discard(item)
        self._dirty_matrix_items.discard(item)

    def remove(self, item):
        """
        Remove item from the canvas

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
        self._remove(item)

    reversible_pair(add, _remove,
                    bind1={'parent': lambda self, item: self.get_parent(item)})


    def add_canvas_constraint(self, item, handle, c):
        """
        Add constraint between items.

        Parameters:
         - item: item holding constraint
         - handle: handle holding constraint
         - c: constraint between items
        """
        if item not in self._canvas_constraints:
            raise ValueError, 'Item not added to canvas'

        i_cons = self._canvas_constraints[item]
        if handle not in i_cons:
            i_cons[handle] = set()
        i_cons[handle].add(c)
        self._solver.add_constraint(c)


    def remove_canvas_constraint(self, item, handle, c=None):
        """
        Remove constraint set between item.

        If constraint is not set then all constraints are removed for given
        item and handle.

        Parameters:
         - item: item holding constraint
         - handle: handle holding constraint
         - c: constraint between items
        """
        if item not in self._canvas_constraints:
            raise ValueError, 'Item not added to canvas'

        i_cons = self._canvas_constraints[item]

        if c is None: # remove all handle's constraints
            h_cons = i_cons[handle]
            for c in h_cons:
                self._solver.remove_constraint(c)
            h_cons.clear()
        else:
            # remove specific constraint
            self._solver.remove_constraint(c)
            i_cons[handle].remove(c)


    def canvas_constraints(self, item):
        """
        Get all constraints set between items for specific item.
        """
        if item not in self._canvas_constraints:
            raise ValueError, 'Item not added to canvas'

        i_cons = self._canvas_constraints[item]

        for cons in i_cons.values():
            for c in cons:
                yield c


    def remove_connections_to_item(self, item):
        """
        Remove all connections (handles connected to and constraints)
        for a specific item.
        This is some brute force cleanup (e.g. if constraints are referenced
        by items, those references are not cleaned up).

        This method implies the constraint used to keep the handle in place
        is connected to Handle.connect_constraint.
        """
        for i, h in self.get_connected_items(item):
            #self._solver.remove_constraint(h.connect_constraint)
            h.disconnect()
            # Never mind..
            h.connected_to = None
            h.disconnect = lambda: 0

    def get_all_items(self):
        """
        Get a list of all items
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
        """
        Return the root items of the canvas.

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

    def reparent(self, item, parent):
        """
        Set new parent for an item.
        """
        self._tree.reparent(item, parent)


    def get_parent(self, item):
        """
        See tree.Tree.get_parent()
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
        """
        See tree.Tree.get_ancestors()
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
        """
        See tree.Tree.get_children()
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
        """
        See tree.Tree.get_all_children()
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

    def get_connected_items(self, item):
        """
        Return a set of items that are connected to @item.
        The list contains tuples (item, handle). As a result an item may be
        in the list more than once (depending on the number of handles that
        are connected). If @item is connected to itself it will also appear
        in the list.

            >>> c = Canvas()
            >>> from gaphas import item
            >>> i = item.Line()
            >>> c.add(i)
            >>> ii = item.Line()
            >>> c.add(ii)
            >>> iii = item.Line()
            >>> c.add (iii)
            >>> i.handles()[0].connected_to = ii
            >>> list(c.get_connected_items(i))
            []
            >>> ii.handles()[0].connected_to = iii
            >>> list(c.get_connected_items(ii)) # doctest: +ELLIPSIS
            [(<gaphas.item.Line ...>, <Handle object on (0, 0)>)]
            >>> list(c.get_connected_items(iii)) # doctest: +ELLIPSIS
            [(<gaphas.item.Line ...>, <Handle object on (0, 0)>)]
        """
        connected_items = set()
        for i in self.get_all_items():
            for h in i.handles():
                if h.connected_to is item:
                    connected_items.add((i, h))
        return connected_items

    def get_matrix_i2c(self, item, calculate=False):
        """
        Get the Item to World matrix for @item.

        item: The item who's item-to-world transformation matrix should be
              found
        calculate: True will allow this function to actually calculate it,
              in stead of raising an AttributeError when no matrix is present
              yet. Note that out-of-date matrices are not recalculated.
        """
        if item._matrix_i2c is None or calculate:
            self.update_matrix(item, recursive=False)
        return item._matrix_i2c


    def get_matrix_c2i(self, item, calculate=False):
        """
        Get the World to Item matrix for @item.
        See get_matrix_i2w().
        """
        if item._matrix_c2i is None or calculate:
            self.update_matrix(item, recursive=False)
        return item._matrix_c2i


    @observed
    def request_update(self, item):
        """
        Set an update request for the item. 

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
        self._dirty_items.add(item)
        self._dirty_matrix_items.add(item)

        # Also add update requests for parents of item
        parent = self._tree.get_parent(item)
        while parent:
            self._dirty_items.add(parent)
            parent = self._tree.get_parent(parent)
        self.update()

    reversible_method(request_update, reverse=request_update)

    @observed
    def request_matrix_update(self, item):
        """
        Schedule only the matrix to be updated.
        """
        self._dirty_matrix_items.add(item)
        self.update()

    reversible_method(request_matrix_update, reverse=request_matrix_update)

    def require_update(self):
        """
        Returns True or False depending on if an update is needed.

            >>> c=Canvas()
            >>> c.require_update()
            False
            >>> from gaphas import item
            >>> i = item.Item()
            >>> c.add(i)
            >>> c.require_update()
            False

        Since we're not in a GTK+ mainloop, the update is not scheduled
        asynchronous. Therefor require_update() returns False.
        """
        return bool(self._dirty_items)

    @async(single=True, priority=PRIORITY_HIGH_IDLE)
    def update(self):
        """
        Update the canvas, if called from within a gtk-mainloop, the
        update job is scheduled as idle job.
        """
        self.update_now()

    @nonrecursive
    def update_now(self):
        """
        Peform an update of the items that requested an update.
        """
        sort = self._sorter.sort
        # Order the dirty items, so they are updated bottom to top
        dirty_items = sort(self._dirty_items, reverse=True)

        # dirty_items is a subset of dirty_matrix_items
        dirty_matrix_items = set(self._dirty_matrix_items)
        try:
            cairo_context = self._obtain_cairo_context()

            for item in dirty_matrix_items:
                self._update_handles(item)

            context_map = dict()
            for item in dirty_items:
                c = Context(cairo=cairo_context)
                context_map[item] = c
                try:
                    item.pre_update(c)
                except Exception, e:
                    print 'Error while pre-updating item %s' % item
                    import traceback
                    traceback.print_exc()

            self.update_matrices()

            self._solver.solve()

            dirty_matrix_items.update(self._dirty_matrix_items)
            self.update_matrices()

            # Also need to set up the dirty_items list here, since items
            # may be marked as dirty during maxtrix update or solving.
            dirty_items = sort(self._dirty_items, reverse=True)

            for item in dirty_items:
                try:
                    c = context_map[item]
                except KeyError:
                    c = Context(cairo=cairo_context)
                try:
                    item.update(c)
                except Exception, e:
                    print 'Error while updating item %s' % item
                    import traceback
                    traceback.print_exc()

        finally:
            self._update_views(self._dirty_items, dirty_matrix_items)
            self._dirty_items.clear()

    def update_matrices(self):
        """
        Update the matrix of the items scheduled to be updated
        *and* their sub-items.

            >>> c = Canvas()
            >>> from gaphas import item
            >>> i = item.Item()
            >>> ii = item.Item()
            >>> i.matrix = (1.0, 0.0, 0.0, 1.0, 5.0, 0.0)
            >>> c.add(i)
            >>> ii.matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 8.0)
            >>> c.add(ii, i)
            >>> c.update_matrices()
            >>> c.get_matrix_i2c(i)
            cairo.Matrix(1, 0, 0, 1, 5, 0)
            >>> c.get_matrix_i2c(ii)
            cairo.Matrix(1, 0, 0, 1, 5, 8)
            >>> len(c._dirty_items)
            0
        """
        dirty_items = self._dirty_matrix_items
        while dirty_items:
            item = dirty_items.pop()
            self.update_matrix(item, recursive=True)

    def update_matrix(self, item, recursive=True):
        """
        Update the World-to-Item (w2i) matrix for @item.
        This is stored as @item._canvas_matrix_i2w.
        @recursive == True will also update child objects.
        """
        parent = self._tree.get_parent(item)

        # First remove from the to-be-updated set.
        self._dirty_matrix_items.discard(item)

        if parent:
            if parent in self._dirty_matrix_items:
                # Parent takes care of updating the child, including current
                self.update_matrix(parent)
                return
            else:
                item._matrix_i2c = Matrix(*item.matrix)
                item._matrix_i2c *= self.get_matrix_i2c(parent)
        else:
            item._matrix_i2c = Matrix(*item.matrix)

        # It's nice to have the W2I matrix present too:
        item._matrix_c2i = Matrix(*item._matrix_i2c)
        item._matrix_c2i.invert()
        for v in self._registered_views:
            v.update_matrix(item)

        # request solving of canvas constraints associated with an item
        request_resolve = self._solver.request_resolve
        for c in self.canvas_constraints(item):
            request_resolve(c)
            
        if recursive:
            for child in self._tree.get_children(item):
                self.update_matrix(child)


    def _update_handles(self, item):
        """
        Update handle positions so the first handle is always located at (0, 0).

        >>> from item import Element
        >>> c = Canvas()
        >>> e = Element()
        >>> c.add(e)
        >>> e.min_width = e.min_height = 0
        >>> c.update_now()
        >>> e.handles()
        [<Handle object on (0, 0)>, <Handle object on (10, 0)>, <Handle object on (10, 10)>, <Handle object on (0, 10)>]

        >>> e.handles()[0].x += 1
        >>> map(float, e.handles()[0].pos)
        [1.0, 0.0]
        >>> c._update_handles(e)
        >>> e.handles()
        [<Handle object on (0, 0)>, <Handle object on (9, 0)>, <Handle object on (9, 10)>, <Handle object on (-1, 10)>]

        >>> e.handles()[0].x += 1
        >>> e.handles()
        [<Handle object on (1, 0)>, <Handle object on (9, 0)>, <Handle object on (9, 10)>, <Handle object on (-1, 10)>]
        >>> c._update_handles(e)
        >>> e.handles()
        [<Handle object on (0, 0)>, <Handle object on (8, 0)>, <Handle object on (8, 10)>, <Handle object on (-2, 10)>]

        """
        handles = item.handles()
        if not handles:
            return
        x, y = map(float, handles[0].pos)
        if x:
            item.matrix.translate(x, 0)
            for h in handles:
                h.x._value -= x
        if y:
            item.matrix.translate(0, y)
            for h in handles:
                h.y._value -= y


    def register_view(self, view):
        """
        Register a view on this canvas. This method is called when setting
        a canvas on a view and should not be called directly from user code.
        """
        self._registered_views.add(view)
        for item in self.get_all_items():
            view.update_matrix(item)


    def unregister_view(self, view):
        """
        Unregister a view on this canvas. This method is called when setting
        a canvas on a view and should not be called directly from user code.
        """
        self._registered_views.discard(view)

    def _update_views(self, dirty_items, dirty_matrix_items=()):
        """
        Send an update notification to all registered views.
        """
        for v in self._registered_views:
            v.request_update(dirty_items, dirty_matrix_items)

    def _obtain_cairo_context(self):
        """
        Try to obtain a Cairo context.

        This is a not-so-clean way to solve issues like calculating the
        bounding box for a piece of text (for that you'll need a CairoContext).
        The Cairo context is created by a View registered as view on this
        canvas. By lack of registered views, a PNG image surface is created
        that is used to create a context.

            >>> c = Canvas()
            >>> c.update_now()
        """
        for view in self._registered_views:
            try:
                return view.window.cairo_create()
            except AttributeError:
                pass
        else:
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 0, 0)
            return cairo.Context(surface)


class VariableProjection(solver.Projection):
    """
    Project a single gaphas.solver.Variable to another space/coordinate system.

    The value has been set in the "other" coordinate system. A callback is
    executed when the value changes.
    
    It's a simple Variable-like class, following the Projection protocol:

    >>> def notify_me(val):
    ...     print 'new value', val
    >>> p = VariableProjection('var placeholder', 3.0, callback=notify_me)
    >>> p.value
    3.0
    >>> p.value = 6.5
    new value 6.5
    """

    def __init__(self, var, value, callback):
        self._var = var
        self._value = value
        self._callback = callback

    def _set_value(self, value):
        self._value = value
        self._callback(value)

    value = property(lambda s: s._value, _set_value)

    def variable(self):
        return self._var


class CanvasProjection(object):
    """
    Project a point as Canvas coordinates.
    Although this is a projection, it behaves like a tuple with two Variables
    (Projections).

    >>> canvas = Canvas()
    >>> from item import Element
    >>> a = Element()
    >>> canvas.add(a)
    >>> a.matrix.translate(30, 2)
    >>> canvas.request_matrix_update(a)
    >>> canvas.update_now()
    >>> canvas.get_matrix_i2c(a)
    cairo.Matrix(1, 0, 0, 1, 30, 2)
    >>> p = CanvasProjection(a.handles()[0].pos, a)
    >>> a.handles()[0].pos
    (Variable(0, 40), Variable(0, 40))
    >>> p[0].value
    30.0
    >>> p[1].value
    2.0
    >>> p[0].value = 10
    >>> p._point
    (Variable(-20, 40), Variable(0, 40))

    TODO: How will this work on rotated variables?
    When the variables are retrieved, new values are calculated.
    """

    def __init__(self, point, item):
        self._point = point
        self._item = item

    def _on_change_x(self, value):
        item = self._item
        self._px = value
        self._point[0].value, self._point[1].value = item.canvas.get_matrix_c2i(item).transform_point(value, self._py)
        item.request_update()

    def _on_change_y(self, value):
        item = self._item
        self._py = value
        self._point[0].value, self._point[1].value = item.canvas.get_matrix_c2i(item).transform_point(self._px, value)
        item.request_update()

    def _get_value(self):
        """
        Return two delegating variables. Each variable should contain
        a value attribute with the real value.
        """
        x, y = self._point
        item = self._item
        self._px, self._py = item.canvas.get_matrix_i2c(item).transform_point(x, y)
        return self._px, self._py

    def __getitem__(self, key):
        return map(VariableProjection,
                   self._point, self._get_value(),
                   (self._on_change_x, self._on_change_y))[key]
        
    def __iter__(self):
        return iter(map(VariableProjection,
                        self._point, self._get_value(),
                        (self._on_change_x, self._on_change_y)))



# Additional tests in @observed methods
__test__ = {
    'Canvas.add': Canvas.add,
    'Canvas.remove': Canvas.remove,
    'Canvas.request_update': Canvas.request_update,
    }


if __name__ == '__main__':
    import doctest
    doctest.testmod(optionflags=doctest.ELLIPSIS)

# vim:sw=4:et
