from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk


class NavigationSwipeWorkaround:
    """Yield root-page swipe events to the enclosing navigation container."""

    def __init__(self, view: Adw.NavigationView) -> None:
        self.view = view
        self._setup_swipes()

    def _setup_swipes(self) -> None:
        self._transitioning = False
        self._controllers = [
            (controller, controller.get_propagation_phase())
            for controller in self.view.observe_controllers()
        ]
        self._page_handlers = {}
        # Watch children before they enter the stack, including Builder pages.
        self._children = self.view.observe_children()
        self._children.connect("items-changed", self._sync_page_handlers)
        self._sync_page_handlers()
        # NavigationView holds this model weakly; retain the subscription.
        self._navigation_stack = self.view.get_navigation_stack()
        self._navigation_stack.connect("items-changed", self._on_stack_changed)
        self._update_swipes()

    def _sync_page_handlers(self, *_args) -> None:
        pages = {child for child in self._children if isinstance(child, Adw.NavigationPage)}
        for page in self._page_handlers.keys() - pages:
            for handler in self._page_handlers.pop(page):
                page.disconnect(handler)
        for page in pages - self._page_handlers.keys():
            self._page_handlers[page] = (
                page.connect("showing", self._on_page_showing),
                page.connect("shown", self._on_page_shown),
            )

    def _on_stack_changed(self, *_args) -> None:
        if self._navigation_stack.get_n_items() > 1:
            self._update_swipes()

    def _on_page_showing(self, *_args) -> None:
        self._transitioning = True

    def _on_page_shown(self, *_args) -> None:
        # Wait for the transition and swipe callback to finish before resetting
        # controllers; changing their phases during a swipe can cancel it.
        self._transitioning = False
        GLib.idle_add(self._update_swipes)

    def _update_swipes(self, *_args) -> bool:
        enabled = self._navigation_stack.get_n_items() > 1
        if not enabled and self._transitioning:
            return GLib.SOURCE_REMOVE
        for controller, phase in self._controllers:
            controller.set_propagation_phase(phase if enabled else Gtk.PropagationPhase.NONE)
        return GLib.SOURCE_REMOVE
