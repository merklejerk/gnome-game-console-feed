from dataclasses import replace

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from game_console_feed.background import (  # noqa: E402
    MAX_GLOW_PERCENT,
    BackgroundMode,
    BackgroundSettings,
    GlowSettings,
    VideoBackground,
)
from game_console_feed.config import load_config, save_config  # noqa: E402
from game_console_feed.discovery import get_matching_alsa_device, get_video_devices  # noqa: E402
from game_console_feed.pipeline import PipelineManager  # noqa: E402

UNITY_VOLUME = 1.0  # GStreamer uses a gain factor, with 1.0 meaning 100%.
MAX_VOLUME = 2.0
VOLUME_STEP = 0.05


def _percent_slider_row(title: str, value: int) -> tuple[Adw.ActionRow, Gtk.Scale]:
    row = Adw.ActionRow(title=title)
    slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, MAX_GLOW_PERCENT, 1)
    slider.set_size_request(160, -1)
    slider.set_valign(Gtk.Align.CENTER)
    slider.set_draw_value(True)
    slider.set_value_pos(Gtk.PositionType.RIGHT)
    slider.set_format_value_func(lambda _scale, percent: f"{percent:.0f}%")
    slider.set_value(value)
    slider.update_property([Gtk.AccessibleProperty.LABEL], [title])
    row.add_suffix(slider)
    return row, slider


class ConsoleWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Game Console Feed")
        self.set_default_size(1280, 720)

        self.config = load_config()
        self.pipeline_manager = PipelineManager(on_error=self.show_error)
        self.audio_muted = self.config.get("audio_muted", False)
        self.background_settings = BackgroundSettings.from_config(self.config)

        self.setup_ui()
        self.load_devices()

    def setup_ui(self):
        self.toolbar_view = Adw.ToolbarView()
        self.header = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header)

        self.device_model = Gtk.StringList()
        self.device_dropdown = Gtk.DropDown(model=self.device_model)
        # We'll connect this signal in load_devices after initial setup
        self.header.pack_start(self.device_dropdown)

        self.snap_btn = Gtk.Button(label="Snap AR")
        self.snap_btn.connect("clicked", self.on_snap_clicked)
        self.header.pack_start(self.snap_btn)

        fullscreen_btn = Gtk.Button.new_from_icon_name("view-fullscreen-symbolic")
        fullscreen_btn.set_tooltip_text("Enter Fullscreen (F11)")
        fullscreen_btn.update_property([Gtk.AccessibleProperty.LABEL], ["Enter Fullscreen"])
        fullscreen_btn.connect("clicked", lambda _button: self.toggle_fullscreen())
        self.header.pack_end(fullscreen_btn)

        settings_btn = Gtk.Button.new_from_icon_name("preferences-system-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.update_property([Gtk.AccessibleProperty.LABEL], ["Settings"])
        settings_btn.connect("clicked", self.show_preferences)
        self.header.pack_end(settings_btn)

        self.mute_btn = Gtk.ToggleButton(label="Mute" if not self.audio_muted else "Unmute")
        self.mute_btn.set_active(self.audio_muted)
        self.mute_btn.connect("toggled", self.on_mute_toggled)
        self.header.pack_end(self.mute_btn)

        self.vol_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, MAX_VOLUME, VOLUME_STEP
        )
        self.vol_scale.set_value(self.config.get("volume", UNITY_VOLUME))
        self.vol_scale.set_size_request(140, -1)
        self.vol_scale.set_digits(2)
        self.vol_scale.set_draw_value(True)
        self.vol_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.vol_scale.set_format_value_func(lambda _scale, value: f"{value:.0%}")
        self.vol_scale.add_mark(UNITY_VOLUME, Gtk.PositionType.BOTTOM, None)
        self.vol_scale.update_property([Gtk.AccessibleProperty.LABEL], ["Volume"])
        self.vol_scale.connect("value-changed", self.on_volume_changed)
        self.header.pack_end(self.vol_scale)

        # Adw.ToastOverlay is the main character for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        self.toast_overlay.set_child(self.toolbar_view)

        self.content_stack = Gtk.Stack()
        self.content_stack.set_vexpand(True)
        self.content_stack.set_hexpand(True)
        self.toolbar_view.set_content(self.content_stack)

        self.status_page = Adw.StatusPage()
        self.status_page.set_title("No Signal")
        self.status_page.set_description("Please select a capture device.")
        self.status_page.set_icon_name("camera-web-symbolic")
        self.content_stack.add_named(self.status_page, "status")

        self.picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN)
        self.video_background = VideoBackground(self.background_settings, self.video_aspect_ratio)
        video = Gtk.Overlay(hexpand=True, vexpand=True)
        video.set_child(self.video_background)
        video.add_overlay(self.picture)
        video.set_measure_overlay(self.picture, True)

        self.content_stack.add_named(video, "video")
        self.content_stack.set_visible_child_name("status")

        keyctrl = Gtk.EventControllerKey.new()
        keyctrl.connect("key-pressed", self.on_key_pressed)
        self.add_controller(keyctrl)

        self.connect("notify::fullscreened", self.on_fullscreen_changed)
        self.connect("close-request", self.on_close_request)

    def show_preferences(self, _button):
        dialog = Adw.PreferencesDialog(title="Settings", search_enabled=False)
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Video Background")
        dialog.add(page)
        page.add(group)

        choices = {
            BackgroundMode.THEME: "Follow Theme",
            BackgroundMode.SOLID: "Solid Color",
            BackgroundMode.GLOW: "Edge Glow",
        }
        modes = tuple(choices)
        mode_row = Adw.ComboRow(title="Background")
        mode_row.set_model(Gtk.StringList.new(list(choices.values())))
        mode_row.set_selected(modes.index(self.background_settings.mode))
        group.add(mode_row)

        color_row = Adw.ActionRow(title="Fill Color")
        color_button = Gtk.ColorDialogButton.new(Gtk.ColorDialog(with_alpha=False))
        color_button.set_valign(Gtk.Align.CENTER)
        color_button.update_property([Gtk.AccessibleProperty.LABEL], ["Fill Color"])
        color_button.set_rgba(self.background_settings.rgba())
        color_row.add_suffix(color_button)
        color_row.set_activatable_widget(color_button)
        group.add(color_row)

        brightness_row, brightness = _percent_slider_row(
            "Brightness", self.background_settings.glow.brightness
        )
        spread_row, spread = _percent_slider_row("Spread", self.background_settings.glow.spread)
        group.add(brightness_row)
        group.add(spread_row)

        def update_visible_rows(mode: BackgroundMode) -> None:
            color_row.set_visible(mode is BackgroundMode.SOLID)
            brightness_row.set_visible(mode is BackgroundMode.GLOW)
            spread_row.set_visible(mode is BackgroundMode.GLOW)

        def change_mode(row, _property):
            mode = modes[row.get_selected()]
            update_visible_rows(mode)
            self.set_background_settings(replace(self.background_settings, mode=mode))

        def change_color(button, _property):
            rgba = button.get_rgba()
            color = "#" + "".join(
                f"{round(channel * 255):02x}" for channel in (rgba.red, rgba.green, rgba.blue)
            )
            self.set_background_settings(replace(self.background_settings, color=color))

        def change_glow(_slider):
            glow = GlowSettings(
                brightness=round(brightness.get_value()),
                spread=round(spread.get_value()),
            )
            self.set_background_settings(replace(self.background_settings, glow=glow))

        update_visible_rows(self.background_settings.mode)
        mode_row.connect("notify::selected", change_mode)
        color_button.connect("notify::rgba", change_color)
        brightness.connect("value-changed", change_glow)
        spread.connect("value-changed", change_glow)
        dialog.present(self)

    def set_background_settings(self, settings: BackgroundSettings) -> None:
        mode_changed = self.background_settings.mode is not settings.mode
        self.background_settings = settings
        self.video_background.apply_settings(settings)
        if mode_changed:
            self.update_background_sampling()
        settings.update_config(self.config)
        save_config(self.config)

    def update_background_sampling(self) -> None:
        if (
            self.background_settings.mode is BackgroundMode.GLOW
            and self.picture.get_paintable() is not None
        ):
            self.pipeline_manager.start_background_sampling(
                self.video_background.push_frame, self.show_glow_unavailable
            )
        else:
            self.pipeline_manager.stop_background_sampling()

    def show_glow_unavailable(self) -> None:
        self.video_background.clear_frame()
        toast = Adw.Toast.new("Edge Glow is unavailable for this feed.")
        dialog = self.get_visible_dialog()
        if isinstance(dialog, Adw.PreferencesDialog):
            dialog.add_toast(toast)
        else:
            self.toast_overlay.add_toast(toast)

    def toggle_fullscreen(self):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def on_fullscreen_changed(self, _window, _property):
        self.toolbar_view.set_reveal_top_bars(not self.is_fullscreen())

    def on_key_pressed(self, controller, keyval, keycode, state):
        if self.get_visible_dialog() is not None:
            return False

        is_ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if keyval == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True
        elif keyval == Gdk.KEY_Escape and self.is_fullscreen():
            self.unfullscreen()
            return True
        elif is_ctrl and keyval in (Gdk.KEY_w, Gdk.KEY_W, Gdk.KEY_q, Gdk.KEY_Q):
            self.close()
            return True
        elif not is_ctrl:
            if keyval in (Gdk.KEY_m, Gdk.KEY_M):
                self.mute_btn.set_active(not self.mute_btn.get_active())
                return True
            elif keyval in (Gdk.KEY_s, Gdk.KEY_S):
                self.on_snap_clicked(None)
                return True
            elif keyval in (Gdk.KEY_plus, Gdk.KEY_equal):
                self.vol_scale.set_value(self.vol_scale.get_value() + VOLUME_STEP)
                return True
            elif keyval in (Gdk.KEY_minus, Gdk.KEY_underscore):
                self.vol_scale.set_value(self.vol_scale.get_value() - VOLUME_STEP)
                return True

        return False

    def load_devices(self):
        self.devices = get_video_devices()
        strings = [d["name"] for d in self.devices]

        self.device_model.splice(0, 0, strings)

        if not self.devices:
            self.status_page.set_description("No video devices found.")
            return

        last_device_id = self.config.get("last_device_id")
        selected_idx = 0
        found_last = False

        for i, dev in enumerate(self.devices):
            if dev["id"] == last_device_id:
                selected_idx = i
                found_last = True
                break

        # Set the selection without firing signals yet
        self.device_dropdown.set_selected(selected_idx)

        # Connect signal ONLY for future user-driven changes
        self.device_dropdown.connect("notify::selected-item", self.on_device_selected)

        # Manually start the stream for the initial selection
        initial_device = self.devices[selected_idx]
        self.start_stream(initial_device)

        # Gracefully handle if the saved device is gone
        if not found_last and last_device_id:
            msg = f"Last used device not found. Defaulting to {initial_device['name']}."
            toast = Adw.Toast.new(msg)
            self.toast_overlay.add_toast(toast)

    def on_device_selected(self, dropdown, pspec):
        idx = dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or not self.devices:
            return
        dev = self.devices[idx]
        self.config["last_device_id"] = dev["id"]
        save_config(self.config)
        self.start_stream(dev)

    def on_mute_toggled(self, btn):
        self.audio_muted = btn.get_active()
        btn.set_label("Unmute" if self.audio_muted else "Mute")
        self.config["audio_muted"] = self.audio_muted
        save_config(self.config)
        self.pipeline_manager.set_mute(self.audio_muted)

    def on_volume_changed(self, scale):
        volume = scale.get_value()
        self.pipeline_manager.set_volume(volume)
        self.config["volume"] = volume
        save_config(self.config)

    def video_aspect_ratio(self) -> float:
        paintable = self.picture.get_paintable()
        if paintable:
            aspect = paintable.get_intrinsic_aspect_ratio()
            if aspect > 0:
                return aspect
        return 16 / 9

    def on_snap_clicked(self, btn):
        if self.is_fullscreen() or self.is_maximized():
            return

        current_width = self.get_width()
        current_height = self.get_height()

        # If we haven't been measured yet, wait for the next tick.
        # This prevents redundant resizes on startup where get_width() might return 0.
        if current_width <= 0 or current_height <= 0:
            return

        # Calculate the height needed for the video area
        video_height = int(current_width / self.video_aspect_ratio())

        # In GTK4, the window size includes the HeaderBar.
        # We need to measure the HeaderBar's natural height and add it.
        measurements = self.header.measure(Gtk.Orientation.VERTICAL, -1)
        header_height = (
            measurements.natural if hasattr(measurements, "natural") else measurements[1]
        )

        target_height = video_height + header_height

        # If the window is already perfectly snapped (within 2 pixel tolerance),
        # do not trigger the destructive hide/present cycle.
        if abs(current_height - target_height) <= 2:
            return

        # Wayland compositors notoriously ignore set_default_size and size requests
        # once the user has manually dragged a window. The only guaranteed way to
        # force a shrink/resize is to hide the window, set the new default size,
        # and present it again.
        # However, we ONLY do this for manual clicks (btn is not None).
        # For auto-snaps on startup, a simple set_default_size is cleaner.
        if btn is None:
            self.set_default_size(current_width, target_height)
            return

        self.hide()

        def _re_present():
            self.set_default_size(current_width, target_height)
            self.present()
            return False

        GLib.idle_add(_re_present)

    def start_stream(self, device_info):
        self.clear_video()

        video_path = device_info["path"]
        audio_path = get_matching_alsa_device(video_path, device_info["name"])

        paintable = self.pipeline_manager.start(
            video_path, audio_path, muted=self.audio_muted, volume=self.vol_scale.get_value()
        )
        if paintable is None:
            return

        self.picture.set_paintable(paintable)
        self.content_stack.set_visible_child_name("video")
        self.update_background_sampling()

        # Let the first frame settle the intrinsic dimensions before snapping the window.
        GLib.timeout_add(500, self._auto_snap, paintable)

    def _auto_snap(self, paintable):
        if self.picture.get_paintable() == paintable:
            self.on_snap_clicked(None)
        return False

    def clear_video(self) -> None:
        self.picture.set_paintable(None)
        self.video_background.clear_frame()

    def show_error(self, msg):
        self.clear_video()
        self.status_page.set_description(msg)
        self.content_stack.set_visible_child_name("status")

    def on_close_request(self, *args):
        self.clear_video()
        self.pipeline_manager.stop()
        return False
