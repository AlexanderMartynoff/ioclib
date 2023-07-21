import pytest
from contextvars import Context
from ioclib.injector import Injector, Requirement, inject
from typing import Iterator
from concurrent.futures import ThreadPoolExecutor


class ClosableService:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class UndefinedService:
    pass


class BreezeService:
    def __init__(self, breeze) -> None:
        self.breeze = breeze


class TemperatureService:
    def __init__(self, temperature) -> None:
        self.temperature = temperature


class WeatherService:
    def __init__(self, temperature_service: TemperatureService, breeze_service: BreezeService) -> None:
        self.temperature_service = temperature_service
        self.breeze_service = breeze_service


def test_singleton_inject() -> None:
    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.injectable
    def main(temperature_service: TemperatureService = inject()) -> None:
        assert isinstance(temperature_service, TemperatureService)

    main()


def test_singleton_multuple_inject() -> None:
    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.define('singleton')
    def breeze_service_def() -> Iterator[BreezeService]:
        yield BreezeService(0)

    @injector.injectable
    def main(temperature_service: TemperatureService = inject(),
             breeze_service: BreezeService = inject()) -> None:

        assert isinstance(temperature_service, TemperatureService)
        assert isinstance(breeze_service, BreezeService)

    main()


def test_singleton_recursion_inject() -> None:
    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.define('singleton')
    def breeze_service_def() -> Iterator[BreezeService]:
        yield BreezeService(0)

    @injector.define('singleton')
    @injector.injectable
    def weather_service_def(temperature_service: TemperatureService = inject(),
                            breeze_service: BreezeService = inject()) -> Iterator[WeatherService]:
        yield WeatherService(temperature_service, breeze_service)

    @injector.injectable
    def main(weather_service: WeatherService = inject()) -> None:
        assert isinstance(weather_service, WeatherService)

        assert isinstance(weather_service.breeze_service, BreezeService)
        assert isinstance(weather_service.temperature_service, TemperatureService)

    main()


def test_lookup_error_inject() -> None:
    injector = Injector()

    @injector.injectable
    def main(undefined_service: UndefinedService = inject()) -> None:
        pass

    with pytest.raises(LookupError):
        main()


def test_without_injectable_inject() -> None:
    def main(undefined_service: UndefinedService = inject()) -> None:
        assert isinstance(undefined_service, Requirement)

    main()


def test_context_inject() -> None:
    injector = Injector()

    @injector.define('context')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.injectable
    def main(temperature_service: TemperatureService = inject()) -> None:
        assert isinstance(temperature_service, TemperatureService)

    main()


def test_context_multiple_inject() -> None:
    injector = Injector()

    @injector.define('context')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.define('context')
    def breeze_service_def() -> Iterator[BreezeService]:
        yield BreezeService(0)

    @injector.injectable
    def main(temperature_service: TemperatureService = inject(),
             breeze_service: BreezeService = inject()) -> None:

        assert isinstance(temperature_service, TemperatureService)
        assert isinstance(breeze_service, BreezeService)

    main()


def test_context_recursion_inject() -> None:
    injector = Injector()

    @injector.define('context')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.define('context')
    def breeze_service_def() -> Iterator[BreezeService]:
        yield BreezeService(0)

    @injector.define('context')
    @injector.injectable
    def weather_service_def(temperature_service: TemperatureService = inject(),
                            breeze_service: BreezeService = inject()) -> Iterator[WeatherService]:
        yield WeatherService(temperature_service, breeze_service)

    @injector.injectable
    def main(weather_service: WeatherService = inject()) -> None:
        assert isinstance(weather_service, WeatherService)

        assert isinstance(weather_service.breeze_service, BreezeService)
        assert isinstance(weather_service.temperature_service, TemperatureService)

    main()


def test_context_with_multiple_context_inject() -> None:
    injector = Injector()

    @injector.define('context')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.injectable
    def get_temperature_service(temperature_service: TemperatureService = inject()) -> TemperatureService:
        return temperature_service

    assert Context().run(get_temperature_service) is not Context().run(get_temperature_service)

    context = Context()
    assert context.run(get_temperature_service) is context.run(get_temperature_service)


def test_context_injector_enter_inject() -> None:
    injector = Injector()

    relove_count = 0
    release_count = 0

    @injector.define('context')
    def closable_service_def() -> Iterator[ClosableService]:
        nonlocal relove_count, release_count

        relove_count += 1
        service = ClosableService()

        yield service

        release_count += 1
        service.close()

    @injector.injectable
    def get_closable_service(closable_service: ClosableService = inject()) -> ClosableService:
        return closable_service

    def main() -> None:
        with injector.entry([closable_service_def]):
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


def test_injector_error_handle_inject() -> None:
    injector = Injector()

    @injector.define('context')
    def closable_service_def() -> Iterator[ClosableService]:
        service = ClosableService()

        try:
            yield service
        finally:
            service.close()

    @injector.injectable
    def get_closable_service(closable_service: ClosableService = inject()) -> ClosableService:
        return closable_service

    def main() -> None:
        closable_service = None

        try:
            with injector.entry([closable_service_def]):
                closable_service = get_closable_service()
        except Exception:
            pass

        assert closable_service and closable_service.closed

    main()


def test_multitrheading() -> None:
    pool = ThreadPoolExecutor(1000)

    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.injectable
    def main(temperature_service: TemperatureService = inject()) -> TemperatureService:
        return temperature_service

    futures = [pool.submit(main) for _ in range(1000)]
    results = [future.result() for future in futures]

    assert len(set(results)) == 1


def test_injectable_class() -> None:
    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    class Class:
        @injector.injectable
        def method(self, temperature_service: TemperatureService = inject()) -> TemperatureService:
            return temperature_service

        @classmethod
        @injector.injectable
        def classmethod(cls, temperature_service: TemperatureService = inject()) -> TemperatureService:
            return temperature_service

        @staticmethod
        @injector.injectable
        def staticmethod(value: int, temperature_service: TemperatureService = inject()) -> int:
            return temperature_service.temperature or value

    cls = Class()

    assert cls.method().temperature == 0
    assert cls.classmethod().temperature == 0
    assert cls.staticmethod(1) == 1
