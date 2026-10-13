from __future__ import annotations

from urllib.parse import unquote, urljoin, urlsplit

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from .i18n import _
from .result_text import ResultTextView
from .wiktionary import Entry


class DefinitionPage(Adw.NavigationPage):
    __gtype_name__ = "WebdictDefinitionPage"
    __gsignals__ = {
        "lookup-word": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "retry": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title(_("Definition"))
        builder = Gtk.Builder()
        builder.set_translation_domain("webdict")
        builder.add_from_resource("/cz/chuang/Webdict/definition-page.ui")
        self.set_child(builder.get_object("definition_toolbar"))
        self.stack = builder.get_object("content_stack")
        self.result: ResultTextView = builder.get_object("result_text")
        self.error_label = builder.get_object("error_label")
        self.find_bar = builder.get_object("find_bar")
        self.find_entry = builder.get_object("find_entry")
        self.find_bar.connect_entry(self.find_entry)
        self.find_entry.connect("search-changed", self._on_find_changed)
        self.find_entry.connect("activate", lambda *_: self._find())
        self.find_entry.connect("next-match", lambda *_: self._find())
        self.find_entry.connect("previous-match", lambda *_: self._find(backwards=True))
        self.find_entry.connect("stop-search", lambda *_: self.find_bar.set_search_mode(False))
        builder.get_object("find_next").connect("clicked", lambda *_: self._find())
        builder.get_object("find_previous").connect("clicked", lambda *_: self._find(backwards=True))
        builder.get_object("retry_button").connect("clicked", lambda *_: self.emit("retry"))
        self.result.connect("activate-link", self._on_activate_link)
        self.result.connect("lookup-word", lambda _view, word: self.emit("lookup-word", word))
        self.connect("hidden", lambda *_: self.result.release_audio())
        self.word = ""
        self.edition_name = ""
        self.edition_code = ""
        self.current_url = None
        self.lookup_generation = 0

    def start_lookup(self, word: str, edition_name: str, code: str) -> int:
        self.find_bar.set_search_mode(False)
        self.find_entry.set_text("")
        self.word = word
        self.edition_name = edition_name
        self.edition_code = code
        self.lookup_generation += 1
        self.current_url = None
        self.set_title(word)
        self.result.stop_audio()
        self.stack.set_visible_child_name("loading")
        return self.lookup_generation

    def show_entry(self, entry: Entry) -> None:
        self.result.render_entry(entry)
        self.current_url = entry.url
        self.stack.set_visible_child_name("result")

    def show_error(self, message: str) -> None:
        self.error_label.set_label(message)
        self.stack.set_visible_child_name("error")

    def open_find(self) -> None:
        if self.stack.get_visible_child_name() != "result":
            return
        self.find_bar.set_search_mode(True)
        self.find_entry.grab_focus()

    def _on_find_changed(self, *_args) -> None:
        if self.find_bar.get_search_mode():
            self._find(restart=True)

    def _find(self, backwards: bool = False, restart: bool = False) -> None:
        query = self.find_entry.get_text()
        self.find_entry.remove_css_class("error")
        if not query or self.stack.get_visible_child_name() != "result":
            return
        if not self.result.find_text(query, backwards=backwards, restart=restart):
            self.find_entry.add_css_class("error")

    def _on_activate_link(self, _view, href: str) -> None:
        if not self.current_url:
            return
        url = urljoin(self.current_url, href)
        target = urlsplit(url)
        if target.scheme not in {"http", "https"}:
            return
        source = urlsplit(self.current_url)
        if target.netloc == source.netloc and target.path.startswith("/wiki/"):
            word = unquote(target.path[len("/wiki/"):]).replace("_", " ")
            if word and ":" not in word and target.path != source.path:
                self.emit("lookup-word", word)
                return
        Gtk.UriLauncher.new(url).launch(self.get_root(), None, None)
