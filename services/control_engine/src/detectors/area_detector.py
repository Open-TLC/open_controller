from abc import ABC, abstractmethod


class AreaDetector(ABC):
    @abstractmethod
    def vehicle_count(self) -> float: ...

    @abstractmethod
    def average_speed(self) -> float: ...

    @abstractmethod
    def average_time_loss(self) -> float: ...
