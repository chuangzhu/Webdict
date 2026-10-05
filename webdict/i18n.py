"""Gettext setup shared by the application and API client."""

import gettext
import locale
import os
from pathlib import Path

from . import quirks


DOMAIN = "webdict"
LOCALE_DIR = os.environ.get("WEBDICT_LOCALEDIR")

try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass


if not LOCALE_DIR:
    development_locale_dir = Path(__file__).resolve().parent.parent / "build" / "po"
    if development_locale_dir.is_dir():
        LOCALE_DIR = str(development_locale_dir)

quirks.patch_nongnu_locale_module()

if LOCALE_DIR:
    gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
    locale.bindtextdomain(DOMAIN, LOCALE_DIR)
    locale.bind_textdomain_codeset(DOMAIN, "UTF-8")

gettext.textdomain(DOMAIN)
locale.textdomain(DOMAIN)

_ = gettext.gettext
