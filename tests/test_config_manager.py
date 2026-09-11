from pathlib import Path
from unittest.mock import patch

import pytest

from othello.common.config_manager import ConfigManager

# Define the real path to the config file in the user's home directory
CONFIG_PATH = Path.home() / ".othellorc"
BACKUP_PATH = Path.home() / ".othellorc.bak_test"


@pytest.fixture(autouse=True)
def manage_environment():
    """(Executed before and after each test)

    Setup and Teardown:
    1. Reset Singleton.
    2. Backup existing config file if present.
    3. Ensure clean state (no config file) before test.
    4. Restore backup after test.
    """
    # Reset Singleton
    ConfigManager._instance = None

    # Backup existing file
    file_existed = False
    if CONFIG_PATH.exists():
        file_existed = True
        CONFIG_PATH.rename(BACKUP_PATH)

    yield

    # Teardown: Clean up created file
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()

    # Restore backup
    if file_existed and BACKUP_PATH.exists():
        BACKUP_PATH.rename(CONFIG_PATH)

    # Reset Singleton again just in case
    ConfigManager._instance = None


def test_missing_config_file_creates_default():
    """Test 1: If the configuration file is missing:

    - It must be created (minimal config).
    - The program must launch with default options.
    """
    # Ensure file is missing (handled by fixture, but double check)
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()

    # Initialize ConfigManager
    cm = ConfigManager()

    # Verify defaults are loaded
    assert cm.config_parser["defaults"]["verbose"] == "false"
    assert cm.config_parser["defaults"]["timeout"] == "30"

    # Verify that the file was created in the REAL home directory
    assert CONFIG_PATH.exists()

    # Verify content
    content = CONFIG_PATH.read_text()
    assert "[defaults]" in content
    assert "verbose = false" in content


def test_invalid_config_file_warning(capsys):
    """Test 2: If the configuration file is present but invalid:

    - The program must display a warning message.
    - The program must launch with default options without overwriting the
      file.
    """
    # Create an invalid file
    original_content = "This is not a valid INI file"
    CONFIG_PATH.write_text(original_content)

    # Initialize ConfigManager
    cm = ConfigManager()

    # Check stdout for the warning message using sys.stdout capture
    # (Checking console output relies on capsys fixture)
    captured = capsys.readouterr()
    assert "Warning: Could not parse config file" in captured.err

    # Verify defaults are still loaded
    assert cm.config_parser["defaults"]["verbose"] == "false"

    # Verify the file content was NOT changed (not overwritten)
    assert CONFIG_PATH.read_text() == original_content


def test_singleton_ensure_same_instance():
    cm1 = ConfigManager()
    cm2 = ConfigManager()
    assert cm1 is cm2


def test_reset_to_defaults():
    cm = ConfigManager()
    # Modify config
    cm.config_parser["defaults"]["verbose"] = "true"
    assert cm.config_parser["defaults"]["verbose"] == "true"

    cm.reset_to_defaults()
    assert cm.config_parser["defaults"]["verbose"] == "false"


def test_valid_options_check_missing_defaults(capsys):
    cm = ConfigManager()
    # Remove defaults section
    del cm.config_parser["defaults"]

    assert cm.valid_options_check() is False
    captured = capsys.readouterr()
    assert "Error: Config file missing 'defaults' section." in captured.err


def test_valid_options_check_invalid_values(capsys):
    cm = ConfigManager()

    # Invalid boolean (verbose)
    cm.config_parser["defaults"]["verbose"] = "maybe"
    assert cm.valid_options_check() is False
    captured = capsys.readouterr()
    assert "must be 'true' or 'false'" in captured.err

    # Invalid int (timeout)
    cm.config_parser["defaults"]["verbose"] = "false"  # Reset valid
    cm.config_parser["defaults"]["timeout"] = "-5"
    assert cm.valid_options_check() is False
    captured = capsys.readouterr()
    assert "must be >= 1" in captured.err

    cm.config_parser["defaults"]["timeout"] = "abc"
    assert cm.valid_options_check() is False
    capsys.readouterr()

    # Invalid size
    cm.config_parser["defaults"]["timeout"] = "30"  # Reset valid
    cm.config_parser["defaults"]["size"] = "9"
    assert cm.valid_options_check() is False
    captured = capsys.readouterr()
    assert "must be one of (6, 8, 10, 12)" in captured.err

    # Invalid ai-mode
    cm.config_parser["defaults"]["size"] = "8"  # Reset valid
    cm.config_parser["defaults"]["ai-mode"] = "random"
    assert cm.valid_options_check() is False

    # Invalid ai-time
    cm.config_parser["defaults"]["ai-mode"] = "minimax"  # Reset valid
    cm.config_parser["defaults"]["ai-time"] = "-1"
    assert cm.valid_options_check() is False

    # Invalid ai-minimax-depth
    cm.config_parser["defaults"]["ai-time"] = "5"  # Reset valid
    cm.config_parser["defaults"]["ai-minimax-depth"] = "0"
    assert cm.valid_options_check() is False

    # Invalid lang
    cm.config_parser["defaults"]["ai-minimax-depth"] = "5"  # Reset valid
    cm.config_parser["defaults"]["lang"] = "es"
    assert cm.valid_options_check() is False


def test_set_and_save_config():
    cm = ConfigManager()
    cm.set("verbose", "false")

    assert cm.config_parser["defaults"]["verbose"] == "false"
    # Verify it was written to file
    content = CONFIG_PATH.read_text()
    assert "verbose = false" in content


def test_set_creates_defaults_if_missing():
    cm = ConfigManager()
    del cm.config_parser["defaults"]  # Simulate missing defaults
    cm.set("verbose", "true")
    assert "defaults" in cm.config_parser
    assert cm.config_parser["defaults"]["verbose"] == "true"


# @patch("builtins.open", side_effect=IOError("Mocked IOError"))
# def test_save_config_ioerror(mock_open, capsys):
#     cm = ConfigManager()
#     cm.save_config()
#     captured = capsys.readouterr()
#     assert "Error saving config: Mocked IOError" in captured.err


@patch("builtins.open", side_effect=IOError("Mocked IOError"))
def test_create_default_config_ioerror(mock_open, capsys):
    # We must reset instance to trigger __init__ and
    # _create_default_config_file again
    ConfigManager._instance = None
    # We also need to ensure config path doesn't exist so it tries to create it
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()

    ConfigManager()
    captured = capsys.readouterr()
    assert "Warning: Could not create default config file" in captured.err
