import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from game_console_feed.config import load_config, save_config  # noqa: E402
from game_console_feed.discovery import get_matching_alsa_device, get_video_devices  # noqa: E402
from game_console_feed.pipeline import PipelineManager  # noqa: E402


class ConsoleWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Game Console Feed")
        self.set_default_size(1280, 720)

        self.config = load_config()
        self.pipeline_manager = PipelineManager(on_error_callback=self.on_pipeline_error)
        self.audio_muted = self.config.get("audio_muted", False)
        self.volume = self.config.get("volume", 1.0)
        self.aspect_locked = self.config.get("aspect_locked", True)
        self.picture = None

        self.setup_ui()
        self.load_devices()

    def setup_ui(self):
        self.header = Adw.HeaderBar()

        self.device_model = Gtk.StringList()
        self.device_dropdown = Gtk.DropDown(model=self.device_model)
        self.device_dropdown.connect("notify::selected-item", self.on_device_selected)
        self.header.pack_start(self.device_dropdown)

        self.snap_btn = Gtk.Button(label="Snap AR")
        self.snap_btn.connect("clicked", self.on_snap_clicked)
        self.header.pack_start(self.snap_btn)

        self.mute_btn = Gtk.ToggleButton(label="Mute" if not self.audio_muted else "Unmute")
        self.mute_btn.set_active(self.audio_muted)
        self.mute_btn.connect("toggled", self.on_mute_toggled)
        self.header.pack_end(self.mute_btn)

        self.vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.05)
        self.vol_scale.set_value(self.volume)
        self.vol_scale.set_size_request(100, -1)
        self.vol_scale.connect("value-changed", self.on_volume_changed)
        self.header.pack_end(self.vol_scale)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.append(self.header)

        self.content_stack = Gtk.Stack()
        self.content_stack.set_vexpand(True)
        self.content_stack.set_hexpand(True)
        self.box.append(self.content_stack)

        self.status_page = Adw.StatusPage()
        self.status_page.set_title("No Signal")
        self.status_page.set_description("Please select a capture device.")
        self.status_page.set_icon_name("camera-web-symbolic")
        self.content_stack.add_named(self.status_page, "status")

        self.video_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.video_box.set_hexpand(True)
        self.video_box.set_vexpand(True)

        self.content_stack.add_named(self.video_box, "video")
        self.content_stack.set_visible_child_name("status")

        self.set_content(self.box)

        keyctrl = Gtk.EventControllerKey.new()
        keyctrl.connect("key-pressed", self.on_key_pressed)
        self.add_controller(keyctrl)

        self.connect("close-request", self.on_close_request)

    def on_key_pressed(self, controller, keyval, keycode, state):
        is_ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if keyval == Gdk.KEY_F11:
            if self.is_fullscreen():
                self.unfullscreen()
            else:
                self.fullscreen()
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
                new_vol = min(1.0, self.volume + 0.05)
                self.vol_scale.set_value(new_vol)
                return True
            elif keyval in (Gdk.KEY_minus, Gdk.KEY_underscore):
                new_vol = max(0.0, self.volume - 0.05)
                self.vol_scale.set_value(new_vol)
                return True

        return False

    def load_devices(self):
        self.devices = get_video_devices()
        strings = [d["name"] for d in self.devices]

        self.device_model.splice(0, 0, strings)

        if not self.devices:
            self.status_page.set_description("No video devices found.")
            return

        last_device = self.config.get("last_device_path")
        selected_idx = 0
        for i, dev in enumerate(self.devices):
            if dev["path"] == last_device:
                selected_idx = i
                break

        # setting the selected index will fire on_device_selected
        # which starts the stream
        self.device_dropdown.set_selected(selected_idx)

    def on_device_selected(self, dropdown, pspec):
        idx = dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or not self.devices:
            return
        dev = self.devices[idx]
        self.config["last_device_path"] = dev["path"]
        save_config(self.config)
        self.start_stream(dev)

    def on_mute_toggled(self, btn):
        self.audio_muted = btn.get_active()
        btn.set_label("Unmute" if self.audio_muted else "Mute")
        self.config["audio_muted"] = self.audio_muted
        save_config(self.config)
        self.pipeline_manager.set_mute(self.audio_muted)

    def on_volume_changed(self, scale):
        self.volume = scale.get_value()
        self.pipeline_manager.set_volume(self.volume)
        self.config["volume"] = self.volume
        save_config(self.config)

    def on_snap_clicked(self, btn):
        if self.is_fullscreen() or self.is_maximized():
            return

        current_width = self.get_width()
        current_height = self.get_height()

        if current_width <= 0:
            current_width = 1280

        aspect_ratio = 16 / 9
        if self.picture:
            paintable = self.picture.get_paintable()
            if paintable:
                w = paintable.get_intrinsic_width()
                h = paintable.get_intrinsic_height()
                if w > 0 and h > 0:
                    aspect_ratio = w / h

        # Calculate the height needed for the video area
        video_height = int(current_width / aspect_ratio)

        # In GTK4, the window size includes the HeaderBar.
        # We need to measure the HeaderBar's natural height and add it.
        measurements = self.header.measure(Gtk.Orientation.VERTICAL, -1)
        header_height = (
            measurements.natural if hasattr(measurements, "natural") else measurements[1]
        )

        target_height = video_height + header_height

        # If the window is already perfectly snapped (within 1 pixel tolerance),
        # do not trigger the destructive hide/present cycle.
        if abs(current_height - target_height) <= 1:
            return

        # Wayland compositors notoriously ignore set_default_size and size requests
        # once the user has manually dragged a window. The only guaranteed way to
        # force a shrink/resize is to hide the window, set the new default size,
        # and present it again.
        # However, hiding and presenting in the exact same event loop tick can
        # cause Wayland Protocol Error 71 because the compositor receives conflicting
        # state changes. We use idle_add to delay the present() to the next tick.
        self.hide()

        def _re_present():
            self.set_default_size(current_width, target_height)
            self.present()
            return False

        GLib.idle_add(_re_present)

    def start_stream(self, device_info):
        self.pipeline_manager.stop()
        self.picture = None

        video_path = device_info["path"]
        audio_path = get_matching_alsa_device(video_path, device_info["name"])

        success = self.pipeline_manager.build_pipeline(video_path, audio_path, self.audio_muted)
        if success:
            paintable = self.pipeline_manager.get_paintable()
            if paintable:
                while self.video_box.get_first_child():
                    self.video_box.remove(self.video_box.get_first_child())

                self.picture = Gtk.Picture.new_for_paintable(paintable)
                self.picture.set_can_shrink(True)
                self.picture.set_hexpand(True)
                self.picture.set_vexpand(True)
                self.picture.set_keep_aspect_ratio(
                    True
                )  # Always keep ratio to show borders instead of distorting

                self.video_box.append(self.picture)
                self.content_stack.set_visible_child_name("video")

                self.pipeline_manager.set_volume(self.volume)
                self.pipeline_manager.play()

                # Give GStreamer a tiny moment to negotiate caps and get the first frame
                # so we can read the intrinsic dimensions, then automatically snap the AR.
                GLib.timeout_add(500, self._auto_snap)
        else:
            self.show_error("Failed to build pipeline.")

    def _auto_snap(self):
        # Only snap if we actually successfully connected and started playing
        if self.picture and self.picture.get_paintable():
            self.on_snap_clicked(None)
        return False

    def on_pipeline_error(self, err_msg):
        GLib.idle_add(self.show_error, err_msg)

    def show_error(self, msg):
        self.status_page.set_description(msg)
        self.content_stack.set_visible_child_name("status")

    def on_close_request(self, *args):
        self.pipeline_manager.stop()
        return False
