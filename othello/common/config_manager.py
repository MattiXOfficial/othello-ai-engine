"""Config Manager Module."""

from pathlib import Path

import configparser
import sys

from othello.common.i18n_manager import I18nManager


def _(message):
    return I18nManager().gettext(message)


class ConfigManager:
    """ConfigManager Class."""

    _instance = None

    DEFAULT_CONFIG = {
        "defaults": {
            "verbose": "false",
            "debug": "false",
            "blitz": "false",
            "timeout": "30",
            "size": "8",
            "ai-mode": "minimax",
            "ai-time": "5",
            "ai-minimax-depth": "5",
            "lang": "en",
            "server_port": "12345",
        }
    }

    def __new__(cls):  # DP SINGLETON
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):  # DP SINGLETON
            return
        self._initialized = True

        self.config_parser = configparser.ConfigParser()
        self.config_path = Path.home() / ".othellorc"
        self._load_config()

    def _load_config(self):
        """Load configuration from defaults and the configuration file.

        Reads the default configuration and tries to update it from the file
        at ``self.config_path``. If the file is missing, it creates a default
        one.

        """
        # Load defaults
        self.config_parser.read_dict(self.DEFAULT_CONFIG)

        # Load from file if it exists
        if self.config_path.exists():
            try:
                self.config_parser.read(self.config_path, encoding="utf-8")
            except configparser.Error as error:
                # Requirement F2: Display warning if
                # invalid but continue with defaults
                print(
                    _(
                        "Warning: Could not parse config file {path}: {error}"
                    ).format(path=self.config_path, error=error),
                    file=sys.stderr,
                )
        else:
            # Requirement F2: Create minimal config file if not present
            self._create_default_config_file()

    def reset_to_defaults(self):
        """Reset the configuration to the internal hardcoded defaults."""
        self.config_parser.clear()
        self.config_parser.read_dict(self.DEFAULT_CONFIG)

    def valid_options_check(self) -> bool:
        """Validate the loaded configuration options."""
        if "defaults" not in self.config_parser:
            print(
                _("Error: Config file missing 'defaults' section."),
                file=sys.stderr,
            )
            return False

        config = self.config_parser["defaults"]
        is_valid = True

        for key, value in config.items():
            if not self._validate_single_option(key, value):
                is_valid = False

        return is_valid

    def _validate_single_option(self, key: str, value: str) -> bool:
        """Dispatch validation for a single key-value pair."""
        try:
            if key in (
                "verbose",
                "debug",
                "blitz",
                "gui",
                "server_mode",
                "daemon",
                "contest",
                "ai_enabled",
            ):
                return self._validate_bool(key, value)
            if key == "timeout":
                return self._validate_int(key, value, min_val=1)
            if key == "size":
                return self._validate_int(
                    key, value, allowed_values=(6, 8, 10, 12)
                )
            if key in ("ai-mode", "ai_mode"):
                return self._validate_choice(
                    key, value, ("minimax", "iterative", "mcts")
                )
            if key in ("ai-mcts-selection", "ai_mcts_selection"):
                return self._validate_choice(key, value, ("UCT", "ML", "DL"))
            if key in ("ai-time", "ai_time"):
                return self._validate_float(key, value, min_val=0.0001)
            if key in ("ai-minimax-depth", "ai_minimax_depth"):
                return self._validate_int(key, value, min_val=1)
            if key == "lang":
                return self._validate_choice(key, value, ("en", "fr"))
            if key == "server_port":
                return self._validate_int(key, value, min_val=1, max_val=65535)

            # Options sans validation stricte (juste string) ou inconnues
            if key in (
                "ai_color",
                "ai-minimax-scoring",
                "ai_minimax_scoring",
                "input_file",
            ):
                return True

            # Option inconnue
            print(
                _("Warning: Unknown option '{key}' in configuration.").format(
                    key=key
                ),
                file=sys.stderr,
            )
            return False

        except ValueError:
            print(
                _("Error: Invalid type for '{key}': {value}").format(
                    key=key, value=value
                ),
                file=sys.stderr,
            )
            return False

    def _validate_bool(self, key: str, value: str) -> bool:
        if value.lower() not in ("true", "false"):
            print(
                _("Error: '{key}' must be 'true' or 'false'.").format(key=key),
                file=sys.stderr,
            )
            return False
        return True

    def _validate_int(
        self,
        key: str,
        value: str,
        min_val=None,
        max_val=None,
        allowed_values=None,
    ) -> bool:
        val = int(value)
        if allowed_values and val not in allowed_values:
            print(
                _("Error: '{key}' must be one of {allowed_values}.").format(
                    key=key, allowed_values=allowed_values
                ),
                file=sys.stderr,
            )
            return False
        if min_val is not None and val < min_val:
            print(
                _("Error: '{key}' must be >= {min_val}.").format(
                    key=key, min_val=min_val
                ),
                file=sys.stderr,
            )
            return False
        if max_val is not None and val > max_val:
            print(
                _("Error: '{key}' must be <= {max_val}.").format(
                    key=key, max_val=max_val
                ),
                file=sys.stderr,
            )
            return False
        return True

    def _validate_float(self, key: str, value: str, min_val=None) -> bool:
        val = float(value)
        if min_val is not None and val < min_val:
            print(
                _("Error: '{key}' must be > {min_val}.").format(
                    key=key, min_val=min_val
                ),
                file=sys.stderr,
            )
            return False
        return True

    def _validate_choice(self, key: str, value: str, choices: tuple) -> bool:
        if value not in choices:
            print(
                _("Error: '{key}' must be one of {choices}.").format(
                    key=key, choices=choices
                ),
                file=sys.stderr,
            )
            return False
        return True

    def _create_default_config_file(self):
        """Create a new configuration file with default settings."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as configfile:
                self.config_parser.write(configfile)
        except IOError as error:
            print(
                _(
                    "Warning: Could not "
                    "create default config file {path}: {error}"
                ).format(path=self.config_path, error=error),
                file=sys.stderr,
            )

    def set(self, key: str, value: str):
        """Set a configuration option and save it directly to the file.

        :param key: The configuration key to set.
        :param value: The value to assign.

        """
        if "defaults" not in self.config_parser:
            self.config_parser["defaults"] = {}

        self.config_parser["defaults"][key] = str(value)
