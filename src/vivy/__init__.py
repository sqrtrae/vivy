from __future__ import annotations

__all__ = [
    # sentinels
    'Unset',
    'UNSET',
    'Default',
    'DEFAULT',
    # core
    'Value',
    'InputValue',
    'VIVY_STORAGE_ATTR',
    # builders
    'scalar',
    'Scalar',
    'list_',
    'List',
    'set_',
    'Set',
    # virtual submodules
    'sentinels',
    'core',
    'builders',
]

import enum
import typing
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from collections.abc import Iterable
from typing import Any
from typing import Literal
from typing import NamedTuple
from typing import Protocol
from typing import Self
from typing import overload

# =========
# sentinels
# =========


class _Sentinel(metaclass=enum.EnumType):
    def __str__(self) -> str:
        return f'<{self.__class__.__name__}>'

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}>'


class Unset(_Sentinel):
    Token = enum.auto()


class Default(_Sentinel):
    Token = enum.auto()


class Missing(_Sentinel):
    Token = enum.auto()


UNSET = Unset.Token
DEFAULT = Default.Token
MISSING = Missing.Token


# ==================
# core functionality
# ==================


type Value[T] = T | Unset
type DefaultValue[T] = Value[T] | Missing
type StoredValue[T] = Value[T] | Missing
type InputValue[T] = Value[T] | Default
type GetValue[T] = Value[T] | Missing
type SetValue[T] = StoredValue[T] | Default

type Factory[T] = Callable[[], T]
type DefaultFactory[T] = Factory[T] | Missing


VIVY_STORAGE_ATTR = '___vivy_storage___'


class HookParams[T, Obj](NamedTuple):
    instance: Obj
    attr_name: str
    stored_value: StoredValue[T]
    default_value: DefaultValue[T]
    call_args: tuple[Any, ...]
    call_kwargs: dict[str, Any]


class BaseAttr[T](ABC):
    @staticmethod
    @abstractmethod
    def mode_hook[Obj](params: HookParams[T, Obj]) -> Literal['get', 'set']: ...

    @staticmethod
    @abstractmethod
    def get_hook[Obj](params: HookParams[T, Obj]) -> GetValue[T]: ...

    @staticmethod
    @abstractmethod
    def set_hook[Obj](params: HookParams[T, Obj]) -> SetValue[T]: ...

    def __init__(
        self,
        *,
        default: DefaultValue[T] = MISSING,
        default_factory: DefaultFactory[T] = MISSING,
    ) -> None:
        if default is not MISSING and default_factory is not MISSING:
            msg = "Can only specify one of 'default' and 'default_factory'."
            raise TypeError(msg)

        if default is not MISSING:
            self._default_factory = lambda: default
        elif default_factory is not MISSING:
            self._default_factory = default_factory
        else:
            self._default_factory = lambda: MISSING

        # is actually set on first call to __get__().
        self._value_caller: Callable[..., Any] | Missing = MISSING

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    @overload
    def __get__(self, instance: None, owner: type) -> Self: ...
    @overload
    def __get__[Obj](
        self,
        instance: Obj,
        owner: type[Obj],
    ) -> Callable[..., Value[T] | Obj]: ...

    def __get__[Obj](
        self,
        instance: Obj,
        owner: type[Obj],
    ) -> Self | Callable[..., Value[T] | Obj]:
        if instance is None:
            return self

        if self._value_caller is MISSING:
            self._prepare_instance(instance)
            self._value_caller = self._make_value_caller(instance)

        return self._value_caller

    @property
    def name(self) -> str:
        return self._name

    def default_value(self) -> DefaultValue[T]:
        return self._default_factory()

    def _get_stored_value(self, instance: object) -> StoredValue[T]:
        return getattr(instance, VIVY_STORAGE_ATTR)[self._name]

    def _set_stored_value(
        self,
        instance: object,
        value: SetValue[T],
    ) -> None:
        if value is DEFAULT:
            if (default_value := self._default_factory()) is MISSING:
                msg = (
                    f'Cannot set value to default for attribute '
                    f'{self._name!r} of '
                    f'{instance.__class__.__name__!r}: '
                    f'attribute has no default value.'
                )
                raise ValueError(msg)
            value = default_value
        getattr(instance, VIVY_STORAGE_ATTR)[self._name] = value

    def _prepare_instance(self, instance: object) -> None:
        if not hasattr(instance, VIVY_STORAGE_ATTR):
            setattr(instance, VIVY_STORAGE_ATTR, {})

        self._set_stored_value(instance, self.default_value())

    def _make_value_caller[Obj](
        self,
        instance: Obj,
    ) -> Callable[..., Value[T] | Obj]:
        def value_caller(*args: Any, **kwargs: Any) -> Value[T] | Obj:
            if len(args) == 1 and len(kwargs) == 0:
                arg = args[0]
                if arg is UNSET or arg is DEFAULT:
                    self._set_stored_value(instance, arg)
                    return instance

            default_value = self._default_factory()
            stored_value = self._get_stored_value(instance)

            params = HookParams(
                instance=instance,
                attr_name=self._name,
                stored_value=stored_value,
                default_value=default_value,
                call_args=args,
                call_kwargs=kwargs,
            )

            if (len(args) == 0 and len(kwargs) == 0) or self.mode_hook(
                params
            ) == 'get':
                ret_value = self.get_hook(params)
                if ret_value is MISSING:
                    msg = (
                        f'Cannot get value for attribute {self._name!r} '
                        f'of {instance.__class__.__name__!r}: '
                        f'missing attribute value.'
                    )
                    raise ValueError(msg)
                return ret_value

            value = self.set_hook(params)
            self._set_stored_value(instance, value)
            return instance

        return value_caller


# =============
# vivy builders
# =============


# these are iterable types that aren't treated as iterable
# by the list/set builders.
_EXCLUDED_ITER_TYPES: list[type] = [
    str,
    bytes,
]


class BaseVivyAttr[T](BaseAttr[T], ABC):
    @staticmethod
    def mode_hook[Obj](params: HookParams[T, Obj]) -> Literal['get', 'set']:
        if params.call_args[0] is MISSING:
            return 'get'
        return 'set'

    @staticmethod
    def get_hook[Obj](params: HookParams[T, Obj]) -> GetValue[T]:
        return params.stored_value


# ~~~~~~
# scalar
# ~~~~~~


class ScalarCaller[T, Obj](Protocol):
    @overload
    def __call__(self, /) -> Value[T]: ...
    @overload
    def __call__(self, value: Unset, /) -> Obj: ...
    @overload
    def __call__(self, value: Default, /) -> Obj: ...
    @overload
    def __call__(self, value: T, /) -> Obj: ...
    def __call__(
        self,
        value: InputValue[T] | Missing = MISSING,
        /,
    ) -> Value[T] | Obj: ...


class Scalar[T](BaseVivyAttr[T]):
    @staticmethod
    def set_hook[Obj](params: HookParams[T, Obj]) -> SetValue[T]:
        return params.call_args[0]

    @overload
    def __get__(self, instance: None, owner: type) -> Self: ...
    @overload
    def __get__[Obj](
        self,
        instance: Obj,
        owner: type[Obj],
    ) -> ScalarCaller[T, Obj]: ...

    def __get__[Obj](
        self,
        instance: Obj,
        owner: type[Obj],
    ) -> Self | Callable[..., Value[T] | Obj]:
        if instance is None:
            return self

        if self._value_caller is MISSING:
            self._prepare_instance(instance)
            self._value_caller = self._make_value_caller(instance)

        return self._value_caller


@overload
def scalar() -> Scalar[Any]: ...
@overload
def scalar[T](*, default: Value[T]) -> Scalar[T]: ...
@overload
def scalar[T](*, default_factory: Factory[T]) -> Scalar[T]: ...


def scalar[T](
    *,
    default: DefaultValue[T] = MISSING,
    default_factory: DefaultFactory[T] = MISSING,
) -> Scalar[T]:
    return Scalar(default=default, default_factory=default_factory)


# ~~~~
# list
# ~~~~


class ListCaller[T, Obj](Protocol):
    @overload
    def __call__(self, /) -> Value[list[T]]: ...
    @overload
    def __call__(self, value: Unset, /) -> Obj: ...
    @overload
    def __call__(self, value: Default, /) -> Obj: ...
    @overload
    def __call__(
        self,
        *values: T | Iterable[T],
        on_existing: Literal['extend', 'replace'] = ...,
    ) -> Obj: ...
    def __call__(
        self,
        value: InputValue[T | Iterable[T]] | Missing = MISSING,
        *other_values: T | Iterable[T],
        on_existing: Literal['extend', 'replace'] = 'extend',
    ) -> Value[list[T]] | Obj: ...


class List[T](BaseVivyAttr[list[T]]):
    @staticmethod
    def set_hook[Obj](params: HookParams[list[T], Obj]) -> SetValue[list[T]]:
        values: list[T | Iterable[T]] = list(params.call_args)

        on_existing = params.call_kwargs.get('on_existing', 'extend')
        if on_existing not in {'extend', 'replace'}:
            msg = (
                f'Invalid value for on_existing ({on_existing!r}): '
                "expected one of 'extend' or 'replace'."
            )
            raise ValueError(msg)

        set_value: list[T] = []
        for value in values:
            if any(
                isinstance(value, iter_type)
                for iter_type in _EXCLUDED_ITER_TYPES
            ) or not isinstance(value, Iterable):
                set_value.append(typing.cast('T', value))
            else:
                set_value.extend(typing.cast('Iterable[T]', value))

        stored_value = params.stored_value
        if (
            on_existing == 'extend'
            and stored_value is not MISSING
            and stored_value is not UNSET
        ):
            set_value = stored_value + set_value

        return set_value

    @overload
    def __get__(self, instance: None, owner: type) -> Self: ...
    @overload
    def __get__[Obj](
        self,
        instance: Obj,
        owner: type[Obj],
    ) -> ListCaller[T, Obj]: ...

    def __get__[Obj](
        self,
        instance: Obj,
        owner: type[Obj],
    ) -> Self | Callable[..., Value[list[T]] | Obj]:
        if instance is None:
            return self

        if self._value_caller is MISSING:
            self._prepare_instance(instance)
            self._value_caller = self._make_value_caller(instance)

        return self._value_caller


@overload
def list_() -> List[Any]: ...
@overload
def list_[T](*, default: Value[list[T]]) -> List[T]: ...
@overload
def list_[T](*, default_factory: Factory[list[T]]) -> List[T]: ...


def list_[T](
    *,
    default: DefaultValue[list[T]] = MISSING,
    default_factory: DefaultFactory[list[T]] = MISSING,
) -> List[T]:
    return List(default=default, default_factory=default_factory)


# ~~~
# set
# ~~~


class SetCaller[T, Obj](Protocol):
    @overload
    def __call__(self, /) -> Value[set[T]]: ...
    @overload
    def __call__(self, value: Unset, /) -> Obj: ...
    @overload
    def __call__(self, value: Default, /) -> Obj: ...
    @overload
    def __call__(
        self,
        *values: T | Iterable[T],
        on_existing: Literal['union', 'intersection', 'replace'] = ...,
    ) -> Obj: ...
    def __call__(
        self,
        value: InputValue[T | Iterable[T]] | Missing = MISSING,
        *other_values: T | Iterable[T],
        on_existing: Literal['union', 'intersection', 'replace'] = 'union',
    ) -> Value[set[T]] | Obj: ...


class Set[T](BaseVivyAttr[set[T]]):
    @staticmethod
    def set_hook[Obj](params: HookParams[set[T], Obj]) -> SetValue[set[T]]:
        values: list[T | Iterable[T]] = list(params.call_args)

        on_existing = params.call_kwargs.get('on_existing', 'union')
        if on_existing not in {'union', 'intersection', 'replace'}:
            msg = (
                f'Invalid value for on_existing ({on_existing!r}): '
                "expected one of 'union', 'intersection', or 'replace'."
            )
            raise ValueError(msg)

        set_value: set[T] = set()
        for value in values:
            if any(
                isinstance(value, iter_type)
                for iter_type in _EXCLUDED_ITER_TYPES
            ) or not isinstance(value, Iterable):
                set_value.add(typing.cast('T', value))
            else:
                set_value = set_value.union(typing.cast('Iterable[T]', value))

        stored_value = params.stored_value
        if stored_value is not MISSING and stored_value is not UNSET:
            if on_existing == 'union':
                set_value = stored_value | set_value
            elif on_existing == 'intersection':
                set_value = stored_value & set_value

        return set_value

    @overload
    def __get__(self, instance: None, owner: type) -> Self: ...
    @overload
    def __get__[Obj](
        self,
        instance: Obj,
        owner: type[Obj],
    ) -> SetCaller[T, Obj]: ...

    def __get__[Obj](
        self,
        instance: Obj,
        owner: type[Obj],
    ) -> Self | Callable[..., Value[set[T]] | Obj]:
        if instance is None:
            return self

        if self._value_caller is MISSING:
            self._prepare_instance(instance)
            self._value_caller = self._make_value_caller(instance)

        return self._value_caller


@overload
def set_() -> Set[Any]: ...
@overload
def set_[T](*, default: Value[set[T]]) -> Set[T]: ...
@overload
def set_[T](*, default_factory: Factory[set[T]]) -> Set[T]: ...


def set_[T](
    *,
    default: DefaultValue[set[T]] = MISSING,
    default_factory: Factory[set[T]] | Missing = MISSING,
) -> Set[T]:
    return Set(default=default, default_factory=default_factory)


# ==================
# virtual submodules
# ==================


class sentinels:
    Unset = Unset
    Default = Default
    Missing = Missing
    UNSET = UNSET
    DEFAULT = DEFAULT
    MISSING = MISSING


class core:
    Value = Value
    DefaultValue = DefaultValue
    StoredValue = StoredValue
    InputValue = InputValue
    GetValue = GetValue
    SetValue = SetValue
    Factory = Factory
    DefaultFactory = DefaultFactory
    VIVY_STORAGE_ATTR = VIVY_STORAGE_ATTR
    HookParams = HookParams
    BaseAttr = BaseAttr


class builders:
    ScalarCaller = ScalarCaller
    Scalar = Scalar
    scalar = scalar
    ListCaller = ListCaller
    List = List
    list_ = list_
    SetCaller = SetCaller
    Set = Set
    set_ = set_
