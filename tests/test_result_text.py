import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from gi.repository import GLib, Gtk

from webdict.result_text import ResultTextView


class ResultTextMenuTests(unittest.TestCase):
    def setUp(self):
        self.view = SimpleNamespace(
            text_buffer=Gtk.TextBuffer(),
            insert_action_group=Mock(),
            set_extra_menu=Mock(),
            emit=Mock(),
        )
        self.view.lookup_selected_definition_word = lambda *args: ResultTextView.lookup_selected_definition_word(self.view, *args)
        self.view._update_lookup_action = lambda *args: ResultTextView._update_lookup_action(self.view, *args)
        ResultTextView._create_lookup_menu(self.view)

    def test_menu_has_touch_icon_and_selection_action(self):
        menu = self.view.set_extra_menu.call_args.args[0]
        self.assertEqual(menu.get_n_items(), 1)
        for name, expected in (
            ("action", "definition.lookup"),
            ("touch-icon", "system-search-symbolic"),
        ):
            self.assertEqual(menu.get_item_attribute_value(0, name, GLib.VariantType.new("s")).get_string(), expected)
        prefix, actions = self.view.insert_action_group.call_args.args
        self.assertEqual(prefix, "definition")
        self.assertIs(actions.lookup_action("lookup"), self.view.lookup_action)

    def test_action_looks_up_trimmed_selection_and_disables_when_cleared(self):
        buffer = self.view.text_buffer
        buffer.set_text(" feline ")
        self.assertFalse(self.view.lookup_action.get_enabled())
        buffer.select_range(buffer.get_start_iter(), buffer.get_end_iter())
        self.assertTrue(self.view.lookup_action.get_enabled())
        self.view.lookup_action.activate(None)
        self.view.emit.assert_called_once_with("lookup-word", "feline")
        buffer.place_cursor(buffer.get_start_iter())
        self.assertFalse(self.view.lookup_action.get_enabled())

    def test_whitespace_selection_does_not_look_up(self):
        buffer = self.view.text_buffer
        buffer.set_text("  ")
        buffer.select_range(buffer.get_start_iter(), buffer.get_end_iter())
        self.view.lookup_action.activate(None)
        self.view.emit.assert_not_called()


class FindInPageTests(unittest.TestCase):
    def setUp(self):
        self.view = SimpleNamespace(text_buffer=Gtk.TextBuffer(), scroll_to_iter=Mock())
        self.view.text_buffer.set_text("Cat dog cat")

    def find(self, query="cat", **kwargs):
        return ResultTextView.find_text(self.view, query, **kwargs)

    def selection(self):
        return tuple(i.get_offset() for i in self.view.text_buffer.get_selection_bounds())

    def test_case_insensitive_next_previous_and_wrap(self):
        self.assertTrue(self.find(restart=True))
        self.assertEqual(self.selection(), (0, 3))
        self.assertTrue(self.find())
        self.assertEqual(self.selection(), (8, 11))
        self.assertTrue(self.find())
        self.assertEqual(self.selection(), (0, 3))
        self.assertTrue(self.find(backwards=True))
        self.assertEqual(self.selection(), (8, 11))
        self.assertTrue(self.find(backwards=True))
        self.assertEqual(self.selection(), (0, 3))

    def test_restart_searches_from_beginning(self):
        self.find("dog", restart=True)
        self.assertTrue(self.find(restart=True))
        self.assertEqual(self.selection(), (0, 3))

    def test_missing_and_empty_queries_do_not_scroll(self):
        self.assertFalse(self.find("missing"))
        self.assertFalse(self.find(""))
        self.view.scroll_to_iter.assert_not_called()

    def test_collapsed_text_is_skipped(self):
        buffer = self.view.text_buffer
        tag = buffer.create_tag("hidden", invisible=True)
        buffer.apply_tag(tag, buffer.get_start_iter(), buffer.get_iter_at_offset(3))
        self.assertTrue(self.find(restart=True))
        self.assertEqual(self.selection(), (8, 11))

    def test_unicode_match_uses_buffer_offsets(self):
        self.view.text_buffer.set_text("猫 café CAFÉ")
        self.assertTrue(self.find("café", restart=True))
        self.assertEqual(self.selection(), (2, 6))
        self.assertTrue(self.find("café"))
        self.assertEqual(self.selection(), (7, 11))
