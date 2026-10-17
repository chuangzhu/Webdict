"""Continuous horizontal sheet collapse using libadwaita's swipe tracker."""

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk


class _SheetLayout(Gtk.LayoutManager):
    def do_measure(self, widget, orientation, for_size):
        return widget.get_child().measure(orientation, for_size)

    def do_allocate(self, widget, width, height, baseline):
        # Extend below the clipped viewport to move the sheet downward.
        offset = round(widget.progress * widget.collapse_distance)
        widget.get_child().allocate(width, height + offset, baseline, None)


class _PageLayout(Gtk.LayoutManager):
    def __init__(self, viewport):
        super().__init__()
        self.viewport = viewport

    def do_measure(self, widget, orientation, for_size):
        return widget.get_child().measure(orientation, for_size)

    def do_allocate(self, widget, width, height, baseline):
        # Keep the page's allocation fixed while the enclosing sheet extends.
        widget.get_child().allocate(width, self.viewport.get_height(), baseline, None)


class SwipeBar(Adw.Bin, Adw.Swipeable):
    """Progress 0 is expanded; 1 collapses into the native bottom bar."""

    def __init__(self, sheet):
        super().__init__()
        self.sheet = sheet
        self.navigation = None
        self.layouts = None
        self._root_transitioning = False
        self.progress = 0.0
        self.collapse_distance = 0
        self.gesture_active = False
        self.set_child(sheet)
        self.set_layout_manager(_SheetLayout())
        self.set_overflow(Gtk.Overflow.HIDDEN)

        target = Adw.CallbackAnimationTarget.new(self._set_progress)
        self.animation = Adw.SpringAnimation.new(
            self, 0, 0, Adw.SpringParams.new(1, 1, 500), target
        )
        self.animation.set_clamp(True)
        self.animation.connect("done", self._settled)
        self.tracker = Adw.SwipeTracker.new(self)
        self.tracker.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.tracker.set_reversed(True)
        self.tracker.set_allow_mouse_drag(True)
        # Capture horizontal input before BottomSheet's vertical tracker.
        # Disable the separate drag controller meant for window handles.
        controllers = self.observe_controllers()
        self._input_controllers = []
        for i in range(controllers.get_n_items()):
            controller = controllers.get_item(i)
            if isinstance(controller, Gtk.GestureDrag):
                ordinary = controller.get_propagation_phase() == Gtk.PropagationPhase.BUBBLE
                self._input_controllers.append((controller, ordinary))
            elif isinstance(controller, Gtk.EventControllerScroll):
                self._input_controllers.append((controller, True))
        self.tracker.connect("notify::enabled", self._route_input)
        self._route_input()
        self.tracker.connect("begin-swipe", self._begin_swipe)
        self.tracker.connect("update-swipe", self._update_swipe)
        self.tracker.connect("end-swipe", self._end_swipe)
        sheet.connect("notify::open", self._open_changed)
        self._open_changed(sheet, None)

    def watch_navigation(self, navigation, layouts):
        self.navigation = navigation
        self.layouts = layouts
        # NavigationView retains this model weakly.
        self._stack = navigation.get_navigation_stack()
        self._stack.connect("items-changed", self._sync_enabled)
        root = self._stack.get_item(0)
        root.connect("showing", self._root_showing)
        root.connect("shown", self._root_shown)
        layouts.connect("notify::layout-name", self._sync_enabled)
        self._sync_enabled()

    def _root_showing(self, *_args):
        self._root_transitioning = True
        self._sync_enabled()

    def _root_shown(self, *_args):
        self._root_transitioning = False
        # Let the navigation swipe finish before capturing new input.
        GLib.idle_add(self._sync_enabled)

    def _sync_enabled(self, *_args):
        enabled = self.sheet.get_open()
        if self.navigation is not None:
            enabled = (enabled and self.layouts.get_layout_name() == "narrow"
                       and self._stack.get_n_items() == 1 and not self._root_transitioning)
        self.tracker.set_enabled(enabled)
        if not enabled:
            self.gesture_active = False
            self.restore()
        return GLib.SOURCE_REMOVE

    def _route_input(self, *_args):
        for controller, ordinary in self._input_controllers:
            phase = (Gtk.PropagationPhase.CAPTURE
                     if ordinary and self.tracker.get_enabled()
                     else Gtk.PropagationPhase.NONE)
            controller.set_propagation_phase(phase)

    def set_page(self, page):
        frame = Adw.Bin(child=page)
        frame.set_layout_manager(_PageLayout(self))
        self.sheet.set_content(frame)

    def _set_progress(self, value):
        self.progress = max(0.0, min(1.0, value))
        self.queue_allocate()

    def _begin_swipe(self, _tracker):
        self.animation.pause()
        if self.progress == 0:
            self.collapse_distance = max(
                0, self.sheet.get_sheet_height() - self.sheet.get_bottom_bar_height()
            )
        self.gesture_active = True

    def _update_swipe(self, _tracker, progress):
        self._set_progress(progress)

    def _end_swipe(self, _tracker, velocity, destination):
        # SwipeTracker also emits end-swipe when a pending gesture is rejected.
        if not self.gesture_active:
            return
        self.gesture_active = False
        self.animation.set_value_from(self.progress)
        self.animation.set_value_to(destination)
        self.animation.set_initial_velocity(velocity)
        self.animation.play()

    def restore(self):
        self.animation.pause()
        self._set_progress(0)

    def _open_changed(self, sheet, _pspec):
        self.gesture_active = False
        self.restore()
        self._sync_enabled()

    def _settled(self, _animation):
        if self.progress < 1 or not self.sheet.get_open():
            return
        # Commit while unmapped to skip a second native closing animation.
        # Hide/show are synchronous, so no hidden frame is drawn.
        self.sheet.set_visible(False)
        try:
            self.sheet.set_open(False)
        finally:
            self.sheet.set_visible(True)
        self.sheet.child_focus(Gtk.DirectionType.TAB_FORWARD)

    def do_get_distance(self):
        return max(1, self.get_width())

    def do_get_progress(self):
        return self.progress

    def do_get_cancel_progress(self):
        return float(self.progress >= 0.5)

    def do_get_snap_points(self):
        # The Python vfunc must return the array AND its out-parameter length.
        return [0.0, 1.0], 2

    def do_get_swipe_area(self, _direction, _is_drag):
        rect = Gdk.Rectangle()
        rect.x = rect.y = rect.width = rect.height = 0
        if not self.sheet.get_open():
            return rect
        # A stationary hit area allows re-grabbing during the animation.
        rect.width = self.get_width()
        rect.height = self.get_height()
        return rect
