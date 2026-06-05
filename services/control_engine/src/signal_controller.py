from abc import ABC, abstractmethod


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
