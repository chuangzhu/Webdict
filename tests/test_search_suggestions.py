import unittest
from concurrent.futures import Future
from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock, patch

from webdict.application import WebdictApplication
from webdict.wiktionary import lookup, search_suggestions


class SearchSuggestionsTests(unittest.TestCase):
    def setUp(self):
        # Drive timers and futures explicitly so each ordering is deterministic.
        self.app = Mock()
        self.app.search.get_text.return_value = "cat"
        self.app.edition.get_selected_edition.return_value = ("English", "en")
        self.app.active_audio = None
        self.app.suggestion_timeout = None
        self.app.suggestion_generation = 0
        self.app.suggestion_list.get_row_at_index.return_value = None
        for name in ("request_suggestions", "finish_suggestions", "finish_search"):
            setattr(self.app, name, partial(getattr(WebdictApplication, name), self.app))
        self.requests = []

        def submit(function, *args):
            future = Future()
            self.requests.append((function, args, future))
            return future

        self.app.executor.submit.side_effect = submit
        self.timeout_add = self.enterContext(patch("webdict.application.GLib.timeout_add", return_value=42))
        self.source_remove = self.enterContext(patch("webdict.application.GLib.source_remove"))
        self.enterContext(patch("webdict.application.GLib.idle_add", side_effect=lambda callback, *args: callback(*args)))
        self.enterContext(patch("webdict.application.Gtk.Label"))
        self.enterContext(patch("webdict.application.Gtk.ListBoxRow"))

    def change_text(self, text):
        self.app.search.get_text.return_value = text
        WebdictApplication.on_search_changed(self.app)

    def fire_debounce(self):
        _delay, callback, generation = self.timeout_add.call_args.args
        callback(generation)
        function, _args, future = self.requests[-1]
        self.assertIs(function, search_suggestions)
        return future

    def press_enter_and_finish_definition(self):
        WebdictApplication.on_search(self.app)
        function, _args, future = self.requests[-1]
        self.assertIs(function, lookup)
        future.set_result(SimpleNamespace(url="https://en.wiktionary.org/wiki/cat"))
        self.app.stack.set_visible_child_name.assert_called_with("result")

    def test_enter_during_debounce_preserves_suggestion_request(self):
        self.change_text("cat")
        self.press_enter_and_finish_definition()
        self.source_remove.assert_not_called()
        self.assertEqual(self.app.suggestion_timeout, 42)
        self.fire_debounce().set_result(("cat", "caterpillar"))
        self.app.suggestion_stack.set_visible_child_name.assert_called_with("suggestions")
        self.assertEqual(self.app.suggestion_list.append.call_count, 2)

    def test_enter_during_request_allows_suggestions_to_finish(self):
        self.change_text("cat")
        future = self.fire_debounce()
        self.app.suggestion_stack.set_visible_child_name.assert_called_with("loading")
        self.press_enter_and_finish_definition()
        future.set_result(("cat",))
        self.app.suggestion_stack.set_visible_child_name.assert_called_with("suggestions")

    def test_debounce_replaces_pending_timer(self):
        self.change_text("ca")
        self.change_text("cat")
        self.source_remove.assert_called_once_with(42)
        self.assertEqual(self.app.suggestion_generation, 2)
        self.fire_debounce()
        self.assertEqual(self.requests[-1][1], ("cat", "en"))

    def test_old_response_does_not_replace_new_suggestions(self):
        self.change_text("ca")
        old_future = self.fire_debounce()
        self.change_text("cat")
        self.fire_debounce().set_result(("cat",))
        self.app.suggestion_stack.set_visible_child_name.reset_mock()
        old_future.set_result(("car",))
        self.app.suggestion_stack.set_visible_child_name.assert_not_called()
        self.assertEqual(self.app.suggestion_list.append.call_count, 1)

    def test_request_failure_stops_spinner(self):
        self.change_text("cat")
        self.fire_debounce().set_exception(RuntimeError("network failed"))
        self.app.suggestion_stack.set_visible_child_name.assert_called_with("empty")


if __name__ == "__main__":
    unittest.main()
