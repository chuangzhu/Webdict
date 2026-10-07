import unittest
from concurrent.futures import Future
from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock, patch

from webdict.application import WebdictApplication
from webdict.wiktionary import WiktionaryError


class DefinitionNavigationTests(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.root = Mock(current_url="https://en.wiktionary.org/wiki/cat")
        self.app.definition_page = self.root
        self.app.definition_navigation.get_visible_page.return_value = self.root
        self.app._update_open_action = partial(WebdictApplication._update_open_action, self.app)

    def test_lookup_pushes_page_without_replacing_source_text(self):
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


if __name__ == "__main__":
    unittest.main()
