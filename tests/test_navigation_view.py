import gc
import unittest
import weakref
from functools import partial
from unittest.mock import MagicMock, Mock, patch

from gi.repository import Gio, GObject

from webdict.navigation_view import Adw, GLib, Gtk, NavigationSwipeWorkaround


class NavigationSwipeWorkaroundTests(unittest.TestCase):
    def setUp(self):
        self.view = Mock()
        self.view._transitioning = False
        self.view.view.observe_children.return_value = MagicMock()
        self.view.view.observe_children.return_value.__iter__.return_value = []
        self.view._sync_page_handlers = partial(NavigationSwipeWorkaround._sync_page_handlers, self.view)

    def test_root_disables_all_inner_controllers_and_push_restores_them(self):
        bubble, capture = Mock(), Mock()
        self.view._controllers = [
            (bubble, Gtk.PropagationPhase.BUBBLE),
            (capture, Gtk.PropagationPhase.CAPTURE),
        ]
        stack = self.view._navigation_stack
        for count in (1, 2, 1):
            stack.get_n_items.return_value = count
            NavigationSwipeWorkaround._update_swipes(self.view)
            bubble.set_propagation_phase.assert_called_with(
                Gtk.PropagationPhase.BUBBLE if count > 1 else Gtk.PropagationPhase.NONE,
            )
            capture.set_propagation_phase.assert_called_with(
                Gtk.PropagationPhase.CAPTURE if count > 1 else Gtk.PropagationPhase.NONE,
            )

    def test_stack_subscription_survives_setup_and_handles_real_model_changes(self):
        controller = Mock()
        controller.get_propagation_phase.return_value = Gtk.PropagationPhase.BUBBLE
        self.view.view.observe_controllers.return_value = [controller]
        self.view._update_swipes = partial(NavigationSwipeWorkaround._update_swipes, self.view)
        self.view._on_stack_changed = partial(NavigationSwipeWorkaround._on_stack_changed, self.view)
        references = []

        def create_model():
            model = Gio.ListStore.new(GObject.Object)
            model.append(GObject.Object())
            references.append(weakref.ref(model))
            return model

        self.view.view.get_navigation_stack.side_effect = create_model
        NavigationSwipeWorkaround._setup_swipes(self.view)
        gc.collect()
        model = references[0]()
        self.assertIsNotNone(model)
        controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.NONE)
        model.append(GObject.Object())
        controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.BUBBLE)
        model.remove(1)
        # The stack shrinks before the transition finishes; keep handlers active.
        controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.BUBBLE)
        with patch("webdict.navigation_view.GLib.idle_add") as idle_add:
            NavigationSwipeWorkaround._on_page_shown(self.view)
            controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.BUBBLE)
            callback = idle_add.call_args.args[0]
        self.assertEqual(callback(), GLib.SOURCE_REMOVE)
        controller.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.NONE)

    def test_deferred_root_update_does_not_disable_newly_pushed_page(self):
        controller = Mock()
        self.view._controllers = [(controller, Gtk.PropagationPhase.BUBBLE)]
        self.view._update_swipes = partial(NavigationSwipeWorkaround._update_swipes, self.view)
        self.view._navigation_stack.get_n_items.return_value = 1
        with patch("webdict.navigation_view.GLib.idle_add") as idle_add:
            NavigationSwipeWorkaround._on_page_shown(self.view)
            callback = idle_add.call_args.args[0]
        self.view._navigation_stack.get_n_items.return_value = 2
        callback()
        controller.set_propagation_phase.assert_called_once_with(Gtk.PropagationPhase.BUBBLE)

    def test_pending_idle_update_does_not_reset_controllers_during_transition(self):
        controller = Mock()
        self.view._controllers = [(controller, Gtk.PropagationPhase.BUBBLE)]
        self.view._navigation_stack.get_n_items.return_value = 1
        NavigationSwipeWorkaround._on_page_showing(self.view)
        NavigationSwipeWorkaround._update_swipes(self.view)
        controller.set_propagation_phase.assert_not_called()
        self.view._transitioning = False
        NavigationSwipeWorkaround._update_swipes(self.view)
        controller.set_propagation_phase.assert_called_once_with(Gtk.PropagationPhase.NONE)

    def test_added_pages_are_watched_once_and_removed_pages_are_disconnected(self):
        page = Mock(spec=Adw.NavigationPage)
        page.connect.side_effect = [11, 12]
        self.view._children = MagicMock()
        self.view._children.__iter__.return_value = [page]
        self.view._page_handlers = {}
        NavigationSwipeWorkaround._sync_page_handlers(self.view)
        page.connect.assert_any_call("showing", self.view._on_page_showing)
        page.connect.assert_any_call("shown", self.view._on_page_shown)
        NavigationSwipeWorkaround._sync_page_handlers(self.view)
        self.assertEqual(page.connect.call_count, 2)
        self.view._children.__iter__.return_value = []
        NavigationSwipeWorkaround._sync_page_handlers(self.view)
        page.disconnect.assert_any_call(11)
        page.disconnect.assert_any_call(12)
        self.assertFalse(self.view._page_handlers)


if __name__ == "__main__":
    unittest.main()
