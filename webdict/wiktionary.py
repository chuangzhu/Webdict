"""Small, edition-agnostic MediaWiki API client."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen


USER_AGENT = "Webdict/0.1 (GTK Wiktionary reader; https://github.com/webdict/webdict)"


class WiktionaryError(Exception):
    pass


@dataclass(frozen=True)
class Entry:
    title: str
    text: str
    url: str


class _ReadableHTML(HTMLParser):
    """Turn MediaWiki's definition HTML into compact, readable plain text."""

    SKIP = {"style", "script", "table", "figure", "sup"}
    BLOCKS = {"h2", "h3", "h4", "h5", "p", "div", "dl", "dt", "dd", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0
        self.list_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.SKIP:
            self.skip_depth += 1
        if self.skip_depth:
            return
        if tag in {"ul", "ol"}:
            self.list_depth += 1
        if tag == "li":
            self.parts.append("\n" + "  " * max(0, self.list_depth - 1) + "• ")
        elif tag in self.BLOCKS:
            self.parts.append("\n")
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in {"ul", "ol"}:
            self.list_depth = max(0, self.list_depth - 1)
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts).replace("\xa0", " ")
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _get_json(host: str, params: dict[str, str], timeout: int = 15):
    url = f"https://{host}/w/api.php?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise WiktionaryError(f"Wiktionary returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise WiktionaryError("Could not connect to Wiktionary.") from exc


def lookup(word: str, edition: str) -> Entry:
    """Look up *word* on any Wikimedia Wiktionary edition."""
    host = f"{edition}.wiktionary.org"
    data = _get_json(host, {
        "action": "parse",
        "page": word,
        "prop": "text|displaytitle",
        "redirects": "1",
        "format": "json",
        "formatversion": "2",
        "origin": "*",
    })
    if "error" in data:
        code = data["error"].get("code", "")
        if code == "missingtitle":
            raise WiktionaryError(f"No entry found for “{word}”.")
        raise WiktionaryError(data["error"].get("info", "Wiktionary returned an error."))

    parsed = data["parse"]
    reader = _ReadableHTML()
    reader.feed(parsed["text"])
    title = re.sub(r"<[^>]+>", "", parsed.get("displaytitle", parsed["title"]))
    return Entry(title, reader.text(), f"https://{host}/wiki/{quote(parsed['title'].replace(' ', '_'))}")
