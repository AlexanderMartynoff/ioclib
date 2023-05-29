from typing import (
    Any,
    Generic,
    Callable,
    Tuple,
    Type,
    TypeVar,
    List,
    ContextManager,
    Iterator,
    Generator,
    Union,
    ClassVar,
    cast,
    get_args,
    get_origin)
from typing_extensions import ParamSpec, Literal, Self
from functools import cached_property, partial, update_wrapper
from inspect import Parameter, signature as get_signature, Signature
from contextvars import ContextVar
from dataclasses import dataclass, replace
from contextlib import contextmanager, suppress
from collections import abc
from threading import Lock


P = ParamSpec('P')
T = TypeVar('T')


void = object()


def inject(name: str | None = None, cls: Type[Any] | None = None) -> Any:
    return Requirement(name, cls, 'injector', void)


@dataclass(frozen=True)
class Requirement(Generic[T]):
    name: str | None
    type: Type[T] | None
    location: str
    default: T | None

    @cached_property
    def types(self) -> Tuple[Type[Any]]:
        origin = get_origin(self.type)

        if origin is Union:
            return tuple(arg for arg in get_args(self.type) if arg is not None)
        elif origin is not None:
            raise TypeError(f'Only `Union` generic support, not `{origin}`')

        return self.type,

    def issuperclass(self, cls) -> bool:
        if not isinstance(cls, tuple):
            cls = cls,

        return any(issubclass(cls, self.types) for cls in cls)


class Definition(Generic[T]):
    classes: list[Type[Self]] = []
    scope: ClassVar[str]

    def __init_subclass__(cls) -> None:
        cls.classes.append(cls)

    def __init__(self, signature: Signature, factory: Callable[..., ContextManager[T]], name: str) -> None:
        self._signature = signature
        self._factory = factory
        self._name = name

        self._lock = Lock()

    def enter(self) -> None:
        raise NotImplementedError()

    def exit(self, error_type: Type[Exception], error: Exception, tb: Any) -> None:
        raise NotImplementedError()

    @property
    def lock(self) -> Lock:
        return self._lock

    @property
    def instance(self) -> T | None:
        raise NotImplementedError()

    @property
    def type(self) -> Type[T]:
        origin = get_origin(self._signature.return_annotation)

        if not issubclass(origin, abc.Iterator):
            raise TypeError()

        arg, = get_args(self._signature.return_annotation)

        return arg


class SingletonDefinition(Definition[T]):
    scope = 'singleton'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self._instance: T | None = None
        self._manager: ContextManager[T] | None = None

    def enter(self) -> None:
        manager = self._factory()

        self._manager = manager
        self._instance = manager.__enter__()

    def exit(self, error_type: Type[Exception], error: Exception, tb: Any) -> None:
        if not self._manager:
            return

        self._manager.__exit__(error_type, error, tb)
        self._manager = None
        self._instance = None

    @property
    def instance(self) -> T | None:
        return self._instance


class ContextDefinition(Definition[T]):
    scope = 'context'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self._instance = ContextVar[T | None]('instance', default=None)
        self._manager = ContextVar[ContextManager[T] | None]('manager', default=None)

    def enter(self) -> None:
        manager = self._factory()

        self._manager.set(manager)
        self._instance.set(manager.__enter__())

    def exit(self, error_type: Type[Exception], error: Exception, tb: Any) -> None:
        manager = self._manager.get()

        if not manager:
            return

        try:
            manager.__exit__(error_type, error, tb)
        finally:
            self._manager.set(None)
            self._instance.set(None)

    @property
    def instance(self) -> T | None:
        return self._instance.get()


class Injector:
    def __init__(self, plugins: List[Callable] | None = None) -> None:
        self._plugins = plugins
        self._definitions: List[Definition[Any]] = []

    def define(self,
               scope: Literal['context', 'singleton'],
               name: str | None = None) -> Callable[[Callable[P, Iterator[T]]], Callable[P, ContextManager[T]]]:

        def definer(function: Callable[P, Iterator[T]]) -> Callable[P, ContextManager[T]]:
            factory = contextmanager(function)

            for cls in Definition.classes:
                if cls.scope == scope:
                    self._definitions.append(cls(
                        signature=get_signature(function),
                        factory=factory,
                        name=name,
                    ))
                    break

            return factory

        return definer

    def release(self, factories, error, error_type, tb) -> None:
        for definition in self._definitions:
            if not factories or definition._factory in factories:
                definition.exit(error, error_type, tb)

    @contextmanager
    def entry(self, release_factories=None) -> Generator[None, Any, None]:
        try:
            yield
        except Exception as error:
            self.release(release_factories, type(error), error, None)
            raise

        self.release(release_factories, None, None, None)

    def injectable(self, function: Callable[P, T]) -> Callable[P, T]:
        return update_wrapper(Injectable(self, function), function)

    def _get(self, requirement: Requirement[T]) -> T:
        definition = self._get_definition(requirement)

        if not definition:
            raise LookupError()

        if definition.instance:
            return definition.instance

        with definition.lock:
            if not definition.instance:
                definition.enter()

        return definition.instance

    def _get_extra(self, requirement: Requirement[T], args=None, kwargs=None) -> T:
        for plugin in self._plugins or []:
            with suppress(LookupError):
                value = plugin(requirement, args, kwargs)

                if value:
                    return value

        if requirement.default is not void:
            return requirement.default

        raise LookupError()

    def _get_definition(self, requirement: Requirement[T]) -> Definition[T] | None:
        assert requirement.type

        for definition in self._definitions:
            if requirement.issuperclass(definition.type) and (
                    definition._name is None or definition._name == requirement.name):
                return cast(Definition[T], definition)

        return None


class Injectable(Generic[T]):
    def __init__(self, injector: Injector, function: Callable[P, T]) -> None:
        self._injector = injector
        self._function = function
        self._signature = get_signature(function)

    def __call__(self, *args: Any, **kwargs: Any) -> T:
        for position, parameter in enumerate(self._signature.parameters.values()):
            requirement = parameter.default

            if not isinstance(requirement, Requirement):
                continue

            requirement = replace(
                requirement,
                type=requirement.type or parameter.annotation,
                name=requirement.name or parameter.name,
            )

            arg = void

            if parameter.kind in [Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD]:
                with suppress(IndexError):
                    arg = args[position]

            if arg is void and parameter.kind in [Parameter.KEYWORD_ONLY, Parameter.POSITIONAL_OR_KEYWORD]:
                with suppress(KeyError):
                    arg = kwargs[parameter.name]

            if arg is void:
                try:
                    value = self._injector._get(requirement)
                except LookupError:
                    value = self._injector._get_extra(requirement, args, kwargs)

                kwargs[parameter.name] = value

        return self._function(*args, **kwargs)

    def __get__(self, instance, cls) -> Callable[P, T]:
        return partial(self, instance if instance else cls)
