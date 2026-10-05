import urllib.request
import logging
import locale
import os
import gi

gi.require_version("Gst", "1.0")

from gi.repository import Gio, Gst


def gst_prefer_curl_http_source() -> None:
    curl_source = Gst.ElementFactory.find("curlhttpsrc")
    soup_source = Gst.ElementFactory.find("souphttpsrc")
    if curl_source is not None:
        curl_source.set_rank(int(Gst.Rank.PRIMARY) + 1)
    if soup_source is not None:
        soup_source.set_rank(Gst.Rank.MARGINAL)


def export_system_proxy_settings() -> None:
    # macOS / Windows
    proxy = urllib.request.getproxies().get("https")
    if proxy:
        os.environ.setdefault("HTTPS_PROXY", proxy)
        logging.info("Exported proxy to Gst: %s", proxy)
        return

    # GNOME
    proxies = Gio.ProxyResolver.get_default().lookup("https://www.wiktionary.org/", None)
    proxy = proxies[0] if proxies else "direct://"
    if proxy != "direct://":
        os.environ.setdefault("HTTPS_PROXY", proxy)
        logging.info("Applied Gio proxy settings to Gst and urllib: %s", proxy)


def patch_nongnu_locale_module() -> None:
    checks = "bindtextdomain", "bind_textdomain_codeset", "textdomain"
    if all(hasattr(locale, name) for name in checks):
        return

    from ctypes import CDLL, c_char_p, c_wchar_p
    libintl = CDLL(None)  # Pulled by gi

    if os.name == "nt":
        libintl.wbindtextdomain.argtypes = [c_char_p, c_wchar_p]
        libintl.wbindtextdomain.restype = c_wchar_p
    else:
        libintl.bindtextdomain.argtypes = [c_char_p, c_char_p]
        libintl.bindtextdomain.restype = c_char_p
    libintl.bind_textdomain_codeset.argtypes = [c_char_p, c_char_p]
    libintl.bind_textdomain_codeset.restype = c_char_p
    libintl.textdomain.argtypes = [c_char_p]
    libintl.textdomain.restype = c_char_p

    def bindtextdomain(domain: str, dir: str) -> str:
        if os.name == "nt":
            return libintl.wbindtextdomain(domain.encode(), dir)
        return libintl.bindtextdomain(domain.encode(), dir.encode()).decode()

    def bind_textdomain_codeset(domain: str, codeset: str) -> str:
        return libintl.bind_textdomain_codeset(domain.encode(), codeset.encode()).decode()

    def textdomain(domain: str) -> str:
        return libintl.textdomain(domain.encode()).decode()

    locale.bindtextdomain = bindtextdomain
    locale.bind_textdomain_codeset = bind_textdomain_codeset
    locale.textdomain = textdomain
