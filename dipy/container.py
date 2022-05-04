from typing import Any, Optional, Callable, Type, TypeVar, Tuple, List, Union, cast
from typing_extensions import ParamSpec, Literal
from functools import partial, update_wrapper
from inspect import Parameter, signature as get_signature, Signature
from contextvars import copy_context, ContextVar
from dataclasses import dataclass, field


P = ParamSpec('P')
T = TypeVar('T')


def root(function: Callable[P, T]) -> Callable[P, T]:
    ''' Always run `function` in new context '''

    def root_function(*args: Any, **kwargs: Any) -> T:
        return copy_context().run(function, *args, **kwargs)

    return root_function


@dataclass
class _Definition:
    signature: Signature
    factory: Callable[..., Any]
    scope: str
    name: str

    def define(self):
        self.set(self.factory())

    def set(self, value):
        raise NotImplementedError()

    def get(self):
        raise NotImplementedError()


@dataclass
class _InstanceDefinition(_Definition):
    _instance: Any = None

    def set(self, value):
        self._instance = value

    def get(self):
        return self._instance


@dataclass
class _ContextDefinition(_Definition):
    _var: ContextVar = field(init=False)

    def __post_init__(self):
        self._var = ContextVar(
            f'{self.signature.return_annotation.__name__}_{self.factory.__name__}',
            default=None)

    def set(self, value):
        self._var.set(value)

    def get(self):
        return self._var.get()


class Container:
    def __init__(self):
        self._definitions: List[_Definition] = []

    def _get_definition(self, cls, name=None) -> _Definition:
        for definition in self._definitions:
            if issubclass(definition.signature.return_annotation, cls) and definition.name == name:
                return definition

    def define(self, scope: Literal['context', 'singleton']) -> Callable[[Callable[P, T]], Callable[P, T]]:
        def definer(function: Callable[P, T]) -> Callable[P, T]:

            if scope == 'context':
                self._definitions.append(_ContextDefinition(
                    get_signature(function, eval_str=True),
                    function,
                    scope,
                    None,
                ))

            elif scope == 'singleton':
                self._definitions.append(_InstanceDefinition(
                    get_signature(function, eval_str=True),
                    function,
                    scope,
                    None,
                ))

            return function

        return definer

    def destroy(self):
        pass

    def get(self, cls: Type[T], name=None) -> T:
        definition = self._get_definition(cls, name)

        if not definition:
            raise LookupError()

        if not definition.get():
            definition.define()

        return cast(T, definition.get())

    @staticmethod
    def root(function: Callable[P, T]) -> Callable[P, T]:
        return root(function)

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
        return partial(self.__call__, instance if instance else cls)


class Injection:
    def __init__(self, name, cls):
        self._name = name
        self._cls = cls

    def __getattr__(self, name):
        raise AttributeError()


def injection(name: Optional[str] = None, cls=None) -> Any:
    return Injection(name, cls)
