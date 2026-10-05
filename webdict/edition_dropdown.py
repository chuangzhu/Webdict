from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


EDITIONS = [
    ("English", "en"), ("中文", "zh"), ("Español", "es"),
    ("Français", "fr"), ("Deutsch", "de"), ("Italiano", "it"),
    ("日本語", "ja"), ("한국어", "ko"), ("Português", "pt"),
    ("Русский", "ru"), ("العربية", "ar"), ("Nederlands", "nl"),
    ("Polski", "pl"), ("Українська", "uk"), ("Tiếng Việt", "vi"),
    ("Ελληνικά", "el"), ("हिन्दी", "hi"), ("Bahasa Indonesia", "id"),
]


class EditionDropdown(Gtk.DropDown):
    __gtype_name__ = "WebdictEditionDropdown"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_model(Gtk.StringList.new([name for name, _code in EDITIONS]))

        code_factory = Gtk.SignalListItemFactory()
        code_factory.connect("setup", self._setup_item)
        code_factory.connect("bind", self._bind_code)
        self.set_factory(code_factory)

        name_factory = Gtk.SignalListItemFactory()
        name_factory.connect("setup", self._setup_item)
        name_factory.connect("bind", self._bind_name)
        self.set_list_factory(name_factory)

    def get_selected_edition(self) -> tuple[str, str]:
        return EDITIONS[self.get_selected()]

    def _setup_item(self, _factory, item) -> None:
        item.set_child(Gtk.Label(xalign=0))

    def _bind_code(self, _factory, item) -> None:
        item.get_child().set_text(EDITIONS[item.get_position()][1].upper())

    def _bind_name(self, _factory, item) -> None:
        item.get_child().set_text(item.get_item().get_string())
