from abc import ABC, abstractmethod

from services.control_engine.src.detector import Detector


class SignalController(ABC):
    """
    SignalController is an abstract class that defines an interface
    that controller needs to implement to be used as a controller.
    """

    @abstractmethod
    def tick(self) -> str: ...

    @property
    @abstractmethod
    def status(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def sumo_name(self) -> str: ...

    @property
    @abstractmethod
    def e1_detectors(self) -> list[Detector]: ...

    @property
    @abstractmethod
    def e3_detectors(self) -> list[Detector]: ...
