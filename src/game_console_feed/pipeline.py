from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
from gi.repository import GLib, Gst, GstVideo  # noqa: E402

if TYPE_CHECKING:
    from gi.repository import Gdk

BACKGROUND_SAMPLE_SIZE = 16  # Width and height of the tightly packed RGB sample.
BACKGROUND_SAMPLE_INTERVAL_MS = 100
DRM_FORMAT_MOD_LINEAR = 0  # A row-major layout the CPU scaler can read.
logger = logging.getLogger(__name__)


def _sample_for_scaler(sample: Gst.Sample) -> Gst.Sample | None:
    caps = sample.get_caps()
    if not GstVideo.video_is_dma_drm_caps(caps):
        return sample

    structure = caps.get_structure(0)
    drm_format = structure.get_string("drm-format")
    if drm_format is None:
        return None
    # The caps parser returns the modifier reliably through GI, including for tiled buffers.
    fourcc, modifier = GstVideo.video_dma_drm_fourcc_from_string(drm_format)
    if modifier != DRM_FORMAT_MOD_LINEAR:
        return None
    raw_format = GstVideo.video_dma_drm_fourcc_to_format(fourcc)
    if raw_format == GstVideo.VideoFormat.UNKNOWN:
        return None

    # Build caps directly because GI can under-allocate the output of to_video_info().
    # Reusing the original buffer preserves plane offsets and row strides.
    raw_structure = structure.copy()
    raw_structure.set_value("format", GstVideo.VideoFormat.to_string(raw_format))
    raw_structure.remove_field("drm-format")
    raw_caps = Gst.Caps.new_empty()
    raw_caps.append_structure(raw_structure)
    return Gst.Sample.new(sample.get_buffer(), raw_caps)


@dataclass(frozen=True)
class _Capture:
    """The playback pipeline and its elements used outside the streaming threads."""

    pipeline: Gst.Pipeline
    video_sink: Gst.Element
    volume: Gst.Element


@dataclass(frozen=True)
class _BackgroundSampler:
    """The isolated converter, its GLib timer, and the sink retaining its input frame."""

    pipeline: Gst.Pipeline
    timer: int
    capture_sink: Gst.Element


class PipelineManager:
    def __init__(self, on_error: Callable[[str], None]):
        self._on_error = on_error
        self._capture: _Capture | None = None
        self._sampler: _BackgroundSampler | None = None

    def start(
        self, video_device: str, audio_device: str, *, muted: bool, volume: float
    ) -> Gdk.Paintable | None:
        self.stop()

        pipeline_str = (
            f"v4l2src device={video_device} ! videoconvert ! "
            "gtk4paintablesink name=vsink sync=false enable-last-sample=false "
            f"alsasrc device={audio_device} ! audioconvert ! volume name=vol ! "
            "audioresample ! autoaudiosink sync=false"
        )

        try:
            pipeline = Gst.parse_launch(pipeline_str)
        except GLib.Error as err:
            self._on_error(f"Failed to create pipeline: {err}")
            return None

        video_sink = pipeline.get_by_name("vsink")
        paintable = video_sink.get_property("paintable")
        if paintable is None:
            self._on_error("Capture pipeline has no video output.")
            return None

        gain = pipeline.get_by_name("vol")
        gain.set_property("mute", muted)
        gain.set_property("volume", volume)
        self._capture = _Capture(pipeline, video_sink, gain)

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_capture_error)
        bus.connect("message::eos", self._on_capture_ended)
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.stop()
            self._on_error("Failed to start playback. Device might be busy.")
            return None
        return paintable

    def start_background_sampling(
        self, on_frame: Callable[[bytes], None], on_unavailable: Callable[[], None]
    ) -> None:
        capture = self._capture
        if capture is None or self._sampler is not None:
            return

        # Convert snapshots in a separate pipeline to preserve playback negotiation.
        try:
            sampler = Gst.parse_launch(
                "appsrc name=background_source is-live=true format=time "
                "max-buffers=1 max-bytes=0 leaky-type=downstream ! "
                "videoconvertscale add-borders=false ! "
                f"video/x-raw,format=RGB,width={BACKGROUND_SAMPLE_SIZE},"
                f"height={BACKGROUND_SAMPLE_SIZE},pixel-aspect-ratio=1/1 ! "
                "appsink name=background_sink max-buffers=1 drop=true wait-on-eos=false "
                "sync=false async=false enable-last-sample=false"
            )
        except GLib.Error as err:
            logger.warning("Could not create Edge Glow sampler: %s", err)
            on_unavailable()
            return

        if sampler.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            sampler.set_state(Gst.State.NULL)
            logger.warning("Could not start Edge Glow sampler")
            on_unavailable()
            return

        capture.video_sink.set_property("enable-last-sample", True)
        timer = GLib.timeout_add(
            BACKGROUND_SAMPLE_INTERVAL_MS, self._poll_background, on_frame, on_unavailable
        )
        self._sampler = _BackgroundSampler(sampler, timer, capture.video_sink)

    def stop_background_sampling(self) -> None:
        sampler = self._sampler
        if sampler is not None:
            self._sampler = None
            GLib.source_remove(sampler.timer)
            sampler.capture_sink.set_property("enable-last-sample", False)
            sampler.pipeline.set_state(Gst.State.NULL)

    def _poll_background(
        self, on_frame: Callable[[bytes], None], on_unavailable: Callable[[], None]
    ) -> bool:
        sampler = self._sampler
        if sampler is None:
            return GLib.SOURCE_REMOVE
        try:
            frame = _read_background_frame(sampler.pipeline, sampler.capture_sink)
        except (GLib.Error, ValueError) as err:
            logger.warning("Edge Glow sampler stopped: %s", err)
            self.stop_background_sampling()
            on_unavailable()
            return GLib.SOURCE_REMOVE
        if frame is not None:
            on_frame(frame)
        return GLib.SOURCE_CONTINUE

    def set_volume(self, value: float) -> None:
        if self._capture is not None:
            self._capture.volume.set_property("volume", value)

    def set_mute(self, mute: bool) -> None:
        if self._capture is not None:
            self._capture.volume.set_property("mute", mute)

    def stop(self) -> None:
        self.stop_background_sampling()
        if self._capture is not None:
            pipeline = self._capture.pipeline
            self._capture = None
            pipeline.get_bus().remove_signal_watch()
            pipeline.set_state(Gst.State.NULL)

    def _on_capture_error(self, _bus: Gst.Bus, message: Gst.Message) -> None:
        err, _debug = message.parse_error()
        self.stop()
        self._on_error(f"Pipeline error: {err.message}")

    def _on_capture_ended(self, _bus: Gst.Bus, _message: Gst.Message) -> None:
        self.stop()
        self._on_error("Capture stream ended.")


def _read_background_frame(sampler: Gst.Pipeline, capture_sink: Gst.Element) -> bytes | None:
    failure = sampler.get_bus().pop_filtered(Gst.MessageType.ERROR)
    if failure is not None:
        err, debug = failure.parse_error()
        raise ValueError(f"{err.message}\n{debug}")

    latest = capture_sink.get_property("last-sample")
    if latest is not None:
        scaler_input = _sample_for_scaler(latest)
        if scaler_input is None:
            raise ValueError(f"Unsupported DMA buffer format ({latest.get_caps().to_string()})")
        result = sampler.get_by_name("background_source").emit("push-sample", scaler_input)
        if result != Gst.FlowReturn.OK:
            raise ValueError(f"Could not queue a capture frame ({result.value_nick})")

    sample = sampler.get_by_name("background_sink").emit("try-pull-sample", 0)
    return _packed_rgb(sample) if sample is not None else None


def _packed_rgb(sample: Gst.Sample) -> bytes:
    buffer = sample.get_buffer()
    layout = GstVideo.buffer_get_video_meta(buffer)
    if layout is None:
        try:
            layout = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
        except TypeError as err:
            raise ValueError("Invalid RGB sample layout") from err

    offset, stride = layout.offset[0], layout.stride[0]
    row_size = 3 * BACKGROUND_SAMPLE_SIZE
    frame_size = row_size * BACKGROUND_SAMPLE_SIZE
    if stride == row_size:
        pixels = buffer.extract_dup(offset, frame_size)
    else:
        # Some buffers pad each row. Only pass pixel bytes to GTK.
        pixels = b"".join(
            buffer.extract_dup(offset + row * stride, row_size)
            for row in range(BACKGROUND_SAMPLE_SIZE)
        )
    if len(pixels) != frame_size:
        raise ValueError("Incomplete RGB sample")
    return pixels
