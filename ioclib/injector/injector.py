from typing import (
    Any,
    Callable,
    ContextManager,
    Iterator,
    Union,
    Self,
    ClassVar,
    cast,
    get_args,
    get_origin)
from functools import cached_property, wraps, partial
from dataclasses import dataclass, replace
from contextlib import contextmanager, suppress, ExitStack
import inspect


Nothing: Any = object()


def requirement(name: str = 'default', cls: type[Any] | None = None) -> Any:
    return Requirement[Any](name, cls, 'injector', Nothing)


@dataclass(frozen=True)
class Requirement[T]:
    name: str
    cls: type[T] | None
    location: str
    default: T | None

    @cached_property
    def clases(self) -> tuple[type, ...]:
        if not self.cls:
            raise ValueError()

        cls = get_origin(self.cls)

        if cls is Union:
            return tuple(arg for arg in get_args(self.cls) if arg is not None)
        elif cls is not None:
            raise TypeError(f'Only `Union` generic support, not `{cls}`')

        return self.cls,

    def issuperclass(self, cls: tuple[type[Any]] | type[Any]) -> bool:
        if not isinstance(cls, tuple):
            cls = cls,

        return any(issubclass(cls, self.clases) for cls in cls)


class Definition[T]:
    register: ClassVar[dict[str, type[Self]]] = {}
    mode: str | None = None
    cls: type[T]

    def __init_subclass__(cls) -> None:
        if not cls.mode:
            return

        if cls.mode in cls.register:
            raise KeyError(f'"{cls.mode}" already exists')

        cls.register[cls.mode] = cls

    def __init__(self, name: str, cls: type[T]) -> None:
        self.name = name
        self.cls = cls

    def __enter__(self) -> Any:
        pass

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        pass

    def __str__(self) -> str:
        return f'<{self.name}:{self.cls.__name__}>'

    def value(self, options: dict[str, Any] | None = None) -> ContextManager[T]:
        raise NotImplementedError()


class ContextManagerDefinition[T](Definition[T]):
    def __init__(self, name, context_manager_factory: Callable[..., ContextManager[T]]) -> None:
        self._context_manager_factory = context_manager_factory
        self._context_manager_factory_signature = inspect.signature(context_manager_factory)

        cls, = get_args(self._context_manager_factory_signature.return_annotation)

        super().__init__(name, cls)

    def __enter__(self) -> Any:
        pass

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        pass


class SingletonDefinition[T](ContextManagerDefinition[T]):
    abstract: ClassVar[bool] = True
    mode: str = 'singleton'

    _value_manager: ContextManager[T]
    _value: T

    def __enter__(self) -> Any:
        self._value_manager = self._context_manager_factory()
        self._value = self._value_manager.__enter__()

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        self._value_manager.__exit__(None, None, None)

        del self._value_manager
        del self._value

    @contextmanager
    def value(self, options: dict[str, Any] | None = None) -> Iterator[T]:
        if not self._value:
            raise ValueError()

        yield self._value


class TransientDefinition[T](ContextManagerDefinition[T]):
    abstract: ClassVar[bool] = True
    mode: str = 'transient'

    def value(self, options: dict[str, Any] | None = None) -> ContextManager[T | None]:
        return self._context_manager_factory()


type InjectorDefiner[T, **P] = Callable[[Callable[P, Iterator[T]]], Callable[P, Iterator[T]]]


class Injector:
    def __init__(self) -> None:
        self._definitions: list[ContextManagerDefinition[Any]] = []

    def __enter__(self) -> Any:
        for definition in self._definitions:
            definition.__enter__()

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        for definition in self._definitions:
            definition.__exit__(exc_type, exc_value, traceback)

    def executor[T, **P](self, function: Callable[P, T]) -> Callable[P, T]:
        """ Example:

            ```
            @injector.executor
            def function(service: Service = requirement()):
                ...
            
            function()  # `service` will inject implicit by injector
            ```
        """

        return wraps(function)(Executor(self, function))

    def define[T, **P](self, scope: str, name: str = 'default') -> InjectorDefiner[T, P]:
        """ Example:

            ```
            @injector.define('singleton')
            def service_definition() -> Iterator[Service]:
                yield Service()
            ```
        """

        Cls = ContextManagerDefinition.register[scope]  # noqa

        def definer(function: Callable[P, Iterator[T]]) -> Callable[P, Iterator[T]]:
            self._definitions.append(Cls(
                name=name,
                context_manager_factory=contextmanager(function),
            ))

            return function

        return definer

    def search[T](self, requirement: Requirement[T]) -> ContextManagerDefinition[T] | None:
        for definition in self._definitions:
            if requirement.issuperclass(definition.cls) and (
                    definition.name is None or definition.name == requirement.name):
                return definition

    def value[T](self,
                 requirement: Requirement[T],
                 args: tuple[Any, ...] | None = None,
                 kwargs: dict[str, Any] | None = None) -> ContextManager[T]:

        definition = self.search(requirement)

        if not definition:
            raise LookupError()

        return definition.value({'requirement': requirement, 'args': args, 'kwargs': kwargs})


class Executor[T, **P]:
    def __init__(self, injector: Injector, function: Callable[P, T]) -> None:
        self._injector = injector
        self._function = function
        self._signature = inspect.signature(self._function)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:  # type: ignore (type checking incorrect with retutn inside ExitStack)
        injections: dict[str, ContextManager[Any]] = {}

        for position, parameter in enumerate(self._signature.parameters.values()):
            requirement = parameter.default

            if not isinstance(requirement, Requirement):
                continue

            requirement = replace(
                requirement, cls=requirement.cls or parameter.annotation, name=requirement.name or parameter.name)

            requirement = cast(Requirement[Any], requirement)

            arg = Nothing

            if parameter.kind in [inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD]:
                with suppress(IndexError):
                    arg = args[position]

            if arg is Nothing and parameter.kind in [inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD]:
                with suppress(KeyError):
                    arg = kwargs[parameter.name]

            if arg is Nothing:
                injections[parameter.name] = self._injector.value(requirement)

        with ExitStack() as stack:
            kwargs = kwargs | {
                name: stack.enter_context(injection) for name, injection in injections.items()
            }  # type: ignore

            return self._function(*args, **kwargs)
 
    def __get__(self, instance: Any | None, cls: type[Any]) -> Callable[..., T]:
        return partial(self, instance or cls)
