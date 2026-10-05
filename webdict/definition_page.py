from __future__ import annotations

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
        builder.get_object("retry_button").connect("clicked", lambda *_: self.emit("retry"))
        self.result.connect("lookup-word", lambda _view, word: self.emit("lookup-word", word))
        self.connect("hidden", lambda *_: self.result.release_audio())
        self.word = ""
        self.edition_name = ""
        self.edition_code = ""
        self.current_url = None
        self.lookup_generation = 0

    def start_lookup(self, word: str, edition_name: str, code: str) -> int:
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
