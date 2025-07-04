from __future__ import annotations

__all__ = []


import enum
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from typing import Any
from typing import Literal
from typing import NamedTuple
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
    ):
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


# ==================
# virtual submodules
# ==================
