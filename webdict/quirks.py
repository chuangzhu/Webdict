from urllib.request import ProxyHandler, build_opener, install_opener
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


def urllib_honor_gnome_proxy_settings() -> None:
    proxies = Gio.ProxyResolver.get_default().lookup("https://www.wiktionary.org/", None)
    proxy = proxies[0] if proxies else "direct://"
    if proxy != "direct://":
        install_opener(build_opener(ProxyHandler({"http": proxy, "https": proxy})))
