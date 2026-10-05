from __future__ import annotations

import sys
import os
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gst", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gst, Gtk, Pango

from . import __version__, quirks
from .i18n import _
from .wiktionary import Entry, WiktionaryError, lookup, search_suggestions


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
        self.edition = builder.get_object("edition_dropdown")
        self.stack = builder.get_object("content_stack")
        self.title = builder.get_object("title")
        self.result = builder.get_object("result_text")
        self.result_buffer = self.result.get_buffer()
        self._create_text_styles()
        self.definition_sections = []
        self.collapsed_sections = set()
        self.section_buttons = []
        self.definition_quotations = []
        self.collapsed_quotations = set()
        self.quotation_buttons = []
        self.audio_buttons = []
        self.active_audio = None
        self.active_audio_button = None
        definition_click = Gtk.GestureClick.new()
        definition_click.set_button(Gdk.BUTTON_PRIMARY)
        definition_click.connect("released", self.on_definition_click)
        self.result.add_controller(definition_click)
        self.retry_button = builder.get_object("retry_button")
        self.error_label = builder.get_object("error_label")
        self.suggestion_stack = builder.get_object("suggestion_stack")
        self.suggestion_list = builder.get_object("suggestion_list")
        self.current_url = None
        self.suggestion_timeout = None
        self.suggestion_generation = 0

        model = Gtk.StringList.new([name for name, _code in EDITIONS])
        self.edition.set_model(model)
        code_factory = Gtk.SignalListItemFactory()
        code_factory.connect("setup", self.setup_edition_item)
        code_factory.connect("bind", self.bind_edition_code)
        self.edition.set_factory(code_factory)
        name_factory = Gtk.SignalListItemFactory()
        name_factory.connect("setup", self.setup_edition_item)
        name_factory.connect("bind", self.bind_edition_name)
        self.edition.set_list_factory(name_factory)
        self.search.connect("activate", self.on_search)
        self.search.connect("search-changed", self.on_search_changed)
        self.edition.connect("notify::selected", self.on_search_changed)
        self.retry_button.connect("clicked", self.on_search)
        self.suggestion_list.connect("row-activated", self.on_suggestion_activated)
        self.window.present()
        self.search.grab_focus()

    def setup_edition_item(self, _factory, item) -> None:
        item.set_child(Gtk.Label(xalign=0))

    def bind_edition_code(self, _factory, item) -> None:
        item.get_child().set_text(EDITIONS[item.get_position()][1])

    def bind_edition_name(self, _factory, item) -> None:
        item.get_child().set_text(item.get_item().get_string())

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
        _name, code = EDITIONS[self.edition.get_selected()]
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

    def on_definition_click(self, _gesture, presses: int, x: float, y: float) -> None:
        """Look up a word that was double-clicked in the definition."""
        if presses != 2:
            return
        # Let GtkTextView's native double-click handler establish its word
        # selection before reading it on the next main-loop iteration.
        GLib.idle_add(self.lookup_selected_definition_word)

    def toggle_definition_section(self, section_index: int) -> bool:
        if section_index in self.collapsed_sections:
            self.collapsed_sections.remove(section_index)
        else:
            self.collapsed_sections.add(section_index)
        self._apply_collapsed_sections()
        self._set_section_disclosure(section_index)
        return GLib.SOURCE_REMOVE

    def lookup_selected_definition_word(self) -> bool:
        if not self.result_buffer.get_has_selection():
            return GLib.SOURCE_REMOVE
        start, end = self.result_buffer.get_selection_bounds()
        word = self.result_buffer.get_text(start, end, False).strip()
        if not word:
            return GLib.SOURCE_REMOVE
        self.search.set_text(word)
        self.search.set_position(-1)
        self.on_search()
        return GLib.SOURCE_REMOVE

    def _create_text_styles(self) -> None:
        styles = {
            "bold": {"weight": Pango.Weight.BOLD},
            "italic": {"style": Pango.Style.ITALIC},
            "code": {"family": "monospace"},
            "link": {"underline": Pango.Underline.SINGLE},
            "h2": {"weight": Pango.Weight.BOLD, "scale": 1.55, "pixels_above_lines": 10, "pixels_below_lines": 3},
            "h3": {"weight": Pango.Weight.BOLD, "scale": 1.3, "pixels_above_lines": 8, "pixels_below_lines": 2},
            "h4": {"weight": Pango.Weight.BOLD, "scale": 1.15, "pixels_above_lines": 6},
            "h5": {"weight": Pango.Weight.BOLD},
            "quotation": {"left_margin": 20, "right_margin": 12},
            "collapsed": {"invisible": True},
        }
        for name, properties in styles.items():
            self.result_buffer.create_tag(name, **properties)

    def _render_entry(self, entry: Entry) -> None:
        self.result_buffer.set_text("")
        self.definition_sections = []
        self.collapsed_sections = set()
        self.definition_quotations = []
        self.collapsed_quotations = set()
        if self.active_audio is not None:
            self._stop_active_audio()
        for button in self.audio_buttons:
            if button.player is not None:
                button.player.set_state(Gst.State.NULL)
                button.bus.remove_signal_watch()
        for button in self.section_buttons + self.quotation_buttons + self.audio_buttons:
            if button.get_parent() is self.result:
                self.result.remove(button)
        self.section_buttons = []
        self.quotation_buttons = []
        self.audio_buttons = []
        heading_style = None
        in_quotation = False

        def finish_heading() -> None:
            section_index = len(self.definition_sections) - 1
            section = self.definition_sections[section_index]
            self.result_buffer.insert(self.result_buffer.get_end_iter(), " ")
            anchor = self.result_buffer.create_child_anchor(self.result_buffer.get_end_iter())
            button = Gtk.Button(
                icon_name="pan-down-symbolic",
                tooltip_text=_("Collapse section"),
                valign=Gtk.Align.CENTER,
            )
            button.add_css_class("flat")
            button.add_css_class("circular")
            button.add_css_class("section-disclosure")
            button.connect(
                "clicked",
                lambda _button, index=section_index: self.toggle_definition_section(index),
            )
            self.result.add_child_at_anchor(button, anchor)
            self.section_buttons.append(button)
            section["button"] = button
            section["heading_end"] = self.result_buffer.get_char_count()

        for run in entry.runs:
            run_heading = next((tag for tag in run.tags if tag in {"h2", "h3", "h4", "h5"}), None)
            run_quotation = "quotation" in run.tags
            if heading_style and run_heading != heading_style:
                finish_heading()
            if in_quotation and not run_quotation:
                self.definition_quotations[-1]["content_end"] = self.result_buffer.get_char_count()
            if run_heading and run_heading != heading_style:
                heading_start = self.result_buffer.get_char_count()
                self.definition_sections.append({
                    "level": int(run_heading[1]),
                    "style": run_heading,
                    "button": None,
                    "heading_start": heading_start,
                    "heading_end": heading_start,
                    "content_start": 0,
                    "content_end": 0,
                })
            if run_quotation and not in_quotation:
                quotation_index = len(self.definition_quotations)
                anchor = self.result_buffer.create_child_anchor(self.result_buffer.get_end_iter())
                icon = Gtk.Image.new_from_icon_name("pan-start-symbolic")
                label = Gtk.Label(label=_("quotations"))
                button_content = Gtk.Box(spacing=4)
                button_content.append(label)
                button_content.append(icon)
                button = Gtk.Button(child=button_content, tooltip_text=_("Expand quotations"), valign=Gtk.Align.CENTER)
                button.add_css_class("flat")
                button.add_css_class("quotation-disclosure")
                button.connect(
                    "clicked",
                    lambda _button, index=quotation_index: self.toggle_definition_quotation(index),
                )
                self.result.add_child_at_anchor(button, anchor)
                self.quotation_buttons.append(button)
                self.result_buffer.insert(self.result_buffer.get_end_iter(), "\n")
                content_start = self.result_buffer.get_char_count()
                self.result_buffer.insert(self.result_buffer.get_end_iter(), "• ")
                self.definition_quotations.append({
                    "button": button,
                    "icon": icon,
                    "content_start": content_start,
                    "content_end": 0,
                })
            if run.audio_url:
                anchor = self.result_buffer.create_child_anchor(self.result_buffer.get_end_iter())
                button = Gtk.Button(
                    icon_name="audio-volume-high-symbolic",
                    tooltip_text=_("Play pronunciation"),
                    valign=Gtk.Align.CENTER,
                )
                button.add_css_class("flat")
                button.add_css_class("circular")
                button.add_css_class("audio-button")
                button.audio_url = run.audio_url
                button.player = None
                button.bus = None
                button.playing = False
                button.connect("clicked", self.on_audio_clicked)
                self.result.add_child_at_anchor(button, anchor)
                self.audio_buttons.append(button)
            position = self.result_buffer.get_end_iter()
            if run.text and run.tags:
                tags = [self.result_buffer.get_tag_table().lookup(name) for name in run.tags]
                self.result_buffer.insert_with_tags(position, run.text, *tags)
            elif run.text:
                self.result_buffer.insert(position, run.text)
            heading_style = run_heading
            in_quotation = run_quotation

        if heading_style:
            finish_heading()
        if in_quotation:
            self.definition_quotations[-1]["content_end"] = self.result_buffer.get_char_count()

        total = self.result_buffer.get_char_count()
        for index, section in enumerate(self.definition_sections):
            content_start = section["heading_end"]
            iterator = self.result_buffer.get_iter_at_offset(content_start)
            if not iterator.is_end() and iterator.get_char() == "\n":
                content_start += 1
            section["content_start"] = content_start
            section["content_end"] = next((
                candidate["heading_start"]
                for candidate in self.definition_sections[index + 1:]
                if candidate["level"] <= section["level"]
            ), total)
        self.collapsed_quotations = set(range(len(self.definition_quotations)))
        self._apply_collapsed_sections()
        for quotation in self.definition_quotations:
            quotation["button"].set_tooltip_text(_("Expand quotations"))

    def on_audio_clicked(self, button) -> None:
        if button.player is None:
            button.player = self._create_audio_pipeline(button.audio_url)
            logging.info("Playing %s", button.audio_url)
            if button.player is None:
                button.set_sensitive(False)
                button.set_tooltip_text(_("Audio playback is unavailable"))
                return
            button.bus = button.player.get_bus()
            button.bus.add_signal_watch()
            button.bus.connect("message", self.on_audio_message, button)
        if button.playing:
            button.player.set_state(Gst.State.PAUSED)
            self._set_audio_button_playing(button, False)
            return
        if self.active_audio is not None and self.active_audio is not button.player:
            self._stop_active_audio()
        self.active_audio = button.player
        self.active_audio_button = button
        result = button.player.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            self._stop_active_audio(_("Audio playback failed"))
            return
        self._set_audio_button_playing(button, True)

    def _create_audio_pipeline(self, url: str):
        player = Gst.ElementFactory.make("playbin", None)
        if player is not None:
            player.set_property("uri", url)
            player.set_property("buffer-duration", 10 * Gst.SECOND)
        return player

    def on_audio_message(self, _bus, message, button) -> None:
        if message.type == Gst.MessageType.EOS:
            button.player.set_state(Gst.State.NULL)
            self._set_audio_button_playing(button, False)
            if self.active_audio is button.player:
                self.active_audio = None
                self.active_audio_button = None
        elif message.type == Gst.MessageType.ERROR:
            button.player.set_state(Gst.State.NULL)
            self._set_audio_button_playing(button, False, _("Audio playback failed"))
            if self.active_audio is button.player:
                self.active_audio = None
                self.active_audio_button = None

    def _set_audio_button_playing(self, button, playing: bool, error: str | None = None) -> None:
        button.playing = playing
        button.set_icon_name(
            "media-playback-pause-symbolic" if playing else "audio-volume-high-symbolic"
        )
        button.set_tooltip_text(error or (_("Pause pronunciation") if playing else _("Play pronunciation")))

    def _stop_active_audio(self, error: str | None = None) -> None:
        if self.active_audio is not None:
            self.active_audio.set_state(Gst.State.NULL)
        if self.active_audio_button is not None:
            self._set_audio_button_playing(self.active_audio_button, False, error)
        self.active_audio = None
        self.active_audio_button = None

    def on_shutdown(self, *_args) -> None:
        if getattr(self, "active_audio", None) is not None:
            self._stop_active_audio()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _apply_collapsed_sections(self) -> None:
        start = self.result_buffer.get_start_iter()
        end = self.result_buffer.get_end_iter()
        self.result_buffer.remove_tag_by_name("collapsed", start, end)
        for index in self.collapsed_sections:
            section = self.definition_sections[index]
            start = self.result_buffer.get_iter_at_offset(section["content_start"])
            end = self.result_buffer.get_iter_at_offset(section["content_end"])
            self.result_buffer.apply_tag_by_name("collapsed", start, end)
        for index in self.collapsed_quotations:
            quotation = self.definition_quotations[index]
            start = self.result_buffer.get_iter_at_offset(quotation["content_start"])
            end = self.result_buffer.get_iter_at_offset(quotation["content_end"])
            self.result_buffer.apply_tag_by_name("collapsed", start, end)

    def toggle_definition_quotation(self, quotation_index: int) -> bool:
        if quotation_index in self.collapsed_quotations:
            self.collapsed_quotations.remove(quotation_index)
        else:
            self.collapsed_quotations.add(quotation_index)
        self._apply_collapsed_sections()
        quotation = self.definition_quotations[quotation_index]
        collapsed = quotation_index in self.collapsed_quotations
        quotation["icon"].set_from_icon_name(
            "pan-start-symbolic" if collapsed else "pan-down-symbolic"
        )
        quotation["button"].set_tooltip_text(
            _("Expand quotations") if collapsed else _("Collapse quotations")
        )
        return GLib.SOURCE_REMOVE

    def _set_section_disclosure(self, section_index: int) -> None:
        section = self.definition_sections[section_index]
        collapsed = section_index in self.collapsed_sections
        section["button"].set_icon_name(
            "pan-start-symbolic" if collapsed else "pan-down-symbolic"
        )
        section["button"].set_tooltip_text(
            _("Expand section") if collapsed else _("Collapse section")
        )

    def _load_resources(self) -> None:
        if getattr(self, "_resource", None):
            return
        candidates = [Path.cwd() / "build" / "webdict-resources.gresource"]
        candidates += [Path(p) / "webdict" / "webdict-resources.gresource"
                       for p in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")]
        candidates.append(Path(sys.prefix) / "share" / "webdict" / "webdict-resources.gresource")
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise RuntimeError(_("Webdict resources were not found; run `meson compile -C build` first."))
        self._resource = Gio.Resource.load(str(path))
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
        if self.active_audio is not None:
            self._stop_active_audio()
        self.suggestion_generation += 1
        if self.suggestion_timeout is not None:
            GLib.source_remove(self.suggestion_timeout)
            self.suggestion_timeout = None
        edition_name, code = EDITIONS[self.edition.get_selected()]
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
            self._render_entry(entry)
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
    quirks.urllib_honor_gnome_proxy_settings()
    return WebdictApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
