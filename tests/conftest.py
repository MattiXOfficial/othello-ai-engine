import os
import pytest

from othello.common.i18n_manager import I18nManager


@pytest.fixture(autouse=True, scope="session")
def force_testing_locale():
    """Force la langue en anglais."""
    # On vide les variables qui pourraient influencer gettext
    os.environ["LANGUAGE"] = "en"
    os.environ["LC_ALL"] = "en_US.UTF-8"
    os.environ["LANG"] = "en_US.UTF-8"

    # On initialise le manager explicitement en anglais
    I18nManager(lang="en")
