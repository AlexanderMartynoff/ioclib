import pytest
from ioclib.injector import Injector, Requirement, requirement
from typing import Iterator
from concurrent.futures import ThreadPoolExecutor


class ClosableService:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class UndefinedService:
    pass


class TimeService:
    def __init__(self, time: float) -> None:
        self.time = time


class TemperatureService:
    def __init__(self, temperature: float) -> None:
        self.temperature = temperature


class WeatherService:
    def __init__(self, temperature_service: TemperatureService, time_service: TimeService) -> None:
        self.temperature_service = temperature_service
        self.time_service = time_service


def test_singleton_inject() -> None:
    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.executor
    def main(temperature_service: TemperatureService = requirement()) -> None:
        assert isinstance(temperature_service, TemperatureService)

    with injector:
        main()


def test_singleton_multuple_inject() -> None:
    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.define('singleton')
    def time_service_def() -> Iterator[TimeService]:
        yield TimeService(0)

    @injector.executor
    def main(temperature_service: TemperatureService = requirement(),
             time_service: TimeService = requirement()) -> None:

        assert isinstance(temperature_service, TemperatureService)
        assert isinstance(time_service, TimeService)

    with injector:
        main()


def test_singleton_recursion_inject() -> None:
    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.define('singleton')
    def time_service_def() -> Iterator[TimeService]:
        yield TimeService(0)

    @injector.define('singleton')
    @injector.executor
    def weather_service_def(temperature_service: TemperatureService = requirement(),
                            time_service: TimeService = requirement()) -> Iterator[WeatherService]:
        yield WeatherService(temperature_service, time_service)

    @injector.executor
    def main(weather_service: WeatherService = requirement()) -> None:
        assert isinstance(weather_service, WeatherService)

        assert isinstance(weather_service.time_service, TimeService)
        assert isinstance(weather_service.temperature_service, TemperatureService)

    with injector:
        main()


def test_lookup_error_inject() -> None:
    injector = Injector()

    @injector.executor
    def main(undefined_service: UndefinedService = requirement()) -> None:
        pass

    with pytest.raises(LookupError):
        main()


def test_error_execution() -> None:
    class TestError(Exception):
        pass

    injector = Injector()

    @injector.define('singleton')
    def time_service_def() -> Iterator[TimeService]:
        yield TimeService(0)

    @injector.executor
    def main(time_service: TimeService = requirement()) -> None:
        raise TestError

    with pytest.raises(TestError), injector:
        main()


def test_without_injectable_inject() -> None:
    def main(undefined_service: UndefinedService = requirement()) -> None:
        assert isinstance(undefined_service, Requirement)

    main()


def test_multitrheading() -> None:
    pool = ThreadPoolExecutor(1000)

    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.executor
    def main(temperature_service: TemperatureService = requirement()) -> TemperatureService:
        return temperature_service

    with injector:
        futures = [pool.submit(main) for _ in range(1000)]
        results = [future.result() for future in futures]

    assert len(set(results)) == 1


def test_injectable_class() -> None:
    injector = Injector()

    @injector.define('singleton')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    class Class:
        @injector.executor
        def method(self, temperature_service: TemperatureService = requirement()) -> TemperatureService:
            return temperature_service

        @classmethod
        @injector.executor
        def classmethod(cls, temperature_service: TemperatureService = requirement()) -> TemperatureService:
            return temperature_service

        @staticmethod
        @injector.executor
        def staticmethod(value: float, temperature_service: TemperatureService = requirement()) -> float:
            return temperature_service.temperature or value

    cls = Class()

    with injector:
        assert cls.method().temperature == 0
        assert cls.classmethod().temperature == 0
        assert cls.staticmethod(1) == 1


def test_transient() -> None:
    injector = Injector()

    @injector.define('transient')
    def temperature_service_def() -> Iterator[TemperatureService]:
        yield TemperatureService(0)

    @injector.executor
    def main(temperature_service_1: TemperatureService = requirement(), temperature_service_2: TemperatureService = requirement()) -> None:
        assert temperature_service_1.temperature == 0
        assert temperature_service_2.temperature == 0
        assert temperature_service_1 is not temperature_service_2

    main()


def test_transient_count() -> None:
    injector = Injector()

    enter_count, exit_count = 0, 0

    @injector.define('transient')
    def temperature_service_def() -> Iterator[TemperatureService]:
        nonlocal enter_count, exit_count

        enter_count += 1
        yield TemperatureService(0)
        exit_count += 1

    @injector.executor
    def main(temperature_service_1: TemperatureService = requirement()) -> None:
        assert isinstance(temperature_service_1, TemperatureService)

    times = 10

    for _ in range(times):
        main()

    assert enter_count == times
    assert exit_count == times
