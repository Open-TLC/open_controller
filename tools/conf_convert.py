import argparse
import json
import os
from typing import Any

import yaml
from jsmin import jsmin

from services.control_engine.src.confread import GlobalConf


def main() -> None:
    """Convert Open Controller configuration files from JSON to YAML."""
    in_fname, out_fname = _parse_args()

    old_conf = GlobalConf(in_fname)
    base_dir = os.path.dirname(os.path.abspath(in_fname))

    timer_conf: dict[str, Any] = _parse_timer_params(old_conf.cnf["timer"])

    nats_raw = old_conf.cnf.get(
        "nats",
        {"server": "localhost", "port": 4222, "mode": "change"},
    )
    nats_conf: dict[str, Any] = _parse_nats_params(nats_raw)

    clockwork_conf: dict[str, Any] = {
        "publisher": {"mode": nats_conf.pop("mode")},
        **_parse_clockwork_params(old_conf.cnf, base_dir),
    }

    new_conf: dict[str, Any] = {
        "timer": timer_conf,
        "nats": nats_conf,
        "clockwork": clockwork_conf,
    }

    _write_output(new_conf, out_fname)


def _write_output(conf: dict[str, Any], filename: str) -> None:
    with open(filename, "w") as f:
        yaml.dump(conf, f, sort_keys=False, width=100)


def _parse_args() -> tuple[str, str]:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-i",
        "--input",
        "--in",
        help="Input file (old JSON configuration)",
        required=True,
    )

    parser.add_argument(
        "-o",
        "--output",
        "--out",
        help="Output file (generated YAML configuration)",
        required=True,
    )

    args = parser.parse_args()

    in_file = args.input
    out_file = args.output

    return (in_file, out_file)


def _parse_timer_params(timer_params: dict[str, Any]) -> dict[str, Any]:
    mode: str = str(timer_params.get("timer_mode"))
    if not mode:
        raise ValueError("Input configuration doesn't include timer mode")
    if mode not in ["fixed", "real"]:
        raise ValueError(
            "Input configuration contains invalid timer mode. Want "
            f"'fixed' or 'real', Got {mode}",
        )
    step: float = float(timer_params.get("time_step", 0))
    if not step:
        raise ValueError("Input configuration doesn't include timer time step")
    if step < 0:
        raise ValueError("Timer time step must be greater than 0")
    multiplier: float = float(timer_params.get("real_time_multiplier", 0))
    if not multiplier:
        raise ValueError("Input configuration doesn't include real time multiplier")
    if multiplier < 0:
        raise ValueError("Real time multiplier must be greater than 0")

    return {
        "mode": mode,
        "time_step": step,
        "real_time_multiplier": multiplier,
    }


def _parse_nats_params(nats_params: dict[str, Any]) -> dict[str, Any]:
    url: str = str(nats_params.get("server", ""))
    if not url:
        raise ValueError("Input configuration doesn't include NATS server URL")

    try:
        port: int = int(nats_params.get("port", 0))
    except (ValueError, TypeError) as exc:
        raise ValueError("NATS port must be a valid integer") from exc

    if not port:
        raise ValueError("Input configuration doesn't include NATS port")
    max_port = 65535
    if not (1 <= port <= max_port):
        raise ValueError(
            f"NATS port must be between 1 and 65535, Got {port}",
        )

    # This will be moved from NATS settings to Clockwork -> publisher
    mode: str = str(nats_params.get("mode", ""))
    if not mode:
        raise ValueError("Input configuration doesn't include NATS mode")

    return {
        "url": url,
        "port": port,
        "mode": mode,
    }


def _parse_clockwork_params(
    input_config: dict[str, Any],
    base_dir: str = ".",
) -> dict[str, Any]:
    """Parse all controllers from either a single or multi-controller configuration."""
    raw_controllers = _extract_raw_controllers(input_config, base_dir)

    if len(raw_controllers) == 1 and "group_outputs" not in raw_controllers[0][1]:
        sumo_options = input_config.get("sumo")
        if sumo_options:
            group_outputs = sumo_options.get("group_outputs")
            raw_controllers[0][1]["group_outputs"] = group_outputs

    controllers_list = []
    detectors_list = []
    for ctrl_id, ctrl_data in raw_controllers:
        detectors = _extract_detectors(ctrl_data)
        parsed_ctrl = _parse_single_controller(ctrl_id, ctrl_data)
        controllers_list.append(parsed_ctrl)
        detectors_list.extend(detectors)

    # Detectors by ID.
    cleaned_detectors: dict[str, dict[str, Any]] = {}

    # Remove possible duplicate entries.
    for det in detectors_list:
        if det["id"] in cleaned_detectors:
            continue

        cleaned_detectors[det["id"]] = det

    return {
        "controllers": controllers_list,
        "detectors": list(cleaned_detectors.values()),
    }


def _extract_raw_controllers(
    cnf: dict[str, Any],
    base_dir: str,
) -> list[tuple[str | None, dict[str, Any]]]:
    """Extract controller configurations from base configuration or external files."""
    raw_list: list[tuple[str | None, dict[str, Any]]] = []

    # Controller configuration can include single or multiple controllers.

    # Multiple controllers.
    if "controllers" in cnf and isinstance(cnf["controllers"], dict):
        ctrl_keys = cnf.get("controller_list", list(cnf["controllers"].keys()))
        for key in ctrl_keys:
            if key in cnf["controllers"]:
                raw_list.append((key, cnf["controllers"][key]))
            elif isinstance(key, dict) and "name" in key:
                raw_list.append((key["name"], key))
    # Single controller.
    elif "controller" in cnf:
        ctrl_val = cnf["controller"]
        if isinstance(ctrl_val, dict):
            known_keys = {
                "name",
                "signal_groups",
                "detectors",
                "print_status",
                "group_list",
                "phases",
                "intergreens",
                "controller_file",
            }
            if any(k in known_keys for k in ctrl_val):
                raw_list.append((ctrl_val.get("name"), ctrl_val))
            else:
                for k, v in ctrl_val.items():
                    if isinstance(v, dict):
                        raw_list.append((k, v))
    else:
        # Fallback if a single controller dict is passed directly.
        raw_list.append((cnf.get("name"), cnf))

    # Handle extra controller configuration files.
    resolved_list: list[tuple[str | None, dict[str, Any]]] = []
    for default_id, data in raw_list:
        if isinstance(data, dict) and "controller_file" in data:
            file_path = data["controller_file"]
            target_path = os.path.join(base_dir, file_path)
            if not os.path.exists(target_path):
                target_path = file_path

            with open(target_path, encoding="utf-8") as f:
                file_data = json.loads(jsmin(f.read()))

            if (
                default_id
                and default_id in file_data
                and isinstance(file_data[default_id], dict)
            ):
                actual_data = file_data[default_id]
                actual_id = default_id
            elif len(file_data) == 1 and isinstance(
                next(iter(file_data.values())),
                dict,
            ):
                inferred_id, actual_data = next(iter(file_data.items()))
                actual_id = default_id or inferred_id
            else:
                actual_data = file_data
                actual_id = default_id or actual_data.get("name")

            resolved_list.append((actual_id, actual_data))
        else:
            cid = default_id or (data.get("name") if isinstance(data, dict) else None)
            resolved_list.append((cid, data))

    return resolved_list


def _extract_detectors(controller_conf: dict[str, Any]) -> list[dict[str, Any]]:
    detectors_conf = dict(controller_conf.get("detectors", {}))

    result_configurations: list[dict[str, Any]] = []
    for det_conf in detectors_conf.values():
        det_id = det_conf.get("sumo_id", "")
        raw_det_type = det_conf.get("type", "")

        if not raw_det_type:
            raise ValueError(f"No type found for detector {det_id}")

        if raw_det_type == "request":
            det_type = "e1_detector"
        elif raw_det_type == "e3detector":
            det_type = "e3_detector"
        else:
            raise ValueError(
                f"Unknown detector type {raw_det_type} for detector {det_id}",
            )

        result_conf = {
            "id": det_id,
            "type": det_type,
            "options": {},
        }

        result_configurations.append(result_conf)

    return result_configurations


def _parse_single_controller(
    ctrl_id: str | None,
    controller: dict[str, Any],
) -> dict[str, Any]:
    """Parse a single controller configuration dictionary."""
    controller_id: str = ctrl_id or str(controller.get("name", ""))
    if not controller_id:
        raise ValueError("Input configuration doesn't include controller name")

    # Merge 'default' signal group values into each group and omit 'default' key.
    raw_signal_groups: dict[str, Any] = controller.get("signal_groups", {})
    default_sg: dict[str, Any] = raw_signal_groups.get("default", {})

    signal_groups: dict[str, Any] = {}
    for sg_name, sg_data in raw_signal_groups.items():
        if sg_name == "default":
            continue
        merged_sg = {**default_sg, **sg_data}
        signal_groups[sg_name] = merged_sg

    for group_options in signal_groups.values():
        if group_options["request_type"] == "detector":
            group_options["constant_request"] = False
        elif group_options["request_type"] == "fixed":
            group_options["constant_request"] = True
        else:
            raise ValueError(f"Unknown request_type {group_options['request_type']}")

        if group_options["green_end"] == "remain":
            group_options["remain_green"] = True
        elif group_options["green_end"] == "after_ext":
            group_options["remain_green"] = False
        else:
            raise ValueError(f"Unknown green_end {group_options['green_end']}")

        for key in (
            "channel",
            "phase_request",
            "request_type",
            "max_amber",
            "max_amber_red",
            "max_red",
            "green_end",
        ):
            group_options.pop(key, None)

    extenders = _parse_extenders(controller)
    requesters = _parse_requesters(controller)

    phases = [_FlowList(row) for row in controller.get("phases", [])]
    intergreens = [_FlowList(row) for row in controller.get("intergreens", [])]

    options: dict[str, Any] = {
        "print_status": controller.get("print_status", False),
        "sumo_outputs": controller.get("group_outputs", []),
        "signal_groups": signal_groups,
        "extenders": extenders,
        "requesters": requesters,
        "group_list": controller.get("group_list", []),
        "phases": phases,
        "intergreens": intergreens,
    }

    return {
        "id": controller_id,
        "type": controller.get("type", "phasering"),
        "options": options,
    }


MODE_MAP = {
    1: "simple",
    2: "pressure",
    3: "pressure_and_time",
    4: "momentum_and_time",
}


def _parse_extenders(config: dict[str, Any]) -> list[dict[str, Any]]:
    detectors = config.get("detectors", {})
    extenders = config.get("extenders", {})

    # Map group IDs to associated detector IDs (e.g. e3detectors)
    group_to_detectors: dict[str, list[str]] = {}
    for det_id, det_info in detectors.items():
        group = det_info.get("group")
        if group:
            group_to_detectors.setdefault(group, []).append(det_id)

    output = []
    for ext_id, ext_info in extenders.items():
        group = ext_info.get("group")
        ext_mode = ext_info.get("ext_mode")

        options = {
            "mode": MODE_MAP.get(ext_mode, str(ext_mode)),
            "threshold": ext_info.get("ext_threshold"),
            "time_discount": ext_info.get("time_discount"),
            "detectors": group_to_detectors.get(group, []),
        }

        output.append(
            {
                "id": ext_id,
                "type": "smart",
                "group": group,
                "options": options,
            },
        )

    return output


def _parse_requesters(config: dict[str, Any]) -> list[dict[str, Any]]:
    detectors = config.get("detectors", {})
    output = []

    for det_id, det_info in detectors.items():
        if det_info.get("type") == "request":
            request_groups = det_info.get("request_groups", [])

            # Primary group is the first element; remaining elements go to side_groups
            main_group = request_groups[0] if request_groups else ""
            side_groups = request_groups[1:]

            sumo_id = det_info.get("sumo_id")
            detector_list = [sumo_id] if sumo_id else []

            output.append(
                {
                    "id": det_id,
                    "type": "trigger",
                    "group": main_group,
                    "side_groups": side_groups,
                    "options": {
                        "detectors": detector_list,
                    },
                },
            )

    return output


class _FlowList(list):
    """Custom list type to enforce flow-style (JSON-like) YAML output."""

    pass


def _flow_list_representer(dumper: yaml.Dumper, data: _FlowList) -> yaml.SequenceNode:
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


yaml.add_representer(_FlowList, _flow_list_representer)

if __name__ == "__main__":
    main()
