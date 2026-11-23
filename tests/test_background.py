from game_console_feed.background import (
    DEFAULT_GLOW_BRIGHTNESS,
    DEFAULT_GLOW_SPREAD,
    GLOW_DEPTH_SAMPLES,
    MAX_GLOW_PERCENT,
    BackgroundMode,
    BackgroundSettings,
    GlowSettings,
    _diffused_strip,
)
from game_console_feed.pipeline import BACKGROUND_SAMPLE_SIZE


def test_saved_glow_uses_existing_appearance_by_default():
    settings = BackgroundSettings.from_config({"video_background_mode": "glow"})

    assert settings.mode is BackgroundMode.GLOW
    assert settings.glow == GlowSettings(DEFAULT_GLOW_BRIGHTNESS, DEFAULT_GLOW_SPREAD)


def test_glow_preferences_round_trip_while_solid_color_is_selected():
    settings = BackgroundSettings(
        BackgroundMode.SOLID, "#002244", GlowSettings(0, MAX_GLOW_PERCENT)
    )
    config: dict = {}

    settings.update_config(config)

    assert BackgroundSettings.from_config(config) == settings


def test_glow_sliders_control_light_and_color_mixing_independently():
    center = BACKGROUND_SAMPLE_SIZE // 2
    colors = [(0.0, 0.0, 0.0)] * BACKGROUND_SAMPLE_SIZE
    colors[center] = (255.0, 0.0, 0.0)

    def pixel(settings: GlowSettings, row: int, column: int) -> int:
        surface = _diffused_strip(colors, settings)
        pixels = surface.get_data().cast("I")
        return pixels[row * (surface.get_stride() // pixels.itemsize) + column]

    middle = GLOW_DEPTH_SAMPLES // 2
    off_center = center + BACKGROUND_SAMPLE_SIZE // 4
    assert pixel(GlowSettings(0, DEFAULT_GLOW_SPREAD), 0, center) == 0
    assert pixel(GlowSettings(MAX_GLOW_PERCENT, DEFAULT_GLOW_SPREAD), 0, center) > 0
    assert pixel(GlowSettings(MAX_GLOW_PERCENT, 0), middle, off_center) == 0
    assert pixel(GlowSettings(MAX_GLOW_PERCENT, MAX_GLOW_PERCENT), middle, off_center) > pixel(
        GlowSettings(MAX_GLOW_PERCENT, DEFAULT_GLOW_SPREAD), middle, off_center
    )
