"""Abstract extender class implementation.

This module implements detecors for signal groups
This is a separate from the SignalGroup in order to make
it easier to implement external control schemes

"""
# Copyright 2020 by Conveqs Oy and Kari Koskinen
# All Rights Reserved
#

from abc import ABC, abstractmethod
from typing import Any

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.point_detector import PointDetector

from .timer import Timer


class Extender(ABC):
    """Active green extender interface."""

    @abstractmethod
    def is_extending(self) -> bool:
        """Check if extender is extending."""
        ...

    @abstractmethod
    def tick(self) -> None:
        """Update extending status."""
        ...


class GapSeekingExtender(Extender):
    """Gap seeking based green extender."""

    def __init__(
        self,
        extender_id: str,
        timer: Timer,
        raw_options: dict[str, Any],
        detectors: list[AreaDetector | PointDetector],
    ) -> None:

        self._timer: Timer = timer
        self._id: str = extender_id
        self._is_extending: bool = False

        self._detector_id: str = str(raw_options.get("detector"))
        if not self._detector_id:
            raise ValueError(f"Extender {extender_id} Doesn't have detector configured")

        extender_detector: AreaDetector | PointDetector | None = None
        for detector in detectors:
            if detector.id == self._detector_id:
                extender_detector = detector
                break
        if not extender_detector:
            raise ValueError(f"Cant' find detector with id {self._detector_id}")
        if not isinstance(extender_detector, PointDetector):
            raise ValueError("Cap seeking extender can use Point detector only")
        self._detector: PointDetector = extender_detector

        self._last_occupied_time: float | None = None
        self._last_detector_state_on: bool = self._detector.is_occupied
        if self._last_detector_state_on:
            self._last_occupied_time = self._timer.seconds

        gap = raw_options.get("gap")
        if gap is None:
            raise ValueError(f"Gap is not defined for {extender_id}")
        self._gap: float = float(gap)
        if self._gap < 0:
            raise ValueError(
                f"Gap for the extender {extender_id} cant be less than zero "
                f"(got {self._gap})",
            )

        def is_extending(self) -> bool:
            return self._is_extending

        def tick(self) -> None:

            self._last_detector_state_on = self._detector.is_occupied
            if self._last_detector_state_on:
                self._last_occupied_time = self._timer.seconds
            if self._last_occupied_time is None:
                return
            time_since_occupied = self._timer.seconds - self._last_occupied_time
            if time_since_occupied > self._gap:
                self._is_extending = False
            else:
                self._is_extending = True
