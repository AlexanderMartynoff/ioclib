import pytest
from contextvars import Context
from dipy import Container, Injection, injection


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
    cr = Container()

    @cr.define('singleton')
    def def_temperature_service() -> TemperatureService:
        yield TemperatureService(0)


    @cr.injectable
    def main(temperature_service: TemperatureService = injection()):
        assert isinstance(temperature_service, TemperatureService)

    main()


def test_singleton_multuple_injection():
    cr = Container()

    @cr.define('singleton')
    def temperature_service() -> TemperatureService:
        yield TemperatureService(0)

    @cr.define('singleton')
    def breeze_service() -> BreezeService:
        yield BreezeService(0)


    @cr.injectable
    def main(temperature_service: TemperatureService = injection(),
             breeze_service: BreezeService = injection()):

        assert isinstance(temperature_service, TemperatureService)
        assert isinstance(breeze_service, BreezeService)

    main()


def test_singleton_recursion_injection():
    cr = Container()

    @cr.define('singleton')
    def temperature_service() -> TemperatureService:
        yield TemperatureService(0)

    @cr.define('singleton')
    def breeze_service() -> BreezeService:
        yield BreezeService(0)

    @cr.define('singleton')
    @cr.injectable
    def weather_service(temperature_service: TemperatureService = injection(),
                        breeze_service: BreezeService = injection()) -> WeatherService:
        yield WeatherService(temperature_service, breeze_service)


    @cr.injectable
    def main(weather_service: WeatherService = injection()):
        assert isinstance(weather_service, WeatherService)

        assert isinstance(weather_service.breeze_service, BreezeService)
        assert isinstance(weather_service.temperature_service, TemperatureService)

    main()


def test_lookup_error_injection():
    cr = Container()

    @cr.injectable
    def main(undefined_service: UndefinedService = injection()):
        pass

    with pytest.raises(LookupError):
        main()


def test_without_injectable_injection():
    def main(undefined_service: UndefinedService = injection()):
        assert isinstance(undefined_service, Injection)

    main()


def test_context_injection():
    cr = Container()

    @cr.define('context')
    def temperature_service() -> TemperatureService:
        yield TemperatureService(0)

    @cr.injectable
    def main(temperature_service: TemperatureService = injection()):
        assert isinstance(temperature_service, TemperatureService)

    main()


def test_context_multiple_injection():
    cr = Container()

    @cr.define('context')
    def temperature_service() -> TemperatureService:
        yield TemperatureService(0)

    @cr.define('context')
    def breeze_service() -> BreezeService:
        yield BreezeService(0)


    @cr.injectable
    def main(temperature_service: TemperatureService = injection(),
             breeze_service: BreezeService = injection()):

        assert isinstance(temperature_service, TemperatureService)
        assert isinstance(breeze_service, BreezeService)

    main()


def test_context_recursion_injection():
    cr = Container()

    @cr.define('context')
    def temperature_service() -> TemperatureService:
        yield TemperatureService(0)

    @cr.define('context')
    def breeze_service() -> BreezeService:
        yield BreezeService(0)

    @cr.define('context')
    @cr.injectable
    def weather_service(temperature_service: TemperatureService = injection(),
                        breeze_service: BreezeService = injection()) -> WeatherService:
        yield WeatherService(temperature_service, breeze_service)


    @cr.injectable
    def main(weather_service: WeatherService = injection()):
        assert isinstance(weather_service, WeatherService)

        assert isinstance(weather_service.breeze_service, BreezeService)
        assert isinstance(weather_service.temperature_service, TemperatureService)

    main()


def test_context_with_multiple_context_injection():
    cr = Container()

    @cr.define('context')
    def temperature_service() -> TemperatureService:
        yield TemperatureService(0)

    @cr.injectable
    def get_temperature_service(temperature_service: TemperatureService = injection()):
        return temperature_service

    assert Context().run(get_temperature_service) is not Context().run(get_temperature_service)

    context = Context()
    assert context.run(get_temperature_service) is context.run(get_temperature_service)


def test_context_container_enter_injection():
    cr = Container()

    relove_count = 0
    release_count = 0

    @cr.define('context')
    def closable_service() -> ClosableService:
        nonlocal relove_count, release_count

        relove_count += 1
        service = ClosableService()

        yield service

        release_count += 1
        service.close()

    @cr.injectable
    def get_closable_service(closable_service: ClosableService = injection()) -> ClosableService:
        return closable_service

    def main():
        with cr.enter(['context']):
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
