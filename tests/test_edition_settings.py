import os
import unittest
from unittest.mock import Mock

from gi.repository import Gio

from webdict.edition_dropdown import EDITIONS, EditionDropdown, Gtk


class EditionSettingsTests(unittest.TestCase):
    def setUp(self):
        schema_dir = os.environ["GSETTINGS_SCHEMA_DIR"]
        source = Gio.SettingsSchemaSource.new_from_directory(schema_dir, None, False)
        self.schema = source.lookup("cz.chuang.Webdict", False)
        self.backend = Gio.memory_settings_backend_new()
        self.settings = Gio.Settings.new_full(self.schema, self.backend, None)
        self.dropdown = Mock(settings=self.settings)

    def test_default_edition_is_english(self):
        EditionDropdown._restore_edition(self.dropdown)
        self.dropdown.set_selected.assert_called_once_with(0)
        self.assertEqual(self.settings.get_string("wiktionary-edition"), "en")

    def test_selection_is_saved_as_code_and_restored(self):
        self.dropdown.get_selected.return_value = 1
        self.dropdown.get_selected_edition.return_value = EDITIONS[1]
        EditionDropdown._save_edition(self.dropdown)
        # A new settings instance reads the saved code through the same backend.
        restored = Mock(settings=Gio.Settings.new_full(self.schema, self.backend, None))
        self.assertEqual(restored.settings.get_string("wiktionary-edition"), "zh")
        EditionDropdown._restore_edition(restored)
        restored.set_selected.assert_called_once_with(1)

    def test_unknown_code_falls_back_to_english(self):
        self.settings.set_string("wiktionary-edition", "unknown")
        EditionDropdown._restore_edition(self.dropdown)
        self.dropdown.set_selected.assert_called_once_with(0)

    def test_no_selection_does_not_overwrite_saved_code(self):
        self.settings.set_string("wiktionary-edition", "fr")
        self.dropdown.get_selected.return_value = Gtk.INVALID_LIST_POSITION
        EditionDropdown._save_edition(self.dropdown)
        self.assertEqual(self.settings.get_string("wiktionary-edition"), "fr")


if __name__ == "__main__":
    unittest.main()
