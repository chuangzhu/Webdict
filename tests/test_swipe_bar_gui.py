"""Real-widget layout/animation integration test; requires a desktop display.

This sends tracker signals, not synthetic device input. Device event routing
still needs a touchscreen/touchpad check. Run with python3 -m unittest -v.
"""

import time
import unittest

from webdict.swipe_bar import SwipeBar
from gi.repository import Adw, Gdk, GLib, Gtk


def wait_until(predicate, timeout=3):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Timed out waiting for GTK layout/animation")


class SwipeBarGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gtk.init()
        if Gdk.Display.get_default() is None:
            raise unittest.SkipTest("No graphical display available")
        Adw.init()

    def test_expanded_sheet_collapse_interrupt_and_commit(self):
        sheet = Adw.BottomSheet()
        sheet.set_sheet(Gtk.Box(width_request=300, height_request=260))
        sheet.set_bottom_bar(Gtk.Label(label="Open", height_request=48))
        wrapper = SwipeBar(sheet)
        page = Gtk.Box()
        wrapper.set_page(page)
        window = Gtk.Window(default_width=480, default_height=600, child=wrapper)
        try:
            window.present()
            wait_until(lambda: wrapper.get_mapped() and sheet.get_bottom_bar_height() > 0)
            self.assertFalse(wrapper.tracker.get_enabled())
            sheet.set_open(True)
            wait_until(lambda: abs(Adw.Swipeable.get_progress(sheet) - 1) < 0.0001)
            self.assertTrue(wrapper.tracker.get_enabled())
            self.assertEqual(Adw.Swipeable.get_snap_points(wrapper), [0.0, 1.0])
            for controller, ordinary in wrapper._input_controllers:
                self.assertEqual(controller.get_propagation_phase(),
                                 Gtk.PropagationPhase.CAPTURE if ordinary else Gtk.PropagationPhase.NONE)

            valid, initial = sheet.get_sheet().compute_bounds(wrapper)
            self.assertTrue(valid)
            valid, page_before = page.compute_bounds(wrapper)
            self.assertTrue(valid)
            wrapper.tracker.emit("begin-swipe")
            wrapper.tracker.emit("update-swipe", 0.5)
            offset = round(wrapper.collapse_distance * 0.5)
            wait_until(lambda: sheet.get_height() == wrapper.get_height() + offset)
            _, moved = sheet.get_sheet().compute_bounds(wrapper)
            _, page_after = page.compute_bounds(wrapper)
            self.assertAlmostEqual(moved.get_y() - initial.get_y(), offset, delta=1)
            self.assertEqual(page_after.get_height(), page_before.get_height())
            self.assertEqual(page_after.get_y(), page_before.get_y())

            wrapper.tracker.emit("end-swipe", 0.0, 0.0)
            if wrapper.animation.get_state() == Adw.AnimationState.PLAYING:
                wait_until(lambda: wrapper.progress < 0.45)
                current = wrapper.progress
                wrapper.tracker.emit("begin-swipe")
                self.assertAlmostEqual(wrapper.progress, current)
                self.assertEqual(wrapper.animation.get_state(), Adw.AnimationState.PAUSED)
            else:
                wrapper.tracker.emit("begin-swipe")
            wrapper.tracker.emit("update-swipe", 0.6)
            wrapper.tracker.emit("end-swipe", 1.0, 1.0)
            wait_until(lambda: not sheet.get_open() and wrapper.progress == 0)
            wait_until(lambda: sheet.get_height() == wrapper.get_height())
            self.assertTrue(sheet.get_visible())
            self.assertFalse(wrapper.tracker.get_enabled())
            self.assertAlmostEqual(Adw.Swipeable.get_progress(sheet), 0)
            sheet.set_open(True)
            self.assertTrue(wrapper.tracker.get_enabled())
        finally:
            window.destroy()
