import pytest

from game_console_feed.pipeline import BACKGROUND_SAMPLE_SIZE, Gst, _packed_rgb, _sample_for_scaler


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
