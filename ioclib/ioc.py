from typing import Any, Optional, Callable, Type, TypeVar, List, ContextManager, cast, get_args, get_origin
from typing_extensions import ParamSpec, Literal
from functools import partial, update_wrapper
from inspect import Parameter, signature as get_signature, Signature
from contextvars import ContextVar
from dataclasses import dataclass
from contextlib import contextmanager
from collections import abc
from threading import Lock


P = ParamSpec('P')
T = TypeVar('T')


class _Definition:
    def __init__(self, signature: Signature, factory: Callable[..., ContextManager], scope: str, name: str):
        self.signature = signature
        self.factory = factory
        self.scope = scope
        self.name = name

        self.lock = Lock()

    def enter(self):
        raise NotImplementedError()

    def exit(self, error_type: Type[Exception], error: Exception, tb: Any):
        raise NotImplementedError()

    def get(self):
        raise NotImplementedError()

    @property
    def cls(self):
        cls = get_origin(self.signature.return_annotation)

        if not issubclass(cls, abc.Iterator):
            raise TypeError()

        arg, = get_args(self.signature.return_annotation)

        return arg


class _InstanceDefinition(_Definition):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._instance: Any = None
        self._manager: ContextManager[Any, Any, Any] = None

    def enter(self):
        manager = self.factory()

        self._manager = manager
        self._instance = manager.__enter__()

    def exit(self, error_type: Type[Exception], error: Exception, tb: Any):
        if not self._manager:
            return

        self._manager.__exit__(error_type, error, tb)
        self._manager = None
        self._instance = None

    def get(self):
        return self._instance


class _ContextDefinition(_Definition):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._instance_var = ContextVar(f'instance_{self.cls.__name__}_{self.factory.__name__}', default=None)
        self._manager_var = ContextVar(f'manager_{self.cls.__name__}_{self.factory.__name__}', default=None)

    def enter(self):
        manager = self.factory()

        self._manager_var.set(manager)
        self._instance_var.set(manager.__enter__())

    def exit(self, error_type: Type[Exception], error: Exception, tb: Any):
        manager = self._manager_var.get()

        if not manager:
            return

        manager.__exit__(error_type, error, tb)

        self._manager_var.set(None)
        self._instance_var.set(None)

    def get(self):
        return self._instance_var.get()


class Container:
    def __init__(self):
        self._definitions: List[_Definition] = []

    def _get_definition(self, cls, name=None) -> _Definition:
        for definition in self._definitions:
            if issubclass(definition.cls, cls) and definition.name == name:
                return definition

    def define(self, scope: Literal['context', 'singleton'], name=None) -> Callable[[Callable[P, T]], Callable[P, T]]:
        assert scope in ['context', 'singleton']

        def definer(function: Callable[P, T]) -> Callable[P, T]:
            signature = get_signature(function)
            factory = contextmanager(function)

            if scope == 'context':
                self._definitions.append(_ContextDefinition(
                    signature=signature,
                    factory=factory,
                    scope=scope,
                    name=name,
                ))

            elif scope == 'singleton':
                self._definitions.append(_InstanceDefinition(
                    signature=signature,
                    factory=factory,
                    scope=scope,
                    name=name,
                ))

            return function

        return definer

    def release(self, scopes, error, error_type, tb):
        for definition in self._definitions:
            if definition.scope in scopes:
                definition.exit(error, error_type, tb)

    @contextmanager
    def run(self, release_scopes=None):
        if not release_scopes:
            release_scopes = ['context', 'singleton']

        try:
            yield
        except Exception as error:
            self.release(release_scopes, type(error), error, None)
            raise
        else:
            self.release(release_scopes, None, None, None)

    def get(self, cls: Type[T], name=None) -> T:
        definition = self._get_definition(cls, name)

        if not definition:
            raise LookupError()

        with definition.lock:
            if not definition.get():
                definition.enter()

        return cast(T, definition.get())

    def injectable(self, function: Callable[P, T]) -> Callable[P, T]:
        return update_wrapper(Injector(self, function), function)


class Injector:
    def __init__(self, cr: Container, function: Callable[P, T]):
        self._cr = cr
        self._function = function
        self._requires = []
        self._signature = get_signature(function)

    def __call__(self, *args: Any, **kwargs: Any) -> T:

        for position, parameter in enumerate(self._signature.parameters.values()):
            injection = parameter.default

            if not isinstance(injection, Injection):
                continue

            arg = Parameter.empty

            if parameter.kind in [Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD]:
                try:
                    arg = args[position]
                except IndexError:
                    pass

            if arg is Parameter.empty and parameter.kind in [Parameter.KEYWORD_ONLY, Parameter.POSITIONAL_OR_KEYWORD]:
                try:
                    arg = kwargs[parameter.name]
                except KeyError:
                    pass

            if arg is Parameter.empty:
                kwargs[parameter.name] = self._cr.get(parameter.annotation)

        return self._function(*args, **kwargs)

    def __get__(self, instance, cls) -> Callable[P, T]:
        return partial(self, instance if instance else cls)


@dataclass(frozen=True)
class Injection:
    __name: str
    __cls: Type[Any]

    def __getattr__(self, name: str) -> Any:
        raise TypeError('Probably you forget `@injectable` decorator for callable function')


def injection(name: Optional[str] = None, cls=None) -> Any:
    return Injection(name, cls)
