import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gst  # noqa: E402


class PipelineManager:
    def __init__(self, on_error_callback=None):
        Gst.init(None)
        self.pipeline = None
        self.video_sink = None
        self.on_error_callback = on_error_callback

    def build_pipeline(self, video_device: str, audio_device: str, mute_audio: bool = False):
        if self.pipeline:
            self.stop()

        pipeline_str = (
            f"v4l2src device={video_device} ! videoconvert ! gtk4paintablesink name=vsink sync=false "  # noqa: E501
            f"alsasrc device={audio_device} ! audioconvert ! volume name=vol ! audioresample ! autoaudiosink sync=false"  # noqa: E501
        )

        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
        except GLib.Error as err:
            if self.on_error_callback:
                self.on_error_callback(f"Failed to create pipeline: {err}")
            return False

        self.video_sink = self.pipeline.get_by_name("vsink")
        self.vol_element = self.pipeline.get_by_name("vol")
        if self.vol_element:
            self.vol_element.set_property("mute", mute_audio)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus_message)
        return True

    def set_volume(self, value: float):
        if self.vol_element:
            self.vol_element.set_property("volume", value)

    def set_mute(self, mute: bool):
        if self.vol_element:
            self.vol_element.set_property("mute", mute)

    def get_paintable(self):
        if self.video_sink:
            return self.video_sink.get_property("paintable")
        return None

    def play(self):
        if self.pipeline:
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                if self.on_error_callback:
                    self.on_error_callback("Failed to start playback. Device might be busy.")

    def stop(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
            self.video_sink = None

    def on_bus_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            self.stop()
            if self.on_error_callback:
                self.on_error_callback(f"Pipeline error: {err.message}")
        elif t == Gst.MessageType.EOS:
            self.stop()
        return True
