from gaphas.solver import Variable


def test_equality():
    v = Variable(3)
    w = Variable(3)
    o = Variable(2)

    assert v == 3
    assert 3 == v
    assert v == w
    assert not v == o

    assert v != 2
    assert 2 != v
    assert not 3 != v
    assert v != o


def test_add_to_variable():
    v = Variable(3)

    assert v + 1 == 4
    assert v - 1 == 2
    assert 1 + v == 4
    assert 4 - v == 1


def test_add_to_variable_with_variable():
    v = Variable(3)
    o = Variable(1)

    assert v + o == 4
    assert v - o == 2


def test_mutiplication():
    v = Variable(3)

    assert v * 2 == 6
    assert v / 2 == 1.5
    assert v // 2 == 1

    assert 2 * v == 6
    assert 4.5 / v == 1.5
    assert 4 // v == 1


def test_mutiplication_with_variable():
    v = Variable(3)
    o = Variable(2)

    assert v * o == 6
    assert v / o == 1.5
    assert v // o == 1


def test_comparison():
    v = Variable(3)

    assert v > 2
    assert v < 4
    assert v >= 2
    assert v >= 3
    assert v <= 4
    assert v <= 3

    assert not v > 3
    assert not v < 3
    assert not v <= 2
    assert not v >= 4


def test_inverse_comparison():
    v = Variable(3)

    assert 4 > v
    assert 2 < v
    assert 4 >= v
    assert 3 >= v
    assert 2 <= v
    assert 3 <= v

    assert not 3 > v
    assert not 3 < v
    assert not 4 <= v
    assert not 2 >= v


def test_power():
    v = Variable(3)
    o = Variable(2)

    assert v ** 2 == 9
    assert 2 ** v == 8
    assert v ** o == 9


def test_modulo():
    v = Variable(3)
    o = Variable(2)

    assert v % 2 == 1
    assert 4 % v == 1
    assert v % o == 1
    assert divmod(v, 2) == (1, 1)
    assert divmod(4, v) == (1, 1)
    assert divmod(v, o) == (1, 1)
