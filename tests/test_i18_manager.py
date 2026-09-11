from unittest.mock import patch

import pytest

from othello.common.i18n_manager import I18nManager


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the I18nManager Singleton state before each test."""
    I18nManager._instance = None
    yield  # above yield = executed before test/ under yield = executed after
    I18nManager._instance = None


def test_i18n_manager_language_detection(monkeypatch, capsys):
    """Test 1: Language detection logic.

    - Default to 'en'.
    - Use LANG/LC_ALL if set.
    - Warn and fallback if unsupported.
    """
    # Case 1: Default (no env vars) -> 'en'
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    manager = I18nManager()
    assert manager.lang == "en"

    # Reset for next case
    I18nManager._instance = None

    # Case 2: LANG='fr_FR.UTF-8' -> 'fr'
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    manager = I18nManager()
    assert manager.lang == "fr"

    # Reset for next case
    I18nManager._instance = None

    # Case 2b: LC_ALL takes precedence
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
    manager = I18nManager()
    assert manager.lang == "fr"

    # Reset for next case
    I18nManager._instance = None

    # Case 3: Unsupported language -> fallback to 'en' + warning
    monkeypatch.setenv("LANG", "es_ES.UTF-8")  # Spanish not supported
    monkeypatch.delenv("LC_ALL", raising=False)
    manager = I18nManager()

    assert manager.lang == "en"
    captured = capsys.readouterr()
    assert "Warning: Language 'es' not supported" in captured.err
    assert "Falling back to English" in captured.err


def test_singleton_logic():
    m1 = I18nManager()
    m2 = I18nManager()
    assert m1 is m2

    # Ensure init_i18n not called twice
    # (mocking harder here due to internal call in __init__)
    # But we can check _initialized
    assert m1._initialized is True


@patch("othello.common.i18n_manager.gettext")
def test_init_i18n_exception(mock_gettext, capsys):
    # Simulate exception during gettext.translation
    mock_gettext.translation.side_effect = Exception("Mocked Exception")

    I18nManager._instance = None
    I18nManager()

    captured = capsys.readouterr()
    assert (
        "Warning: i18n initialization failed: Mocked Exception" in captured.err
    )
    # Should fallback to global install
    mock_gettext.install.assert_called_with("othello")


def test_language_parsing_edge_cases(monkeypatch):
    # Test just "fr" (no dots or underscores)
    monkeypatch.setenv("LANG", "fr")
    monkeypatch.delenv("LC_ALL", raising=False)

    I18nManager._instance = None
    manager = I18nManager()
    assert manager.lang == "fr"

    # Test "fr_CA" (underscore only)
    I18nManager._instance = None
    monkeypatch.setenv("LANG", "fr_CA")
    manager = I18nManager()
    assert manager.lang == "fr"
