from time import monotonic, sleep

import pytest
from gi.repository import GLib

from game_console_feed.pipeline import (
    BACKGROUND_SAMPLE_SIZE,
    Gst,
    PipelineManager,
    _Capture,
    _packed_rgb,
    _sample_for_scaler,
)


@pytest.mark.parametrize("drm_format", ["YUYV", "YUYV:0x0100000000000001"])
def test_sampler_reads_only_linear_dma_frames(drm_format):
    Gst.init(None)
    caps = Gst.Caps.from_string(
        f"video/x-raw(memory:DMABuf),format=DMA_DRM,drm-format={drm_format},"
        "width=1920,height=1080,framerate=60/1,pixel-aspect-ratio=1/1,"
        "interlace-mode=progressive,colorimetry=2:4:5:1"
    )
    buffer = Gst.Buffer.new()
    sample = Gst.Sample.new(buffer, caps)

    prepared = _sample_for_scaler(sample)

    if drm_format != "YUYV":
        assert prepared is None
        return

    assert prepared is not None
    raw_caps = prepared.get_caps()
    assert raw_caps.get_structure(0).get_string("format") == "YUY2"
    assert raw_caps.get_structure(0).get_string("colorimetry") == "2:4:5:1"
    assert raw_caps.get_features(0).contains("memory:SystemMemory")
    assert prepared.get_buffer() == buffer
    assert sample.get_caps().is_equal(caps)


def test_sampler_rejects_a_short_rgb_frame():
    Gst.init(None)
    size = BACKGROUND_SAMPLE_SIZE
    caps = Gst.Caps.from_string(f"video/x-raw,format=RGB,width={size},height={size}")
    buffer = Gst.Buffer.new_allocate(None, 3 * size * size - 1, None)

    with pytest.raises(ValueError, match="Incomplete RGB sample"):
        _packed_rgb(Gst.Sample.new(buffer, caps))


def test_sampler_requires_a_video_layout():
    Gst.init(None)
    caps = Gst.Caps.from_string("application/octet-stream")

    with pytest.raises(ValueError, match="Invalid RGB sample layout"):
        _packed_rgb(Gst.Sample.new(Gst.Buffer.new(), caps))


def test_sampler_error_releases_resources_and_keeps_capture_playing():
    Gst.init(None)
    # A real capture pipeline with test sources runs without a display or ALSA device.
    capture = Gst.parse_launch(
        "videotestsrc is-live=true ! video/x-raw,format=RGB ! "
        "fakesink name=video sync=false enable-last-sample=false "
        "audiotestsrc is-live=true ! volume name=gain ! fakesink sync=false"
    )
    sink = capture.get_by_name("video")
    capture.get_bus().add_signal_watch()
    manager = PipelineManager(on_error=pytest.fail)
    manager._capture = _Capture(capture, sink, capture.get_by_name("gain"))
    frames: list[bytes] = []
    unavailable: list[bool] = []
    context = GLib.MainContext.default()

    def wait_until(predicate):
        deadline = monotonic() + 3
        while not predicate():
            assert monotonic() < deadline, "Timed out waiting for the sampler"
            context.iteration(False)
            sleep(0.005)

    try:
        capture.set_state(Gst.State.PLAYING)
        assert capture.get_state(Gst.SECOND).state == Gst.State.PLAYING
        manager.start_background_sampling(frames.append, lambda: unavailable.append(True))
        wait_until(lambda: frames)
        assert len(frames[-1]) == 3 * BACKGROUND_SAMPLE_SIZE**2
        sampler = manager._sampler
        assert sampler is not None

        failure = Gst.Message.new_error(sampler.pipeline, GLib.Error("test error"), "test")
        assert sampler.pipeline.post_message(failure)
        wait_until(lambda: unavailable)

        assert unavailable == [True]
        assert manager._sampler is None
        assert context.find_source_by_id(sampler.timer) is None
        assert sink.get_property("last-sample") is None
        assert sampler.pipeline.get_state(0).state == Gst.State.NULL
        assert capture.get_state(0).state == Gst.State.PLAYING
    finally:
        manager.stop()
