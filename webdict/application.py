from __future__ import annotations

import sys
import os
import logging
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gst", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gst, Gtk, Pango

from . import __version__, quirks
from .edition_dropdown import EditionDropdown  # Register the widget for Gtk.Builder.
from .i18n import _
from .result_text import ResultTextView  # Register the widget for Gtk.Builder.
from .wiktionary import Entry, WiktionaryError, lookup, search_suggestions


class WebdictApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="cz.chuang.Webdict", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="webdict")
        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_shutdown)

        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self.on_about)
        self.add_action(about)
        self.open_wiktionary_action = Gio.SimpleAction.new("open-wiktionary", None)
        self.open_wiktionary_action.set_enabled(False)
        self.open_wiktionary_action.connect("activate", self.on_open)
        self.add_action(self.open_wiktionary_action)
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
        builder = Gtk.Builder()
        builder.set_translation_domain("webdict")
        builder.add_from_resource("/cz/chuang/Webdict/window.ui")
        self.window = builder.get_object("window")
        self.window.set_application(self)
        self.search = builder.get_object("search_entry")
        self.split_view = builder.get_object("split_view")
        self.edition: EditionDropdown = builder.get_object("edition_dropdown")
        self.stack = builder.get_object("content_stack")
        self.title = builder.get_object("title")
        self.result: ResultTextView = builder.get_object("result_text")
        self.result.connect("lookup-word", self.on_definition_word)
        self.retry_button = builder.get_object("retry_button")
        self.error_label = builder.get_object("error_label")
        self.suggestion_stack = builder.get_object("suggestion_stack")
        self.suggestion_list = builder.get_object("suggestion_list")
        self.current_url = None
        self.suggestion_timeout = None
        self.suggestion_generation = 0

        self.search.connect("activate", self.on_search)
        self.search.connect("search-changed", self.on_search_changed)
        self.edition.connect("notify::selected", self.on_search_changed)
        self.retry_button.connect("clicked", self.on_search)
        self.suggestion_list.connect("row-activated", self.on_suggestion_activated)
        self.window.present()
        self.search.grab_focus()

    def on_search_changed(self, *_args) -> None:
        if self.suggestion_timeout is not None:
            GLib.source_remove(self.suggestion_timeout)
            self.suggestion_timeout = None
        self.suggestion_generation += 1
        generation = self.suggestion_generation
        self.suggestion_timeout = GLib.timeout_add(250, self.request_suggestions, generation)

    def request_suggestions(self, generation: int) -> bool:
        self.suggestion_timeout = None
        query = self.search.get_text().strip()
        self.suggestion_stack.set_visible_child_name("loading")
        _name, code = self.edition.get_selected_edition()
        future = self.executor.submit(search_suggestions, query, code)
        future.add_done_callback(
            lambda f: GLib.idle_add(self.finish_suggestions, f, generation, query)
        )
        return GLib.SOURCE_REMOVE

    def finish_suggestions(self, future, generation: int, query: str) -> bool:
        if generation != self.suggestion_generation or query != self.search.get_text().strip():
            return GLib.SOURCE_REMOVE
        try:
            suggestions = future.result()
        except Exception:
            suggestions = ()
        while row := self.suggestion_list.get_row_at_index(0):
            self.suggestion_list.remove(row)
        for suggestion in suggestions:
            label = Gtk.Label(label=suggestion, xalign=0, ellipsize=Pango.EllipsizeMode.END)
            row = Gtk.ListBoxRow(child=label)
            row.suggestion = suggestion
            self.suggestion_list.append(row)
        if suggestions:
            self.suggestion_stack.set_visible_child_name("suggestions")
        else:
            self.suggestion_stack.set_visible_child_name("empty")
        return GLib.SOURCE_REMOVE

    def on_suggestion_activated(self, _list, row) -> None:
        self.search.set_text(row.suggestion)
        self.search.set_position(-1)
        self.on_search()

    def on_definition_word(self, _view, word: str) -> None:
        self.search.set_text(word)
        self.search.set_position(-1)
        self.on_search()

    def on_shutdown(self, *_args) -> None:
        if getattr(self, "result", None) is not None:
            self.result.stop_audio()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _load_resources(self) -> None:
        self._resource = Gio.Resource.load(os.environ["WEBDICT_RESOURCEFILE"])
        Gio.resources_register(self._resource)
        css = Gtk.CssProvider()
        css.load_from_resource("/cz/chuang/Webdict/style.css")
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
        self.title.set_title(word)
        self.result.stop_audio()
        edition_name, code = self.edition.get_selected_edition()
        self.stack.set_visible_child_name("loading")
        self.open_wiktionary_action.set_enabled(False)
        self.current_url = None
        self.split_view.set_show_content(True)
        self.search.set_sensitive(False)
        future = self.executor.submit(lookup, word, code)
        future.add_done_callback(lambda f: GLib.idle_add(self.finish_search, f, edition_name))

    def finish_search(self, future, edition_name: str) -> bool:
        self.search.set_sensitive(True)
        try:
            entry: Entry = future.result()
        except (WiktionaryError, Exception) as exc:
            message = str(exc) if isinstance(exc, WiktionaryError) else _("Something unexpected went wrong.")
            self.error_label.set_label(message)
            self.stack.set_visible_child_name("error")
        else:
            self.result.render_entry(entry)
            self.current_url = entry.url
            self.open_wiktionary_action.set_enabled(True)
            self.stack.set_visible_child_name("result")
        return GLib.SOURCE_REMOVE

    def on_open(self, *_args) -> None:
        if self.current_url:
            Gtk.UriLauncher.new(self.current_url).launch(self.window, None, None)

    def on_about(self, *_args) -> None:
        dialog = Adw.AboutDialog(
            application_name="Webdict",
            application_icon="cz.chuang.Webdict",
            developer_name=_("Webdict contributors"),
            version=__version__,
            comments=_("A focused dictionary for every Wiktionary edition."),
            website="https://github.com/chuangzhu/Webdict",
            license_type=Gtk.License.GPL_3_0,
        )
        dialog.add_acknowledgement_section(
            _("Dictionary Data and Infrastructure"),
            [_("Wiktionary contributors"), _("Wikimedia Foundation")],
        )
        dialog.present(self.props.active_window)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    Gst.init(None)
    quirks.gst_prefer_curl_http_source()
    quirks.export_system_proxy_settings()
    return WebdictApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
