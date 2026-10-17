"""Display-independent checks for dismissal geometry and spring handoff."""

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from webdict.swipe_bar import SwipeBar, _PageLayout, _SheetLayout
from gi.repository import Adw, GObject, Gtk


class SwipeBarTests(unittest.TestCase):
    def test_native_snap_points_callback_returns_array_and_count(self):
        """Exercise the C-to-Python vfunc boundary, not just the Python method.

        This callback does not use its instance, so a plain GObject lets us
        check the real registered trampoline without requiring a display.
        """
        class SwipeableInterface(ctypes.Structure):
            _fields_ = [
                ("interface_type", ctypes.c_size_t),
                ("instance_type", ctypes.c_size_t),
                ("get_distance", ctypes.c_void_p),
                ("get_snap_points", ctypes.c_void_p),
            ]

        gobject = ctypes.CDLL("libgobject-2.0.so.0")
        glib = ctypes.CDLL("libglib-2.0.so.0")
        gobject.g_type_class_ref.argtypes = [ctypes.c_size_t]
        gobject.g_type_class_ref.restype = ctypes.c_void_p
        gobject.g_type_class_unref.argtypes = [ctypes.c_void_p]
        gobject.g_type_interface_peek.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        gobject.g_type_interface_peek.restype = ctypes.POINTER(SwipeableInterface)
        glib.g_free.argtypes = [ctypes.c_void_p]

        klass = gobject.g_type_class_ref(hash(SwipeBar.__gtype__))
        points = None
        try:
            interface = gobject.g_type_interface_peek(klass, hash(Adw.Swipeable.__gtype__))
            callback_type = ctypes.CFUNCTYPE(
                ctypes.POINTER(ctypes.c_double), ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int),
            )
            callback = callback_type(interface.contents.get_snap_points)
            instance = GObject.Object()
            count = ctypes.c_int(-1)
            points = callback(hash(instance), ctypes.byref(count))
            self.assertEqual(count.value, 2)
            self.assertTrue(points)
            self.assertEqual([points[i] for i in range(count.value)], [0.0, 1.0])
        finally:
            if points:
                glib.g_free(points)
            gobject.g_type_class_unref(klass)

    def test_swipe_area_covers_open_sheet_and_page_only_while_open(self):
        state = Mock()
        state.progress = 0.5
        state.sheet.get_open.return_value = True
        state.get_height.return_value = 600
        state.get_width.return_value = 480
        for drag in (True, False):
            rect = SwipeBar.do_get_swipe_area(state, None, drag)
            self.assertEqual((rect.x, rect.y, rect.width, rect.height), (0, 0, 480, 600))
        state.progress = 1
        self.assertEqual(SwipeBar.do_get_swipe_area(state, None, True).height, 600)
        state.sheet.get_open.return_value = False
        self.assertEqual(SwipeBar.do_get_swipe_area(state, None, True).height, 0)

    def test_retraction_keeps_page_height(self):
        child = Mock()
        widget = Mock()
        widget.get_child.return_value = child
        widget.sheet.get_bottom_bar_height.return_value = 64
        widget.collapse_distance = 320
        for progress, height in [(0, 600), (0.25, 680), (0.5, 760), (1, 920)]:
            widget.progress = progress
            _SheetLayout.do_allocate(None, widget, 480, 600, -1)
            child.allocate.assert_called_with(480, height, -1, None)
            viewport = Mock()
            viewport.get_height.return_value = 600
            _PageLayout.do_allocate(SimpleNamespace(viewport=viewport), widget,
                                    480, height, -1)
            child.allocate.assert_called_with(480, 600, -1, None)

    def test_interrupt_and_reverse_from_current_position(self):
        state = SimpleNamespace(animation=Mock(), progress=0.63)
        SwipeBar._begin_swipe(state, None)
        state.animation.pause.assert_called_once()
        self.assertEqual(state.progress, 0.63)
        SwipeBar._end_swipe(state, None, -1.8, 0.0)
        state.animation.set_value_from.assert_called_once_with(0.63)
        state.animation.set_value_to.assert_called_once_with(0.0)
        state.animation.set_initial_velocity.assert_called_once_with(-1.8)
        state.animation.play.assert_called_once()
        state.animation.reset.assert_not_called()

    def test_pending_gesture_does_not_start_a_spring(self):
        state = SimpleNamespace(animation=Mock(), gesture_active=False)
        SwipeBar._end_swipe(state, None, 0, 0)
        state.animation.play.assert_not_called()

    def test_open_state_enables_horizontal_collapse(self):
        state = Mock()
        for opened in (True, False):
            state.sheet.get_open.return_value = opened
            SwipeBar._open_changed(state, state.sheet, None)
            state._sync_enabled.assert_called()
            self.assertFalse(state.gesture_active)

    def test_capture_routing_is_restored_after_tracker_enable(self):
        ordinary, handle, scroll = Mock(), Mock(), Mock()
        state = SimpleNamespace(
            tracker=Mock(),
            _input_controllers=[(ordinary, True), (handle, False), (scroll, True)],
        )
        for enabled in (False, True):
            state.tracker.get_enabled.return_value = enabled
            SwipeBar._route_input(state)
            expected = Gtk.PropagationPhase.CAPTURE if enabled else Gtk.PropagationPhase.NONE
            ordinary.set_propagation_phase.assert_called_with(expected)
            scroll.set_propagation_phase.assert_called_with(expected)
            handle.set_propagation_phase.assert_called_with(Gtk.PropagationPhase.NONE)

    def test_commit_hides_only_during_native_state_change(self):
        state = SimpleNamespace(progress=1, sheet=Mock())
        state.sheet.get_open.return_value = True
        SwipeBar._settled(state, None)
        calls = state.sheet.mock_calls
        from unittest.mock import call
        self.assertLess(calls.index(call.set_visible(False)), calls.index(call.set_open(False)))
        self.assertLess(calls.index(call.set_open(False)), calls.index(call.set_visible(True)))

    def test_progress_is_bounded_and_cancellation_uses_nearest_endpoint(self):
        state = SimpleNamespace(progress=0, queue_allocate=Mock())
        for value, expected in [(-0.2, 0), (0.4, 0.4), (1.2, 1)]:
            SwipeBar._set_progress(state, value)
            self.assertEqual(state.progress, expected)
            self.assertEqual(SwipeBar.do_get_cancel_progress(state),
                             float(expected >= 0.5))


if __name__ == "__main__":
    unittest.main()


class NavigationGatingTests(unittest.TestCase):
    def test_only_open_narrow_single_page_can_close(self):
        state = SimpleNamespace(sheet=Mock(), navigation=Mock(), layouts=Mock(),
                                _stack=Mock(), tracker=Mock(), restore=Mock(),
                                gesture_active=True, _root_transitioning=False)
        for opened, layout, pages, transitioning, expected in (
            (True, 'narrow', 1, False, True),
            (False, 'narrow', 1, False, False),
            (True, 'wide', 1, False, False),
            (True, 'narrow', 2, False, False),
            (True, 'narrow', 1, True, False),
        ):
            state.sheet.get_open.return_value = opened
            state.layouts.get_layout_name.return_value = layout
            state._stack.get_n_items.return_value = pages
            state._root_transitioning = transitioning
            state.restore.reset_mock()
            SwipeBar._sync_enabled(state)
            state.tracker.set_enabled.assert_called_with(expected)
            self.assertEqual(state.restore.called, not expected)
