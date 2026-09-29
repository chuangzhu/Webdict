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
class TextRun:
    text: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Entry:
    title: str
    text: str
    url: str
    runs: tuple[TextRun, ...] = ()


class _ReadableHTML(HTMLParser):
    """Turn MediaWiki HTML into a small, safe rich-text representation."""

    SKIP = {"style", "script", "table", "figure", "sup"}
    SKIP_CLASSES = {
        "mw-editsection", "mw-jump-link", "mw-empty-elt", "noprint",
        "metadata", "thumb", "NavFrame", "sister-project", "interproject",
        "thumbcaption", "gallery", "mw-file-element", "floatleft", "floatright",
        "audiometa", "maintenance-line",
    }
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    BLOCKS = {"h2", "h3", "h4", "h5", "p", "div", "dl", "dt", "dd", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__()
        self.runs: list[TextRun] = []
        self.skip_depth = 0
        self.list_depth = 0
        self.active: list[str] = []
        self.quotation_list_depth: int | None = None

    def _append(self, text: str) -> None:
        if not text:
            return
        tags = tuple(self.active)
        if self.runs and self.runs[-1].tags == tags:
            previous = self.runs[-1]
            self.runs[-1] = TextRun(previous.text + text, tags)
        else:
            self.runs.append(TextRun(text, tags))

    def _newline(self, count: int = 1) -> None:
        while self.runs and not self.runs[-1].text:
            self.runs.pop()
        existing = 0
        if self.runs:
            existing = len(self.runs[-1].text) - len(self.runs[-1].text.rstrip("\n"))
        if existing < count:
            self._append("\n" * (count - existing))

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())
        should_skip = tag in self.SKIP or bool(classes & self.SKIP_CLASSES)
        if self.skip_depth or should_skip:
            if tag not in self.VOID:
                self.skip_depth += 1
            return
        citation_container = "citation-whole" in classes
        starts_quotation_group = citation_container and self.quotation_list_depth is None
        if starts_quotation_group:
            # The first citation is normally preceded by the nested list's
            # bullet. Replace that structural marker with one group control;
            # the renderer adds the line break when the group is expanded.
            if self.runs:
                trimmed = re.sub(r"\n\s*•\s*$", "", self.runs[-1].text)
                self.runs[-1] = TextRun(trimmed, self.runs[-1].tags)
                if not trimmed:
                    self.runs.pop()
            self._append(" ")
            self.quotation_list_depth = self.list_depth
            self.active.append("quotation")
        if tag in {"ul", "ol"}:
            self.list_depth += 1
            self._newline()
        if tag == "li":
            self._newline()
            self._append("  " * max(0, self.list_depth - 1) + "• ")
        elif tag in {"h2", "h3", "h4", "h5"}:
            self._newline()
            self.active.append(tag)
        elif tag in {"p", "div", "dl", "dt", "dd"} and not citation_container:
            self._newline()
        elif tag == "br":
            self._newline()
        if tag in {"b", "strong"}:
            self.active.append("bold")
        elif tag in {"i", "em"}:
            self.active.append("italic")
        elif tag in {"code", "kbd", "samp"}:
            self.active.append("code")
        elif tag == "a":
            self.active.append("link")

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            # Some MediaWiki HTML serializes void elements as <img/> or even
            # <img></img>. That closing event must not close the surrounding
            # skipped container.
            if tag in self.VOID:
                return
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        style = {
            "b": "bold", "strong": "bold", "i": "italic", "em": "italic",
            "code": "code", "kbd": "code", "samp": "code", "a": "link",
            "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h5",
        }.get(tag)
        if style in self.active:
            index = len(self.active) - 1 - self.active[::-1].index(style)
            self.active.pop(index)
        closes_quotation_group = (
            tag in {"ul", "ol"}
            and self.quotation_list_depth is not None
            and self.list_depth == self.quotation_list_depth
        )
        if tag in {"ul", "ol"}:
            self.list_depth = max(0, self.list_depth - 1)
        if tag in self.BLOCKS:
            self._newline()
        if closes_quotation_group:
            if "quotation" in self.active:
                self.active.remove("quotation")
            self.quotation_list_depth = None

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        value = re.sub(r"\s+", " ", data.replace("\xa0", " "))
        if not self.runs or self.runs[-1].text.endswith((" ", "\n")):
            value = value.lstrip()
        self._append(value)

    def text(self) -> str:
        return "".join(run.text for run in self.rich_text()).strip()

    def rich_text(self) -> tuple[TextRun, ...]:
        runs = list(self.runs)
        while runs and not runs[0].text.strip():
            runs.pop(0)
        while runs and not runs[-1].text.strip():
            runs.pop()
        if runs:
            runs[0] = TextRun(runs[0].text.lstrip(), runs[0].tags)
            runs[-1] = TextRun(runs[-1].text.rstrip(), runs[-1].tags)
        return tuple(run for run in runs if run.text)


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
    return Entry(
        title,
        reader.text(),
        f"https://{host}/wiki/{quote(parsed['title'].replace(' ', '_'))}",
        reader.rich_text(),
    )


def search_suggestions(query: str, edition: str, limit: int = 20) -> tuple[str, ...]:
    """Return title completions from a Wiktionary edition's search API."""
    if not query.strip():
        return ()
    data = _get_json(f"{edition}.wiktionary.org", {
        "action": "opensearch",
        "search": query,
        "namespace": "0",
        "limit": str(limit),
        "redirects": "resolve",
        "format": "json",
        "origin": "*",
    })
    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        return ()
    return tuple(str(title) for title in data[1][:limit])
