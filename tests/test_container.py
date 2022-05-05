import pytest
from contextvars import Context
from ioclib import Container, Injection, injection
from typing import Iterator

class ClosableService:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class UndefinedService:
    pass


class BreezeService:
    def __init__(self, breeze):
        self.breeze = breeze


class TemperatureService:
    def __init__(self, temperature):
        self.temperature = temperature


class WeatherService:
    def __init__(self, temperature_service: TemperatureService, breeze_service: BreezeService):
        self.temperature_service = temperature_service
        self.breeze_service = breeze_service


def test_singleton_injection():
    ioc = Container()

    @ioc.define('singleton')
    def def_temperature_service() -> Iterator[TemperatureService]:
        yield TemperatureService(0)


    @ioc.injectable
    def main(temperature_service: TemperatureService = injection()):
        assert isinstance(temperature_service, TemperatureService)

    main()


def test_singleton_multuple_injection():
    ioc = Container()

    @ioc.define('singleton')
    def temperature_service() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @ioc.define('singleton')
    def breeze_service() -> Iterator[BreezeService]:
        yield BreezeService(0)


    @ioc.injectable
    def main(temperature_service: TemperatureService = injection(),
             breeze_service: BreezeService = injection()):

        assert isinstance(temperature_service, TemperatureService)
        assert isinstance(breeze_service, BreezeService)

    main()


def test_singleton_recursion_injection():
    ioc = Container()

    @ioc.define('singleton')
    def temperature_service() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @ioc.define('singleton')
    def breeze_service() -> Iterator[BreezeService]:
        yield BreezeService(0)

    @ioc.define('singleton')
    @ioc.injectable
    def weather_service(temperature_service: TemperatureService = injection(),
                        breeze_service: BreezeService = injection()) -> Iterator[WeatherService]:
        yield WeatherService(temperature_service, breeze_service)


    @ioc.injectable
    def main(weather_service: WeatherService = injection()):
        assert isinstance(weather_service, WeatherService)

        assert isinstance(weather_service.breeze_service, BreezeService)
        assert isinstance(weather_service.temperature_service, TemperatureService)

    main()


def test_lookup_error_injection():
    ioc = Container()

    @ioc.injectable
    def main(undefined_service: UndefinedService = injection()):
        pass

    with pytest.raises(LookupError):
        main()


def test_without_injectable_injection():
    def main(undefined_service: UndefinedService = injection()):
        assert isinstance(undefined_service, Injection)

    main()


def test_context_injection():
    ioc = Container()

    @ioc.define('context')
    def temperature_service() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @ioc.injectable
    def main(temperature_service: TemperatureService = injection()):
        assert isinstance(temperature_service, TemperatureService)

    main()


def test_context_multiple_injection():
    ioc = Container()

    @ioc.define('context')
    def temperature_service() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @ioc.define('context')
    def breeze_service() -> Iterator[BreezeService]:
        yield BreezeService(0)


    @ioc.injectable
    def main(temperature_service: TemperatureService = injection(),
             breeze_service: BreezeService = injection()):

        assert isinstance(temperature_service, TemperatureService)
        assert isinstance(breeze_service, BreezeService)

    main()


def test_context_recursion_injection():
    ioc = Container()

    @ioc.define('context')
    def temperature_service() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @ioc.define('context')
    def breeze_service() -> Iterator[BreezeService]:
        yield BreezeService(0)

    @ioc.define('context')
    @ioc.injectable
    def weather_service(temperature_service: TemperatureService = injection(),
                        breeze_service: BreezeService = injection()) -> Iterator[WeatherService]:
        yield WeatherService(temperature_service, breeze_service)


    @ioc.injectable
    def main(weather_service: WeatherService = injection()):
        assert isinstance(weather_service, WeatherService)

        assert isinstance(weather_service.breeze_service, BreezeService)
        assert isinstance(weather_service.temperature_service, TemperatureService)

    main()


def test_context_with_multiple_context_injection():
    ioc = Container()

    @ioc.define('context')
    def temperature_service() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @ioc.injectable
    def get_temperature_service(temperature_service: TemperatureService = injection()):
        return temperature_service

    assert Context().run(get_temperature_service) is not Context().run(get_temperature_service)

    context = Context()
    assert context.run(get_temperature_service) is context.run(get_temperature_service)


def test_context_container_enter_injection():
    ioc = Container()

    relove_count = 0
    release_count = 0

    @ioc.define('context')
    def closable_service() -> Iterator[ClosableService]:
        nonlocal relove_count, release_count

        relove_count += 1
        service = ClosableService()

        yield service

        release_count += 1
        service.close()

    @ioc.injectable
    def get_closable_service(closable_service: ClosableService = injection()) -> ClosableService:
        return closable_service

    def main():
        with ioc.run(['context']):
            closable_service = get_closable_service()
            assert not closable_service.closed

            assert relove_count == 1
            assert release_count == 0

            closable_service = get_closable_service()
            assert not closable_service.closed

            assert relove_count == 1
            assert release_count == 0

        assert closable_service.closed

        assert relove_count == 1
        assert release_count == 1

    main()


def test_container_error_handle_injection():
    ioc = Container()

    @ioc.define('context')
    def closable_service() -> Iterator[ClosableService]:
        service = ClosableService()

        try:
            yield service
        finally:
            service.close()

    @ioc.injectable
    def get_closable_service(closable_service: ClosableService = injection()) -> ClosableService:
        return closable_service

    def main():
        try:
            with ioc.run():
                closable_service = get_closable_service()
                raise RuntimeError()
        except Exception:
            pass

        assert closable_service.closed

    main()
