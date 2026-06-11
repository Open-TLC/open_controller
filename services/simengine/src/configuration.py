import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import mock_open, patch

from jsmin import jsmin


class GeneralConfiguration:
    def __init__(self, filename: str) -> None:
        file_content: dict[str, Any] = self._read_file(filename)
        cleaned_conf = self._parse_conf(file_content)
        if not self._is_valid(cleaned_conf):
            raise Exception("Invalid configuration")

        self.timer: dict[str, Any] = cleaned_conf["timer"]
        self.sumo: dict[str, Any] = cleaned_conf["sumo"]
        self.active_controllers: list[str] = cleaned_conf["active_controllers"]
        self.controllers: dict[str, Any] = cleaned_conf["controllers"]

        # Save the cleaned and joined configuration to a new file.
        self._write_cleaned_conf_to_file(filename)

    def _is_valid(self, conf: dict[str, Any]) -> bool:
        """
        Checks that all necessary fields can be found in the configuration.

        Args:
            conf: Parsed configuration.

        Returns:
            Whether the configuration is valid or not.
        """
        NECESSARY_FIELDS: list[str] = [
            "timer",
            "sumo",
            "active_controllers",
            "controllers",
        ]

        for field in NECESSARY_FIELDS:
            if field not in conf:
                return False

        return True

    def _read_file(self, filename: str) -> dict[str, Any]:
        """
        Opens the json file and returns values as a dictionary.

        Args:
            filename: Name of the configuration file.

        Returns:
            Configuration file as a dictionary.
        """
        config: dict[str, Any] = {}
        try:
            with open(filename) as f:
                config = json.loads(jsmin(f.read()))
        except FileNotFoundError as e:
            raise Exception(f"Configuration file not found: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Couldn't parse configuration file: {e}")

        return config

    def _write_cleaned_conf_to_file(self, filename: str) -> None:
        original_file_path = Path(filename)

        cleaned_filename: str = (
            f"{original_file_path.stem}_cleaned{original_file_path.suffix}"
        )

        cleaned_conf = {
            "timer": self.timer,
            "sumo": self.sumo,
            "active_controllers": self.active_controllers,
            "controllers": self.controllers,
        }
        json_conf = json.dumps(cleaned_conf)

        # Create or overwrite the cleaned configuration file.
        with open(cleaned_filename, "w") as f:
            f.write(json_conf)

    def _parse_conf(self, conf: dict[str, Any]) -> dict[str, Any]:
        """
        Cleans up the configuration by removing unused options.
        Also reads additional configurations from files referenced in this file.
        For example if controller configurations are in separate files,
        they are read and the contents are added to the dictionary.

        Args:
            conf: Base configuration dictionary.

        Returns:
            Cleaned configuration dictionary with referenced file contents added.
        """
        # Convert single controller configuration to the
        # same format as multi controller configuration.
        if "controller" in conf:
            conf["controllers"] = {conf["controller"]["name"]: conf["controller"]}
            conf.pop("controller")

        result: dict[str, Any] = {}

        # We only care about timer, sumo, active_controllers and
        # controllers configurations. Everything else is ignored.
        for key in conf:
            if key == "timer":
                result[key] = self._parse_timer_conf(conf[key])

            if key == "sumo":
                result[key] = self._parse_sumo_conf(conf[key])

            if key == "active_controllers":
                # Active controllers don't need extra parsing.
                # They are added to the result as is.
                if type(conf[key]) is not list:
                    raise ValueError(
                        "active_controllers in configuration is not a list"
                    )
                result[key] = list(conf[key])

            if key == "controllers":
                result[key] = self._parse_controller_conf(conf[key])

        return result

    def _parse_timer_conf(self, conf: dict[str, Any]) -> dict[str, Any]:
        """
        Parses the timer configuration removing all unnecessary options.

        Args:
            conf: "timer" configuration from Open Controller configuration

        Returns:
            Cleaned version of timer configuration.
        """
        result: dict[str, Any] = {}
        for option in conf:
            if option == "timer_mode":
                result[option] = conf[option]

            if option == "time_step":
                result[option] = conf[option]

            if option == "real_time_multiplier":
                result[option] = conf[option]

            if option == "max_time":
                result[option] = conf[option]

            # This is only relevant if timer_mode is set to cycle.
            if option == "cycle_time":
                result[option] = conf[option]

        return result

    def _parse_sumo_conf(self, conf: dict[str, Any]) -> dict[str, Any]:
        """
        Parses the simulation configuration removing all unnecessary options.

        Args:
            conf: "sumo" configuration from Open Controller configuration

        Returns:
            Cleaned version of SUMO configuration.
        """
        result: dict[str, Any] = {}
        for option in conf:
            if option == "graph":
                result[option] = conf[option]

            if option == "file_name":
                result[option] = conf[option]

        return result

    def _parse_controller_conf(self, conf: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """
        Parses the controller configuration removing all unnecessary options.

        Args:
            conf: "controllers" configuration from Open Controller configuration

        Returns:
            Cleaned version of controller configuration.
        """
        result: dict[str, dict[str, Any]] = {}
        for name in conf:
            single_conf: dict[str, Any]
            # If controller's configuration is in a different file, it is read
            # from there.
            if "controller_file" in conf[name]:
                single_conf = self._parse_controller_from_file(
                    conf[name]["controller_file"], name
                )
            # Otherwise the configuration must be found
            # in the original configuration dictionary.
            else:
                single_conf = self._parse_single_controller(conf[name])

            result[name] = single_conf

        return result

    def _parse_controller_from_file(
        self, filename: str, controller_name: str
    ) -> dict[str, Any]:
        # Since individual controller files have the controller name as the key,
        # extra layer needs to be "popped off".
        file_content = self._read_file(filename)[controller_name]
        result = self._parse_single_controller(file_content)
        return result

    def _parse_single_controller(self, conf: dict[str, Any]) -> dict[str, Any]:
        # Single controller configuration in the result is initialized.
        result: dict[str, Any] = {}

        for option in conf:
            if option == "sumo_name":
                result[option] = conf[option]

            if option == "print_status":
                result[option] = conf[option]

            if option == "group_outputs":
                result[option] = conf[option]

            if option == "signal_groups":
                result[option] = conf[option]

            if option == "detectors":
                result[option] = conf[option]

            if option == "extenders":
                result[option] = conf[option]

            if option == "group_list":
                result[option] = conf[option]

            if option == "phases":
                result[option] = conf[option]

            if option == "intergreens":
                result[option] = conf[option]

        return result


class TestGeneralConfiguration(unittest.TestCase):
    def setUp(self):
        # A valid baseline configuration payload
        self.valid_raw_data = {
            "timer": {
                "timer_mode": "cycle",
                "time_step": 1,
                "real_time_multiplier": 2,
                "max_time": 3600,
                "cycle_time": 90,
                "unrelated_field": "ignore_me",
            },
            "sumo": {"graph": True, "file_name": "sim.sumocfg"},
            "active_controllers": ["controller_1"],
            "controllers": {
                "controller_1": {
                    "sumo_name": "tl_1",
                    "print_status": True,
                    "group_outputs": ["group1", "group1", "group2"],
                    "signal_groups": [],
                    "detectors": {"det1": {}},
                    "extenders": {"ext1": {}},
                    "group_list": ["group1", "group2"],
                    "phases": [[1, 0], [0, 1]],
                    "intergreens": [[0, 3], [3, 0]],
                    "extra_junk": 123,
                }
            },
        }
        self.valid_json_str = json.dumps(self.valid_raw_data)

    @patch("builtins.open", new_callable=mock_open)
    @patch("__main__.jsmin", side_effect=lambda x: x)
    def test_successful_initialization(self, mock_jsmin, mock_file):
        """Test that a valid standard configuration initializes correctly and writes the cleaned file."""
        mock_file.return_value.read.return_value = self.valid_json_str

        # Initialize class
        config = GeneralConfiguration("config.json")

        # Assert properties are set correctly and filtered
        self.assertEqual(config.timer["timer_mode"], "cycle")
        self.assertNotIn("unrelated_field", config.timer)
        self.assertEqual(config.sumo["graph"], True)
        self.assertEqual(config.active_controllers, ["controller_1"])
        self.assertIn("controller_1", config.controllers)
        self.assertIn("sumo_name", config.controllers["controller_1"])
        self.assertIn("intergreens", config.controllers["controller_1"])
        self.assertNotIn("extra_junk", config.controllers["controller_1"])

        # Check that it attempted to write the *_cleaned.json file
        mock_file.assert_any_call("config_cleaned.json", "w")

    @patch("builtins.open", new_callable=mock_open)
    @patch("__main__.jsmin", side_effect=lambda x: x)
    def test_legacy_single_controller_conversion(self, mock_jsmin, mock_file):
        """Test that the legacy 'controller' field converts properly into 'controllers'."""
        legacy_data = {
            "timer": {},
            "sumo": {},
            "active_controllers": [],
            "controller": {"name": "my_controller", "sumo_name": "tl_single"},
        }
        mock_file.return_value.read.return_value = json.dumps(legacy_data)

        config = GeneralConfiguration("legacy.json")

        # Verify it converted 'controller' to 'controllers' dictionary format
        self.assertIn("my_controller", config.controllers)
        self.assertEqual(config.controllers["my_controller"]["sumo_name"], "tl_single")

    @patch("builtins.open", side_effect=FileNotFoundError("File not found"))
    def test_file_not_found_exception(self, mock_file):
        """Test that a missing file raises a generic custom Exception."""
        with self.assertRaises(Exception) as context:
            GeneralConfiguration("missing.json")
        self.assertIn("Configuration file not found", str(context.exception))

    @patch("builtins.open", new_callable=mock_open)
    @patch("__main__.jsmin", side_effect=lambda x: x)
    def test_invalid_json_exception(self, mock_jsmin, mock_file):
        """Test that malformed JSON raises a custom Exception."""
        mock_file.return_value.read.return_value = "{ broken json"

        with self.assertRaises(Exception) as context:
            GeneralConfiguration("broken.json")
        self.assertIn("Couldn't parse configuration file", str(context.exception))

    @patch("builtins.open", new_callable=mock_open)
    @patch("__main__.jsmin", side_effect=lambda x: x)
    def test_missing_necessary_fields(self, mock_jsmin, mock_file):
        """Test that a config missing required final top-level keys triggers 'Invalid configuration'."""
        incomplete_data = {"timer": {}, "sumo": {}}  # missing other core parameters
        mock_file.return_value.read.return_value = json.dumps(incomplete_data)

        with self.assertRaises(Exception) as context:
            GeneralConfiguration("incomplete.json")
        self.assertEqual(str(context.exception), "Invalid configuration")

    @patch("builtins.open", new_callable=mock_open)
    @patch("__main__.jsmin", side_effect=lambda x: x)
    def test_active_controllers_not_a_list(self, mock_jsmin, mock_file):
        """Test that if active_controllers is a string instead of a list, ValueError is thrown."""
        bad_active_type = {
            "timer": {},
            "sumo": {},
            "active_controllers": "not-a-list",  # Error here
            "controllers": {},
        }
        mock_file.return_value.read.return_value = json.dumps(bad_active_type)

        with self.assertRaises(ValueError) as context:
            GeneralConfiguration("bad_type.json")
        self.assertIn("is not a list", str(context.exception))

    @patch("builtins.open")
    @patch("__main__.jsmin", side_effect=lambda x: x)
    def test_controller_configuration_from_external_file(
        self, mock_jsmin, mock_open_file
    ):
        """Test reading a separate file when 'controller_file' property is supplied."""
        base_data = {
            "timer": {},
            "sumo": {},
            "active_controllers": [],
            "controllers": {
                "ext_controller": {"controller_file": "external_node.json"}
            },
        }
        external_data = {
            "ext_controller": {
                "sumo_name": "external_tl",
                "print_status": False,
            }
        }

        # Dict matching specific file names to simulated file content strings
        file_contents = {
            "base.json": json.dumps(base_data),
            "external_node.json": json.dumps(external_data),
        }

        # Dynamically switch file contexts based on the name passed to `open()`
        mock_open_file.side_effect = lambda filename, *args, **kwargs: mock_open(
            read_data=file_contents.get(filename, "{}")
        )()

        config = GeneralConfiguration("base.json")

        # Validate external parsing strategy success
        self.assertIn("ext_controller", config.controllers)
        self.assertEqual(
            config.controllers["ext_controller"]["sumo_name"], "external_tl"
        )


if __name__ == "__main__":
    unittest.main()
