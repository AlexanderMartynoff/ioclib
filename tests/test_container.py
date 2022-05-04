import pytest
from contextvars import copy_context, Context
from dipy import Container, injection


class ServiceLookupError:
    pass


class ServiceB:
    pass


class ServiceC:
    pass


class ServiceA:
    def __init__(self, b_service: ServiceB):
        self.service_b = b_service


di = Container()


@di.define('singleton')
def c_service() -> ServiceC:
    return ServiceC()


@di.define('context')
def b_service() -> ServiceB:
    return ServiceB()


@di.define('context')
@di.injectable
def a_service(b_service: ServiceB = injection()) -> ServiceA:
    return ServiceA(b_service)


def test_injection():
    @di.injectable
    def get_service_a(service_a: ServiceA = injection()):
        return service_a

    service_a = get_service_a()

    assert isinstance(service_a, ServiceA)
    assert isinstance(service_a.service_b, ServiceB)


def test_injections():
    @di.injectable
    def get_service_a_and_b(service_a: ServiceA = injection(), service_b: ServiceB = injection()):
        return service_a, service_b

    service_a, service_b = get_service_a_and_b()

    assert isinstance(service_a, ServiceA)
    assert isinstance(service_b, ServiceB)


def test_lookup_error_injection():
    @di.injectable
    def get_service_lookup_error(service_lookup_error: ServiceLookupError = injection()):
        return service_lookup_error

    with pytest.raises(LookupError):
        get_service_lookup_error()


def test_context_injection():
    @di.injectable
    def main(service_a: ServiceA = injection()):
        return service_a

    context_1 = Context()
    context_2 = Context()

    service_a_1 = context_1.run(main)
    service_a_2 = context_2.run(main)

    assert isinstance(service_a_1, ServiceA)
    assert isinstance(service_a_2, ServiceA)

    assert service_a_1 is not service_a_2
    assert service_a_1.service_b is not service_a_2.service_b

    context_3 = Context()

    service_a_1 = context_3.run(main)
    service_a_2 = context_3.run(main)

    assert service_a_1 is service_a_2
    assert service_a_1.service_b is service_a_2.service_b


def test_context_singleton_injection():
    @di.injectable
    def main(service_c: ServiceC = injection()):
        return service_c

    context_1 = Context()
    context_2 = Context()

    service_c_1 = context_1.run(main)
    service_c_2 = context_2.run(main)

    assert isinstance(service_c_1, ServiceC)
    assert isinstance(service_c_1, ServiceC)

    assert service_c_1 is service_c_2
