import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from webdict.wiktionary import _ReadableHTML
from webdict.result_text import ResultTextView
from webdict.definition_page import DefinitionPage
from gi.repository import Gtk


class LinkTests(unittest.TestCase):
    def test_parser_preserves_targets_across_formatting_and_trimming(self):
        reader = _ReadableHTML()
        reader.feed('<a href="/wiki/cat"> cat <b>animal</b></a><a href="/wiki/dog">dog </a>')
        runs = reader.rich_text()
        self.assertEqual([run.href for run in runs], ['/wiki/cat', '/wiki/cat', '/wiki/dog'])
        self.assertEqual(runs[-1].text, 'dog')
        self.assertIn('bold', runs[1].tags)

    def test_adjacent_links_with_different_targets_do_not_merge(self):
        reader = _ReadableHTML()
        reader.feed('<a href="/wiki/a">a</a><a href="/wiki/b">b</a> plain')
        self.assertEqual([run.href for run in reader.rich_text()], ['/wiki/a', '/wiki/b', None])

    def test_link_lookup_and_selection_guard(self):
        buffer = Gtk.TextBuffer()
        buffer.set_text('cat')
        tag = buffer.create_tag(None)
        buffer.apply_tag(tag, buffer.get_start_iter(), buffer.get_end_iter())
        view = SimpleNamespace(text_buffer=buffer, link_tags={tag: '/wiki/cat'},
                               _link_at_pointer=Mock(return_value='/wiki/cat'), emit=Mock())
        self.assertEqual(ResultTextView._link_at_iter(view, buffer.get_start_iter()), '/wiki/cat')
        ResultTextView._on_link_released(view, None, 1, 0, 0)
        view.emit.assert_called_once_with('activate-link', '/wiki/cat')
        view.emit.reset_mock()
        buffer.select_range(buffer.get_start_iter(), buffer.get_end_iter())
        ResultTextView._on_link_released(view, None, 1, 0, 0)
        view.emit.assert_not_called()

    def test_entry_target_is_decoded_for_in_app_lookup(self):
        page = SimpleNamespace(current_url='https://fr.wiktionary.org/wiki/chat', emit=Mock())
        DefinitionPage._on_activate_link(page, None, '/wiki/caf%C3%A9_au_lait#French')
        page.emit.assert_called_once_with('lookup-word', 'café au lait')

    def test_external_and_namespace_links_prompt_before_browser(self):
        page = SimpleNamespace(current_url='https://en.wiktionary.org/wiki/cat', emit=Mock(),
                               confirm_open_browser=Mock())
        DefinitionPage._on_activate_link(page, None, '//example.org/example')
        page.confirm_open_browser.assert_called_with('https://example.org/example')
        DefinitionPage._on_activate_link(page, None, '/wiki/Help:Contents')
        page.confirm_open_browser.assert_called_with('https://en.wiktionary.org/wiki/Help:Contents')
        page.emit.assert_not_called()

    def test_browser_launch_requires_explicit_open_response(self):
        page = SimpleNamespace(get_root=Mock())
        url = 'https://example.org/example?a=1&b=2'
        with patch('webdict.definition_page.Adw.AlertDialog') as alert, \
                patch('webdict.definition_page.Gtk.UriLauncher') as launcher:
            DefinitionPage.confirm_open_browser(page, url)
            alert.assert_called_once_with(heading='Open in Browser?', body=url)
            dialog = alert.return_value
            dialog.set_default_response.assert_called_once_with('cancel')
            dialog.set_close_response.assert_called_once_with('cancel')
            dialog.present.assert_called_once_with(page.get_root.return_value)
            launcher.new.assert_not_called()
            _signal, response = dialog.connect.call_args.args
            response(dialog, 'cancel')
            launcher.new.assert_not_called()
            response(dialog, 'open')
            launcher.new.assert_called_once_with(url)
            launcher.new.return_value.launch.assert_called_once_with(page.get_root.return_value, None, None)

    def test_non_web_targets_are_ignored(self):
        page = SimpleNamespace(current_url='https://en.wiktionary.org/wiki/cat', emit=Mock())
        with patch('webdict.definition_page.Gtk.UriLauncher') as launcher:
            DefinitionPage._on_activate_link(page, None, 'javascript:alert(1)')
            launcher.new.assert_not_called()
        page.emit.assert_not_called()
