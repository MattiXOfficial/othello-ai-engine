"""I18 Manager Module."""

from pathlib import Path

import gettext
import os
import sys


class I18nManager:
    """I18nManager Class."""

    _instance = None

    def __new__(cls, lang=None):
        if cls._instance is None:
            cls._instance = super(I18nManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, lang=None):
        """Initialize the I18nManager.

        :param lang: The language code to use (e.g., "en", "fr").
            If None, detects from env.

        """
        if self._initialized:
            if lang and lang != self.lang:
                self.lang = lang
                self.init_i18n()  # Re-initialize with new language
            return

        self.lang = lang
        self.gettext = None
        self.init_i18n()
        self._initialized = True

    def init_i18n(self):
        """Setup the internationalization environment.

        Determines the language from environment variables (LC_ALL, LANG)
        if not provided, and installs the gettext translation.

        """
        # Determine language
        if not self.lang:
            env_lang = os.environ.get("LC_ALL", os.environ.get("LANG", "en"))
            # Extract lang code (e.g. fr_FR.UTF-8 -> fr)
            if "." in env_lang:
                env_lang = env_lang.split(".")[0]
            if "_" in env_lang:
                env_lang = env_lang.split("_")[0]
            self.lang = env_lang

        if self.lang.upper() in ["C", "POSIX", ""]:
            self.lang = "en"

        # Support check (F3)
        supported = ["en", "fr"]
        if self.lang not in supported:
            # According to F3, warn and fallback to en
            # We print to stderr
            print(
                f"Warning: Language '{self.lang}' not supported. "
                "Falling back to English.",
                file=sys.stderr,
            )
            self.lang = "en"

        # Setup gettext
        # structure: othello/locales/
        base_path = Path(__file__).resolve().parent.parent
        localedir = base_path / "locales"

        try:
            # Fallback=True ensures that if translation is missing,
            # it uses source
            lang_trans = gettext.translation(
                "othello",
                localedir=str(localedir),
                languages=[self.lang],
                fallback=True,
            )
            self.gettext = lang_trans.gettext
        except Exception as error:
            print(
                f"Warning: i18n initialization failed: {error}",
                file=sys.stderr,
            )
            gettext.install("othello")  # Global fallback
