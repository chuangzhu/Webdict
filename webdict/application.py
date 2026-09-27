from __future__ import annotations

import sys
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import __version__
from .wiktionary import Entry, WiktionaryError, lookup


EDITIONS = [
    ("English", "en"), ("中文", "zh"), ("Español", "es"),
    ("Français", "fr"), ("Deutsch", "de"), ("Italiano", "it"),
    ("日本語", "ja"), ("한국어", "ko"), ("Português", "pt"),
    ("Русский", "ru"), ("العربية", "ar"), ("Nederlands", "nl"),
    ("Polski", "pl"), ("Українська", "uk"), ("Tiếng Việt", "vi"),
    ("Ελληνικά", "el"), ("हिन्दी", "hi"), ("Bahasa Indonesia", "id"),
]


class WebdictApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="io.github.webdict.Webdict", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="webdict")
        self.connect("activate", self.on_activate)
        self.connect("shutdown", lambda *_: self.executor.shutdown(wait=False, cancel_futures=True))

        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self.on_about)
        self.add_action(about)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

    def on_activate(self, _app) -> None:
        window = self.props.active_window
        if window:
            window.present()
            return

        self._load_resources()
        builder = Gtk.Builder.new_from_resource("/io/github/webdict/Webdict/window.ui")
        self.window = builder.get_object("window")
        self.window.set_application(self)
        self.search = builder.get_object("search_entry")
        self.edition = builder.get_object("edition_dropdown")
        self.stack = builder.get_object("content_stack")
        self.title = builder.get_object("result_title")
        self.subtitle = builder.get_object("result_subtitle")
        self.result = builder.get_object("result_text")
        self.open_button = builder.get_object("open_button")
        self.retry_button = builder.get_object("retry_button")
        self.error_label = builder.get_object("error_label")
        self.current_url = None

        model = Gtk.StringList.new([name for name, _code in EDITIONS])
        self.edition.set_model(model)
        self.search.connect("activate", self.on_search)
        self.open_button.connect("clicked", self.on_open)
        self.retry_button.connect("clicked", self.on_search)
        builder.get_object("search_button").connect("clicked", self.on_search)
        self.window.present()
        self.search.grab_focus()

    def _load_resources(self) -> None:
        if getattr(self, "_resource", None):
            return
        candidates = [Path.cwd() / "build" / "webdict-resources.gresource"]
        candidates += [Path(p) / "webdict" / "webdict-resources.gresource"
                       for p in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")]
        candidates.append(Path(sys.prefix) / "share" / "webdict" / "webdict-resources.gresource")
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise RuntimeError("Webdict resources were not found; run `meson compile -C build` first.")
        self._resource = Gio.Resource.load(str(path))
        Gio.resources_register(self._resource)
        css = Gtk.CssProvider()
        css.load_from_resource("/io/github/webdict/Webdict/style.css")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def on_search(self, *_args) -> None:
        word = self.search.get_text().strip()
        if not word:
            self.search.add_css_class("error")
            return
        self.search.remove_css_class("error")
        edition_name, code = EDITIONS[self.edition.get_selected()]
        self.stack.set_visible_child_name("loading")
        self.search.set_sensitive(False)
        future = self.executor.submit(lookup, word, code)
        future.add_done_callback(lambda f: GLib.idle_add(self.finish_search, f, edition_name))

    def finish_search(self, future, edition_name: str) -> bool:
        self.search.set_sensitive(True)
        try:
            entry: Entry = future.result()
        except (WiktionaryError, Exception) as exc:
            message = str(exc) if isinstance(exc, WiktionaryError) else "Something unexpected went wrong."
            self.error_label.set_label(message)
            self.stack.set_visible_child_name("error")
        else:
            self.title.set_label(entry.title)
            self.subtitle.set_label(f"From {edition_name} Wiktionary")
            self.result.get_buffer().set_text(entry.text)
            self.current_url = entry.url
            self.stack.set_visible_child_name("result")
        return GLib.SOURCE_REMOVE

    def on_open(self, *_args) -> None:
        if self.current_url:
            Gtk.UriLauncher.new(self.current_url).launch(self.window, None, None)

    def on_about(self, *_args) -> None:
        Adw.AboutDialog(
            application_name="Webdict",
            application_icon="io.github.webdict.Webdict",
            developer_name="Webdict contributors",
            version=__version__,
            comments="A focused dictionary for every Wiktionary edition.",
            website="https://www.wiktionary.org/",
            license_type=Gtk.License.GPL_3_0,
        ).present(self.props.active_window)


def main() -> int:
    return WebdictApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
