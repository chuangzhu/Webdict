import unittest
import gc
import weakref
from concurrent.futures import Future
from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gi.repository import Gio, GObject

from webdict.application import GLib, Gtk, WebdictApplication
from webdict.wiktionary import WiktionaryError


class DefinitionNavigationTests(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.app.definition_transitioning = False
        self.root = Mock(current_url="https://en.wiktionary.org/wiki/cat")
        self.app.definition_page = self.root
        self.app.definition_navigation.get_visible_page.return_value = self.root
        self.app._update_open_action = partial(WebdictApplication._update_open_action, self.app)

    def test_double_click_pushes_page_without_replacing_source_text(self):
        self.root.edition_name = "English"
        self.root.edition_code = "en"
        page = Mock()
        with patch("webdict.application.DefinitionPage", return_value=page):
            WebdictApplication.on_definition_word(self.app, self.root, "feline")
        self.app.definition_navigation.push.assert_called_once_with(page)
        self.app._lookup_definition.assert_called_once_with(page, "feline", "English", "en")
        self.root.result.render_entry.assert_not_called()
        self.app.search.set_text.assert_not_called()
        self.app.definition_navigation.replace.assert_not_called()

    def test_response_after_back_updates_only_its_own_page(self):
        page = Mock(lookup_generation=1)
        entry = SimpleNamespace(url="https://en.wiktionary.org/wiki/feline")
        future = Future()
        future.set_result(entry)
        WebdictApplication.finish_search(self.app, future, page, 1)
        page.show_entry.assert_called_once_with(entry)
        self.root.show_entry.assert_not_called()
        self.app.definition_navigation.push.assert_not_called()
        self.app.search.set_sensitive.assert_not_called()
        self.app.open_wiktionary_action.set_enabled.assert_called_with(True)

    def test_failed_lookup_shows_error_on_child_page(self):
        page = Mock(lookup_generation=1, current_url=None)
        self.app.definition_navigation.get_visible_page.return_value = page
        future = Future()
        future.set_exception(WiktionaryError("Entry unavailable"))
        WebdictApplication.finish_search(self.app, future, page, 1)
        page.show_error.assert_called_once_with("Entry unavailable")
        self.root.show_error.assert_not_called()
        self.app.open_wiktionary_action.set_enabled.assert_called_with(False)

    def test_retry_uses_page_word_and_edition(self):
        page = Mock(word="chat", edition_name="Français", edition_code="fr")
        WebdictApplication.on_definition_retry(self.app, page)
        self.app._lookup_definition.assert_called_once_with(page, "chat", "Français", "fr")

    def test_superseded_request_cannot_replace_new_result(self):
        page = Mock(lookup_generation=2)
        future = Future()
        future.set_result(SimpleNamespace(url="https://en.wiktionary.org/wiki/old"))
        WebdictApplication.finish_search(self.app, future, page, 1)
        page.show_entry.assert_not_called()
        self.app.search.set_sensitive.assert_not_called()

    def test_open_wiktionary_uses_visible_page_url(self):
        page = Mock(current_url="https://fr.wiktionary.org/wiki/chat")
        self.app.definition_navigation.get_visible_page.return_value = page
        with patch("webdict.application.Gtk.UriLauncher") as launcher:
            WebdictApplication.on_open(self.app)
        launcher.new.assert_called_once_with(page.current_url)
        launcher.new.return_value.launch.assert_called_once_with(self.app.window, None, None)

    def test_root_disables_all_inner_controllers_and_push_restores_them(self):
        bubble, capture = Mock(), Mock()
        self.app.definition_navigation_controllers = [
            (bubble, Gtk.PropagationPhase.BUBBLE),
            (capture, Gtk.PropagationPhase.CAPTURE),
        ]
        stack = self.app.definition_navigation_stack
        for count in (1, 2, 1):
            stack.get_n_items.return_value = count
            WebdictApplication._update_definition_swipes(self.app)
            bubble.set_propagation_phase.assert_called_with(
                Gtk.PropagationPhase.BUBBLE if count > 1 else Gtk.PropagationPhase.NONE,
            )
            capture.set_propagation_phase.assert_called_with(
                Gtk.PropagationPhase.CAPTURE if count > 1 else Gtk.PropagationPhase.NONE,
            )

    def test_stack_subscription_survives_setup_and_handles_real_model_changes(self):
        controller = Mock()
        controller.get_propagation_phase.return_value = Gtk.PropagationPhase.BUBBLE
        self.app.definition_navigation.observe_controllers.return_value = [controller]
        self.app._update_definition_swipes = partial(WebdictApplication._update_definition_swipes, self.app)
        self.app._on_definition_stack_changed = partial(WebdictApplication._on_definition_stack_changed, self.app)
        references = []

        def create_model():
            model = Gio.ListStore.new(GObject.Object)
            model.append(GObject.Object())
            references.append(weakref.ref(model))
            return model

        self.app.definition_navigation.get_navigation_stack.side_effect = create_model
        WebdictApplication._setup_definition_swipes(self.app)
        gc.collect()
        model = references[0]()
        self.assertIsNotNone(model)
        controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.NONE)
        model.append(GObject.Object())
        controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.BUBBLE)
        model.remove(1)
        # The stack shrinks before the transition finishes; keep handlers active.
        controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.BUBBLE)
        with patch("webdict.application.GLib.idle_add") as idle_add:
            WebdictApplication._on_definition_page_shown(self.app)
            controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.BUBBLE)
            callback = idle_add.call_args.args[0]
        self.assertEqual(callback(), GLib.SOURCE_REMOVE)
        controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.NONE)

    def test_deferred_root_update_does_not_disable_newly_pushed_page(self):
        controller = Mock()
        self.app.definition_navigation_controllers = [(controller, Gtk.PropagationPhase.BUBBLE)]
        self.app._update_definition_swipes = partial(WebdictApplication._update_definition_swipes, self.app)
        self.app.definition_navigation_stack.get_n_items.return_value = 1
        with patch("webdict.application.GLib.idle_add") as idle_add:
            WebdictApplication._on_definition_page_shown(self.app)
            callback = idle_add.call_args.args[0]
        self.app.definition_navigation_stack.get_n_items.return_value = 2
        callback()
        controller.set_propagation_phase.assert_called_once_with(Gtk.PropagationPhase.BUBBLE)

    def test_pending_idle_update_does_not_reset_controllers_during_transition(self):
        controller = Mock()
        self.app.definition_navigation_controllers = [(controller, Gtk.PropagationPhase.BUBBLE)]
        self.app.definition_navigation_stack.get_n_items.return_value = 1
        WebdictApplication._on_definition_page_showing(self.app)
        WebdictApplication._update_definition_swipes(self.app)
        controller.set_propagation_phase.assert_not_called()
        self.app.definition_transitioning = False
        WebdictApplication._update_definition_swipes(self.app)
        controller.set_propagation_phase.assert_called_once_with(Gtk.PropagationPhase.NONE)


if __name__ == "__main__":
    unittest.main()
