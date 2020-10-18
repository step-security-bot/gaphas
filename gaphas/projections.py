from gaphas.connector import Position
from gaphas.matrix import Matrix
from gaphas.solver import Projection, Variable


class MatrixProjection:
    def __init__(self, pos: Position, matrix: Matrix):
        self._orig_pos = pos
        self.matrix = matrix
        self._x = Variable(0.0, pos.strength)
        self._y = Variable(0.0, pos.strength)
        self._update_projected_pos()

    def _update_projected_pos(self):
        self._x.value, self._y.value = self.matrix.transform_point(*self._orig_pos)  # type: ignore[misc]

    def _update_orig_pos(self):
        inv = Matrix(*self.matrix)  # type: ignore[misc]
        inv.invert()
        self._orig_pos.x, self._orig_pos.y = inv.transform_point(self._x, self._y)  # type: ignore[arg-type]

    def _set_x(self, x):
        self._x.value = x
        self._update_orig_pos()

    def _set_y(self, y):
        self._y.value = y
        self._update_orig_pos()

    x = property(lambda s: s._x, _set_x)
    y = property(lambda s: s._y, _set_y)


# Deprecated:


class VariableProjection(Projection):
    """Project a single `solver.Variable` to another space/coordinate system.

    The value has been set in the "other" coordinate system. A
    callback is executed when the value changes. The callback should set the original value.

    It's a simple Variable-like class, following the Projection protocol:

    >>> def notify_me(val):
    ...     print('new value', val)
    >>> p = VariableProjection('var placeholder', 3.0, callback=notify_me)
    >>> p.value
    3.0
    >>> p.value = 6.5
    new value 6.5
    """

    def __init__(self, var, value, callback):
        super().__init__(var)
        self._value = value
        self._callback = callback

    def _set_value(self, value):
        self._value = value
        self._callback(value)
        self.notify()

    def add_handler(self, handler):
        super().add_handler(handler)

    def remove_handler(self, handler):
        super().remove_handler(handler)

    value = property(lambda s: s._value, _set_value)

    def variable(self):
        return self._var


class CanvasProjection:
    """Project a point as Canvas coordinates.  Although this is a projection,
    it behaves like a tuple with two Variables (Projections).

    >>> canvas = Canvas()
    >>> from gaphas.item import Element
    >>> a = Element()
    >>> canvas.add(a)
    >>> a.matrix.translate(30, 2)
    >>> canvas.request_matrix_update(a)
    >>> canvas.update_now()
    >>> canvas.get_matrix_i2c(a)
    cairo.Matrix(1, 0, 0, 1, 30, 2)
    >>> p = CanvasProjection(a.handles()[2].pos, a)
    >>> a.handles()[2].pos
    <Position object on (10, 10)>
    >>> p[0].value
    40.0
    >>> p[1].value
    12.0
    >>> p[0].value = 63
    >>> p._point
    <Position object on (33, 10)>

    When the variables are retrieved, new values are calculated.
    """

    def __init__(self, point, item):
        self._point = point
        self._item = item

    def _on_change_x(self, value):
        item = self._item
        self._px = value
        self._point.x.value, self._point.y.value = item.canvas.get_matrix_c2i(
            item
        ).transform_point(value, self._py)
        item.canvas.request_update(item, matrix=False)

    def _on_change_y(self, value):
        item = self._item
        self._py = value
        self._point.x.value, self._point.y.value = item.canvas.get_matrix_c2i(
            item
        ).transform_point(self._px, value)
        item.canvas.request_update(item, matrix=False)

    def _get_value(self):
        """Return two delegating variables.

        Each variable should contain a value attribute with the real
        value.
        """
        item = self._item
        x, y = self._point.x, self._point.y
        self._px, self._py = item.canvas.get_matrix_i2c(item).transform_point(x, y)
        return self._px, self._py

    pos = property(
        lambda self: list(
            map(
                VariableProjection,
                self._point,
                self._get_value(),
                (self._on_change_x, self._on_change_y),
            )
        )
    )

    def __getitem__(self, key):
        # Note: we can not use bound methods as callbacks, since that will
        #       cause pickle to fail.
        return self.pos[key]

    def __iter__(self):
        return iter(self.pos)
