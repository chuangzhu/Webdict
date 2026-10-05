from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gdk, GLib, GObject, Gst, Gtk, Pango

from .i18n import _
from .wiktionary import Entry


class ResultTextView(Gtk.TextView):
    __gtype_name__ = "WebdictResultTextView"
    __gsignals__ = {
        "lookup-word": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.text_buffer = self.get_buffer()
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
        self.add_controller(definition_click)

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
        if not self.text_buffer.get_has_selection():
            return GLib.SOURCE_REMOVE
        start, end = self.text_buffer.get_selection_bounds()
        word = self.text_buffer.get_text(start, end, False).strip()
        if not word:
            return GLib.SOURCE_REMOVE
        self.emit("lookup-word", word)
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
            self.text_buffer.create_tag(name, **properties)

    def render_entry(self, entry: Entry) -> None:
        self.release_audio()
        self.text_buffer.set_text("")
        self.definition_sections = []
        self.collapsed_sections = set()
        self.definition_quotations = []
        self.collapsed_quotations = set()
        for button in self.section_buttons + self.quotation_buttons + self.audio_buttons:
            if button.get_parent() is self:
                self.remove(button)
        self.section_buttons = []
        self.quotation_buttons = []
        self.audio_buttons = []
        heading_style = None
        in_quotation = False

        def finish_heading() -> None:
            section_index = len(self.definition_sections) - 1
            section = self.definition_sections[section_index]
            self.text_buffer.insert(self.text_buffer.get_end_iter(), " ")
            anchor = self.text_buffer.create_child_anchor(self.text_buffer.get_end_iter())
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
            self.add_child_at_anchor(button, anchor)
            self.section_buttons.append(button)
            section["button"] = button
            section["heading_end"] = self.text_buffer.get_char_count()

        for run in entry.runs:
            run_heading = next((tag for tag in run.tags if tag in {"h2", "h3", "h4", "h5"}), None)
            run_quotation = "quotation" in run.tags
            if heading_style and run_heading != heading_style:
                finish_heading()
            if in_quotation and not run_quotation:
                self.definition_quotations[-1]["content_end"] = self.text_buffer.get_char_count()
            if run_heading and run_heading != heading_style:
                heading_start = self.text_buffer.get_char_count()
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
                anchor = self.text_buffer.create_child_anchor(self.text_buffer.get_end_iter())
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
                self.add_child_at_anchor(button, anchor)
                self.quotation_buttons.append(button)
                self.text_buffer.insert(self.text_buffer.get_end_iter(), "\n")
                content_start = self.text_buffer.get_char_count()
                self.text_buffer.insert(self.text_buffer.get_end_iter(), "• ")
                self.definition_quotations.append({
                    "button": button,
                    "icon": icon,
                    "content_start": content_start,
                    "content_end": 0,
                })
            if run.audio_url:
                anchor = self.text_buffer.create_child_anchor(self.text_buffer.get_end_iter())
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
                self.add_child_at_anchor(button, anchor)
                self.audio_buttons.append(button)
            position = self.text_buffer.get_end_iter()
            if run.text and run.tags:
                tags = [self.text_buffer.get_tag_table().lookup(name) for name in run.tags]
                self.text_buffer.insert_with_tags(position, run.text, *tags)
            elif run.text:
                self.text_buffer.insert(position, run.text)
            heading_style = run_heading
            in_quotation = run_quotation

        if heading_style:
            finish_heading()
        if in_quotation:
            self.definition_quotations[-1]["content_end"] = self.text_buffer.get_char_count()

        total = self.text_buffer.get_char_count()
        for index, section in enumerate(self.definition_sections):
            content_start = section["heading_end"]
            iterator = self.text_buffer.get_iter_at_offset(content_start)
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
            self.stop_audio()
        self.active_audio = button.player
        self.active_audio_button = button
        result = button.player.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            self.stop_audio(_("Audio playback failed"))
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

    def stop_audio(self, error: str | None = None) -> None:
        if self.active_audio is not None:
            self.active_audio.set_state(Gst.State.NULL)
        if self.active_audio_button is not None:
            self._set_audio_button_playing(self.active_audio_button, False, error)
        self.active_audio = None
        self.active_audio_button = None

    def release_audio(self) -> None:
        self.stop_audio()
        for button in self.audio_buttons:
            if button.player is not None:
                button.player.set_state(Gst.State.NULL)
                button.bus.remove_signal_watch()
                self._set_audio_button_playing(button, False)
                button.player = None
                button.bus = None

    def _apply_collapsed_sections(self) -> None:
        start = self.text_buffer.get_start_iter()
        end = self.text_buffer.get_end_iter()
        self.text_buffer.remove_tag_by_name("collapsed", start, end)
        for index in self.collapsed_sections:
            section = self.definition_sections[index]
            start = self.text_buffer.get_iter_at_offset(section["content_start"])
            end = self.text_buffer.get_iter_at_offset(section["content_end"])
            self.text_buffer.apply_tag_by_name("collapsed", start, end)
        for index in self.collapsed_quotations:
            quotation = self.definition_quotations[index]
            start = self.text_buffer.get_iter_at_offset(quotation["content_start"])
            end = self.text_buffer.get_iter_at_offset(quotation["content_end"])
            self.text_buffer.apply_tag_by_name("collapsed", start, end)

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
