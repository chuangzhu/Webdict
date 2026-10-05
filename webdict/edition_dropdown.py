from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk


EDITIONS = [
    ("English", "en"), ("中文", "zh"), ("Español", "es"),
    ("Français", "fr"), ("Deutsch", "de"), ("Italiano", "it"),
    ("日本語", "ja"), ("한국어", "ko"), ("Português", "pt"),
    ("Русский", "ru"), ("العربية", "ar"), ("Nederlands", "nl"),
    ("Polski", "pl"), ("Українська", "uk"), ("Tiếng Việt", "vi"),
    ("Ελληνικά", "el"), ("हिन्दी", "hi"), ("Bahasa Indonesia", "id"),
]


def load_settings() -> Gio.Settings:
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup("cz.chuang.Webdict", True) if source else None
    if schema is None:
        # Support running directly from a Meson source checkout.
        schema_dir = Path(__file__).resolve().parent.parent / "build" / "data"
        if (schema_dir / "gschemas.compiled").exists():
            source = Gio.SettingsSchemaSource.new_from_directory(str(schema_dir), source, False)
            schema = source.lookup("cz.chuang.Webdict", False)
    if schema is None:
        raise RuntimeError("Webdict settings schema was not found; run `meson compile -C build` first.")
    return Gio.Settings.new_full(schema, None, None)


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

        self.settings = load_settings()
        self._restore_edition()
        self.connect("notify::selected", self._save_edition)

    def _restore_edition(self) -> None:
        saved_code = self.settings.get_string("wiktionary-edition")
        selected = next((index for index, (_name, code) in enumerate(EDITIONS)
                         if code == saved_code), 0)
        self.set_selected(selected)

    def _save_edition(self, *_args) -> None:
        if self.get_selected() != Gtk.INVALID_LIST_POSITION:
            _name, code = self.get_selected_edition()
            self.settings.set_string("wiktionary-edition", code)

    def get_selected_edition(self) -> tuple[str, str]:
        return EDITIONS[self.get_selected()]

    def _setup_item(self, _factory, item) -> None:
        item.set_child(Gtk.Label(xalign=0))

    def _bind_code(self, _factory, item) -> None:
        item.get_child().set_text(EDITIONS[item.get_position()][1].upper())

    def _bind_name(self, _factory, item) -> None:
        item.get_child().set_text(item.get_item().get_string())
