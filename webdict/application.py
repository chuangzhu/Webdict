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
from .definition_page import DefinitionPage
from .edition_dropdown import EditionDropdown  # Register the widget for Gtk.Builder.
from .i18n import _
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
        self.definition_navigation = builder.get_object("definition_navigation")
        self._setup_definition_swipes()
        self.definition_page: DefinitionPage = builder.get_object("definition_page")
        self._connect_definition_page(self.definition_page)
        self.definition_navigation.connect("notify::visible-page", self._update_open_action)
        self.suggestion_stack = builder.get_object("suggestion_stack")
        self.suggestion_list = builder.get_object("suggestion_list")
        self.suggestion_timeout = None
        self.suggestion_generation = 0

        self.search.connect("activate", self.on_search)
        self.search.connect("search-changed", self.on_search_changed)
        self.edition.connect("notify::selected", self.on_search_changed)
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

    def _connect_definition_page(self, page: DefinitionPage) -> None:
        page.connect("lookup-word", self.on_definition_word)
        page.connect("retry", self.on_definition_retry)
        page.connect("showing", self._on_definition_page_showing)
        page.connect("shown", self._on_definition_page_shown)

    def _setup_definition_swipes(self) -> None:
        self.definition_transitioning = False
        self.definition_navigation_controllers = [
            (controller, controller.get_propagation_phase())
            for controller in self.definition_navigation.observe_controllers()
        ]
        # NavigationView holds this model weakly; retain the signal subscription.
        self.definition_navigation_stack = self.definition_navigation.get_navigation_stack()
        self.definition_navigation_stack.connect("items-changed", self._on_definition_stack_changed)
        self._update_definition_swipes()

    def _on_definition_stack_changed(self, *_args) -> None:
        if self.definition_navigation_stack.get_n_items() > 1:
            self._update_definition_swipes()

    def _on_definition_page_shown(self, *_args) -> None:
        # Stack changes happen inside the swipe's end callback. Wait for the
        # transition and callback to finish before resetting its controllers.
        self.definition_transitioning = False
        GLib.idle_add(self._update_definition_swipes)

    def _on_definition_page_showing(self, *_args) -> None:
        self.definition_transitioning = True

    def _update_definition_swipes(self, *_args) -> bool:
        # Disable all inner event handlers at the root so events reach the
        # outer split view. Disabling only GestureDrag leaves other handlers active.
        enabled = self.definition_navigation_stack.get_n_items() > 1
        if not enabled and self.definition_transitioning:
            return GLib.SOURCE_REMOVE
        for controller, phase in self.definition_navigation_controllers:
            controller.set_propagation_phase(phase if enabled else Gtk.PropagationPhase.NONE)
        return GLib.SOURCE_REMOVE

    def on_definition_word(self, source_page: DefinitionPage, word: str) -> None:
        source_page.result.stop_audio()
        page = DefinitionPage()
        self._connect_definition_page(page)
        self.definition_navigation.push(page)
        self._lookup_definition(page, word, source_page.edition_name, source_page.edition_code)

    def on_definition_retry(self, page: DefinitionPage) -> None:
        self._lookup_definition(page, page.word, page.edition_name, page.edition_code)

    def _update_open_action(self, *_args) -> None:
        page = self.definition_navigation.get_visible_page()
        self.open_wiktionary_action.set_enabled(page is not None and page.current_url is not None)

    def on_shutdown(self, *_args) -> None:
        if getattr(self, "definition_navigation", None) is not None:
            pages = self.definition_navigation.get_navigation_stack()
            for index in range(pages.get_n_items()):
                pages.get_item(index).result.release_audio()
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
        edition_name, code = self.edition.get_selected_edition()
        self.definition_navigation.replace([self.definition_page])
        self.split_view.set_show_content(True)
        self._lookup_definition(self.definition_page, word, edition_name, code)

    def _lookup_definition(self, page: DefinitionPage, word: str, edition_name: str, code: str) -> None:
        generation = page.start_lookup(word, edition_name, code)
        self._update_open_action()
        if page is self.definition_page:
            self.search.set_sensitive(False)
        future = self.executor.submit(lookup, word, code)
        future.add_done_callback(lambda f: GLib.idle_add(self.finish_search, f, page, generation))

    def finish_search(self, future, page: DefinitionPage, generation: int) -> bool:
        if generation != page.lookup_generation:
            return GLib.SOURCE_REMOVE
        if page is self.definition_page:
            self.search.set_sensitive(True)
        try:
            entry: Entry = future.result()
        except (WiktionaryError, Exception) as exc:
            message = str(exc) if isinstance(exc, WiktionaryError) else _("Something unexpected went wrong.")
            page.show_error(message)
        else:
            page.show_entry(entry)
        self._update_open_action()
        return GLib.SOURCE_REMOVE

    def on_open(self, *_args) -> None:
        page = self.definition_navigation.get_visible_page()
        if page is not None and page.current_url:
            Gtk.UriLauncher.new(page.current_url).launch(self.window, None, None)

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
