from typing import Any, Optional, Callable, Type, TypeVar, List, cast, ContextManager
from typing_extensions import ParamSpec, Literal
from functools import partial, update_wrapper
from inspect import Parameter, signature as get_signature, Signature
from contextvars import copy_context, ContextVar
from dataclasses import dataclass, field
from contextlib import contextmanager


P = ParamSpec('P')
T = TypeVar('T')


@dataclass
class _Definition:
    signature: Signature
    factory: Callable[..., Any]
    scope: str
    name: str

    def enter(self):
        raise NotImplementedError()

    def exit(self):
        raise NotImplementedError()

    def get(self):
        raise NotImplementedError()

    @property
    def cls(self):
        return self.signature.return_annotation

@dataclass
class _InstanceDefinition(_Definition):
    _instance: Any = None

    def enter(self):
        manager = self.factory()

        self._manager = manager
        self._instance = manager.__enter__()

    def exit(self):
        self._manager.__exit__(None, None, None)
        self._manager = None
        self._instance = None

    def get(self):
        return self._instance


@dataclass
class _ContextDefinition(_Definition):
    _manager_var: ContextVar = field(init=False)
    _instance_var: ContextVar = field(init=False)

    def __post_init__(self):
        self._instance_var = ContextVar(
            f'instance_{self.cls.__name__}_{self.factory.__name__}', default=None)
        self._manager_var = ContextVar(
            f'manager_{self.cls.__name__}_{self.factory.__name__}', default=None)

    def enter(self):
        manager = self.factory()

        self._manager_var.set(manager)
        self._instance_var.set(manager.__enter__())

    def exit(self):
        manager = self._manager_var.get()

        if manager:
            manager.__exit__(None, None, None)

        self._manager_var.set(None)
        self._instance_var.set(None)

    def get(self):
        return self._instance_var.get()


class Container:
    def __init__(self):
        self._definitions: List[_Definition] = []

    def _get_definition(self, cls, name=None) -> _Definition:
        for definition in self._definitions:
            if issubclass(definition.signature.return_annotation, cls) and definition.name == name:
                return definition

    def define(self, scope: Literal['context', 'singleton']) -> Callable[[Callable[P, T]], Callable[P, T]]:
        assert scope in ['context', 'singleton']

        def definer(function: Callable[P, T]) -> Callable[P, T]:
            signature = get_signature(function, eval_str=True)
            factory = contextmanager(function)

            if scope == 'context':
                self._definitions.append(_ContextDefinition(
                    signature=signature,
                    factory=factory,
                    scope=scope,
                    name=None,
                ))

            elif scope == 'singleton':
                self._definitions.append(_InstanceDefinition(
                    signature=signature,
                    factory=factory,
                    scope=scope,
                    name=None,
                ))

            return function

        return definer

    def exit(self, scope):
        for definition in self._definitions:
            if definition.scope == scope:
                definition.exit()

    def get(self, cls: Type[T], name=None) -> T:
        definition = self._get_definition(cls, name)

        if not definition:
            raise LookupError()

        if not definition.get():
            definition.enter()

        return cast(T, definition.get())

    def root(self, function: Callable[P, T]) -> Callable[P, T]:
        ''' Run `function` in new context, and close all closable definitions after call end '''

        def rootify(*args: Any, **kwargs: Any) -> T:
            try:
                return function(*args, **kwargs)
            except Exception:
                raise
            finally:
                self.exit('context')

        return partial(copy_context().run, rootify)

    def injectable(self, function: Callable[P, T]) -> Callable[P, T]:
        return update_wrapper(Injector(self, function), function)


class Injector:
    def __init__(self, di: Container, function: Callable[P, T]):
        self._di = di
        self._function = function
        self._requires = []
        self._signature = get_signature(function, eval_str=True)

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
                kwargs[parameter.name] = self._di.get(parameter.annotation)

        return self._function(*args, **kwargs)

    def __get__(self, instance, cls) -> Callable[P, T]:
        return partial(self, instance if instance else cls)


@dataclass(frozen=True)
class Injection:
    name: str
    cls: Type[Any]


def injection(name: Optional[str] = None, cls=None) -> Any:
    return Injection(name, cls)
