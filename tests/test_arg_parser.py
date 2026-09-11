import pytest

from othello.common.arg_parser import ArgParser
from othello.common.config_manager import ConfigManager


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the ConfigManager Singleton state before each test."""
    ConfigManager._instance = None
    yield
    ConfigManager._instance = None


def test_help_option(capsys):
    parser = ArgParser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "show this help message and exit" in captured.out


def test_version_option(capsys):
    parser = ArgParser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "othello" in captured.out


def test_invalid_option(capsys):
    parser = ArgParser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse(["--invalid-option"])
    assert excinfo.value.code != 0


def test_config_update_defaults():
    """Test standard options update ConfigManager."""
    parser = ArgParser()
    parser.parse(
        [
            "--verbose",
            "--debug",
            "--blitz",
            "--time",
            "60",
            "--gui",
            "--size",
            "10",
            "--contest",
            "--lang",
            "en",
        ]
    )

    cm = ConfigManager()
    defaults = cm.config_parser["defaults"]

    assert defaults["verbose"] == "true"
    assert defaults["debug"] == "true"
    assert defaults["blitz"] == "true"
    assert defaults["timeout"] == "60"
    assert defaults["gui"] == "true"
    assert defaults["size"] == "10"
    assert defaults["contest"] == "true"
    assert defaults["lang"] == "en"


def test_ai_options():
    """Test AI-related command line arguments."""
    parser = ArgParser()

    # Test with all AI options
    parser.parse(
        [
            "--ai",
            "w",
            "--ai-time",
            "2.5",
            "--ai-mode",
            "minimax",
            "--ai-minimax-depth",
            "5",
            "--ai-minimax-scoring",
            "function1",
        ]
    )

    cm = ConfigManager()
    defaults = cm.config_parser["defaults"]

    assert defaults["ai_enabled"] == "true"
    assert defaults["ai_color"] == "w"
    assert defaults["ai_time"] == "2.5"
    assert defaults["ai_mode"] == "minimax"
    assert defaults["ai_minimax_depth"] == "5"
    assert defaults["ai_minimax_scoring"] == "function1"


# def test_ai_default_args():
#     """Test AI arguments with default values where applicable."""
#     parser = ArgParser()
#     # --ai without value (nargs='?') -> constant 'default'
#     parser.parse(["--ai"])

#     cm = ConfigManager()
#     defaults = cm.config_parser["defaults"]
#     assert defaults["ai_enabled"] == "true"
#     assert defaults["ai_color"] == "default"


def test_file_load():
    """Test file loading argument."""
    parser = ArgParser()
    parser.parse(["my_save_game.json"])

    cm = ConfigManager()
    defaults = cm.config_parser["defaults"]
    assert defaults["input_file"] == "my_save_game.json"


def test_server_options():
    """Test server-related arguments."""
    parser = ArgParser()
    parser.parse(["--server", "-p", "8080", "--daemon"])

    cm = ConfigManager()
    defaults = cm.config_parser["defaults"]
    assert defaults["server_mode"] == "true"
    assert defaults["server_port"] == "8080"
    assert defaults["daemon"] == "true"


def test_server_default_port():
    """Test server argument default port (const)."""
    parser = ArgParser()
    parser.parse(["--server"])

    cm = ConfigManager()
    defaults = cm.config_parser["defaults"]
    assert defaults["server_mode"] == "true"
    assert defaults["server_port"] == "12345"
