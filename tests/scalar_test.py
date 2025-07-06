from __future__ import annotations

import pytest

import vivy
from vivy import ScalarCaller


class MyClass:
    no_default: vivy.Scalar[int] = vivy.scalar()
    unset_default: vivy.Scalar[int] = vivy.scalar(default=vivy.UNSET)
    with_default: vivy.Scalar[int] = vivy.scalar(default=0)
    unset_default_factory: vivy.Scalar[int] = vivy.scalar(
        default_factory=lambda: vivy.UNSET
    )
    with_default_factory: vivy.Scalar[int] = vivy.scalar(
        default_factory=lambda: 31_415_926_535
    )


@pytest.mark.parametrize(
    ('name', 'default_value'),
    [
        pytest.param('no_default', vivy.MISSING, id='no_default'),
        pytest.param('unset_default', vivy.UNSET, id='unset_default'),
        pytest.param('with_default', 0, id='with_default'),
        pytest.param(
            'unset_default_factory', vivy.UNSET, id='unset_default_factory'
        ),
        pytest.param(
            'with_default_factory', 31_415_926_535, id='with_default_factory'
        ),
    ],
)
def test_descriptor_properties(name, default_value):
    attr = getattr(MyClass, name)
    assert isinstance(attr, vivy.Scalar)
    assert attr.name == name
    assert attr.default_value() == default_value


@pytest.mark.parametrize(
    ('name', 'default_value'),
    [
        pytest.param('no_default', vivy.MISSING, id='no_default'),
        pytest.param('unset_default', vivy.UNSET, id='unset_default'),
        pytest.param('with_default', 0, id='with_default'),
        pytest.param(
            'unset_default_factory', vivy.UNSET, id='unset_default_factory'
        ),
        pytest.param(
            'with_default_factory', 31_415_926_535, id='with_default_factory'
        ),
    ],
)
def test_instance_builders(name, default_value):
    obj = MyClass()
    has_default = default_value is not vivy.MISSING
    value_caller: ScalarCaller[int] = getattr(obj, name)

    # test default value behavior
    if has_default:
        assert value_caller() == default_value
    else:
        with pytest.raises(ValueError):
            value_caller()

    # test setting to a value
    value_caller(64)
    assert value_caller() == 64

    # test setting to <UNSET>
    value_caller(vivy.UNSET)
    assert value_caller() == vivy.UNSET

    # test setting to default value
    if has_default:
        value_caller(vivy.DEFAULT)
        assert value_caller() == default_value
    else:
        with pytest.raises(ValueError):
            value_caller(vivy.DEFAULT)

    # test instance object is returned after setting value
    assert value_caller(999) is obj


# the main point behind this test is to ensure there is no
# "cross-contamination" between different builders on the same class.
def test_multiple_builders():
    obj = (
        MyClass()
        .no_default(1)
        .unset_default(2)
        .with_default(3)
        .unset_default_factory(4)
        .with_default_factory(5)
    )

    assert obj.no_default() == 1
    assert obj.unset_default() == 2
    assert obj.with_default() == 3
    assert obj.unset_default_factory() == 4
    assert obj.with_default_factory() == 5

    obj.no_default(vivy.UNSET).unset_default(12345).with_default_factory(
        vivy.DEFAULT
    ).unset_default_factory(54321)

    assert obj.no_default() == vivy.UNSET
    assert obj.unset_default() == 12345
    assert obj.with_default() == 3
    assert obj.unset_default_factory() == 54321
    assert obj.with_default_factory() == 31_415_926_535
