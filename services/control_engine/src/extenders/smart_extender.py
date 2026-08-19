from collections.abc import Callable
from typing import Any

from services.control_engine.src.detectors.area_detector import AreaDetector
from services.control_engine.src.detectors.point_detector import PointDetector
from services.control_engine.src.timer import Timer

from .extender import Extender

VALID_MODES = ["simple", "pressure", "pressure_and_time", "momentum_and_time"]


class SmartExtender(Extender):
    """Queue length comparison based green extender."""

    def __init__(
        self,
        extender_id: str,
        timer: Timer,
        raw_options: dict[str, Any],
        conflict_detector_ids: list[str],
        detectors: list[AreaDetector | PointDetector],
        get_green_start_cb: Callable[[], float],
    ) -> None:
        self._id = extender_id
        self._timer = timer
        self._green_start_cb = get_green_start_cb

        self._mode = self._parse_mode(extender_id, raw_options)
        self._threshold = self._parse_non_negative_float(
            extender_id,
            raw_options,
            key="threshold",
        )
        self._time_discount = self._parse_non_negative_float(
            extender_id,
            raw_options,
            key="time_discount",
        )

        own_ids = self._parse_own_detector_ids(extender_id, raw_options)
        self._own_group_detectors = self._resolve_area_detectors(
            extender_id,
            own_ids,
            detectors,
        )
        self._conflict_group_detectors = self._resolve_area_detectors(
            extender_id,
            conflict_detector_ids,
            detectors,
        )

    @staticmethod
    def _parse_mode(extender_id: str, raw_options: dict[str, Any]) -> str:
        mode = raw_options.get("mode", "")
        if not mode:
            raise ValueError(f"No mode configured for extender {extender_id}")
        if mode not in VALID_MODES:
            raise ValueError(
                f"Unknown mode for extender {extender_id}: {mode}. "
                f"Valid modes are {VALID_MODES}",
            )
        return str(mode)

    @staticmethod
    def _parse_non_negative_float(
        extender_id: str,
        raw_options: dict[str, Any],
        key: str,
    ) -> float:
        val = raw_options.get(key)
        if val is None:
            raise ValueError(
                f"No {key.replace('_', ' ')} configured for extender {extender_id}",
            )

        float_val = float(val)
        if float_val < 0:
            raise ValueError(
                f"Invalid {key.replace('_', ' ')} for extender {extender_id}. "
                "Value can't be less than zero",
            )
        return float_val

    @staticmethod
    def _parse_own_detector_ids(
        extender_id: str,
        raw_options: dict[str, Any],
    ) -> list[str]:
        raw_own_detectors = raw_options.get("detectors")
        if not isinstance(raw_own_detectors, list) or len(raw_own_detectors) == 0:
            raise ValueError(
                f"No own group detectors configured for extender {extender_id}",
            )
        return [str(d_id) for d_id in raw_own_detectors]

    @staticmethod
    def _resolve_area_detectors(
        extender_id: str,
        target_ids: list[str],
        available_detectors: list[AreaDetector | PointDetector],
    ) -> list[AreaDetector]:
        resolved: list[AreaDetector] = []
        target_set = set(target_ids)

        for detector in available_detectors:
            if detector.id not in target_set:
                continue

            if not isinstance(detector, AreaDetector):
                raise ValueError(
                    f"Smart extender can only use area detectors. "
                    f"Extender {extender_id} was given detector {detector.id} which "
                    "isn't an area detector.",
                )
            resolved.append(detector)

        return resolved

    def tick(self) -> None:
        """Update extending status."""
        self._is_extending = self._calculate_extension()

    def _calculate_extension(self) -> bool:
        own_group_vehicle_count: int = 0
        own_group_momentum: float = 0

        for detector in self._own_group_detectors:
            if detector.vehicle_count == 0:
                continue

            own_group_vehicle_count += int(detector.vehicle_count)

            speed_threshold: float = 0.2
            own_group_momentum += (
                detector.vehicle_count
                if detector.average_speed >= speed_threshold
                else 0
            )

        # If extender group has no vehicles, extension is turned off.
        if own_group_vehicle_count == 0:
            return False

        conflicting_vehicles = 0
        for detector in self._conflict_group_detectors:
            conflicting_vehicles += int(detector.vehicle_count)

        # If conflicting groups have no vehicles, extension continues.
        if conflicting_vehicles == 0:
            return True

        if self._mode == "simple":
            return self._simple_extend(own_group_vehicle_count)

        if self._mode == "pressure":
            return self._pressure_extend(own_group_vehicle_count, conflicting_vehicles)

        if self._mode == "pressure_and_time":
            return self._pressure_time_extend(
                own_group_vehicle_count,
                conflicting_vehicles,
            )

        if self._mode == "momentum_and_time":
            return self._momentum_time_extend(own_group_momentum, conflicting_vehicles)

        # This should never be reached, as modes are sanitized in constructor.
        raise ValueError(f"Unknown mode for extender {self.id}: {self._mode}")

    def _simple_extend(self, own_vehicles: int) -> bool:
        return own_vehicles > self._threshold

    def _pressure_extend(self, own_vehicles: int, conflicting_vehicles: int) -> bool:
        traffic_ratio = own_vehicles / conflicting_vehicles
        return traffic_ratio > self._threshold

    def _pressure_time_extend(
        self,
        own_vehicles: int,
        conflicting_vehicles: int,
    ) -> bool:
        green_elapsed = self._timer.seconds - self._green_start_cb()
        time_discount = 1.0 + (green_elapsed / self._time_discount)
        traffic_ratio = own_vehicles / conflicting_vehicles
        threshold = self._threshold * time_discount
        return traffic_ratio > threshold

    def _momentum_time_extend(self, momentum: float, conflicting_vehicles: int) -> bool:
        green_elapsed = self._timer.seconds - self._green_start_cb()
        time_discount = 1.0 + (green_elapsed / self._time_discount)
        traffic_ratio = momentum / conflicting_vehicles
        threshold = self._threshold * time_discount
        return traffic_ratio > threshold
