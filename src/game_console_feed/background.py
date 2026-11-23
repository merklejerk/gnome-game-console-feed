import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

import cairo
import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_foreign("cairo")
from gi.repository import Gdk, Gtk  # noqa: E402

from game_console_feed.pipeline import BACKGROUND_SAMPLE_SIZE  # noqa: E402

DEFAULT_FILL = "#000000"
FRAME_BLEND = 0.25  # Weight of a fresh sample when smoothing successive frames.
MAX_GLOW_PERCENT = 100
DEFAULT_GLOW_BRIGHTNESS = 60
DEFAULT_GLOW_SPREAD = 50
GLOW_DEPTH_SAMPLES = 12  # Rows of progressively mixed color between the picture and window edge.


class BackgroundMode(StrEnum):
    """Persisted choices for the area around the video."""

    THEME = "theme"
    SOLID = "solid"
    GLOW = "glow"


@dataclass(frozen=True)
class GlowSettings:
    """Edge Glow brightness and color spread, expressed as whole percentages."""

    brightness: int = DEFAULT_GLOW_BRIGHTNESS  # Light level next to the picture.
    spread: int = DEFAULT_GLOW_SPREAD  # How much neighboring colors mix across the bars.


@dataclass(frozen=True)
class BackgroundSettings:
    """Background mode and saved preferences for each configurable mode."""

    mode: BackgroundMode
    color: str
    glow: GlowSettings = GlowSettings()  # Retained when switching background modes.

    @classmethod
    def from_config(cls, config: dict) -> "BackgroundSettings":
        mode = BackgroundMode.THEME
        saved_mode = config.get("video_background_mode")
        if isinstance(saved_mode, str) and saved_mode in BackgroundMode:
            mode = BackgroundMode(saved_mode)

        color = config.get("video_background_color")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            color = DEFAULT_FILL
        glow = GlowSettings(
            brightness=_saved_percentage(
                config.get("edge_glow_brightness"), DEFAULT_GLOW_BRIGHTNESS
            ),
            spread=_saved_percentage(config.get("edge_glow_spread"), DEFAULT_GLOW_SPREAD),
        )
        return cls(mode, color.lower(), glow)

    def update_config(self, config: dict) -> None:
        config["video_background_mode"] = self.mode.value
        config["video_background_color"] = self.color
        config["edge_glow_brightness"] = self.glow.brightness
        config["edge_glow_spread"] = self.glow.spread

    def rgba(self) -> Gdk.RGBA:
        rgba = Gdk.RGBA()
        rgba.parse(self.color)
        return rgba


def _saved_percentage(value: object, default: int) -> int:
    if type(value) is int and 0 <= value <= MAX_GLOW_PERCENT:
        return value
    return default


class VideoBackground(Gtk.DrawingArea):
    """Draw the fill under the video picture using the same aspect ratio as playback."""

    def __init__(self, settings: BackgroundSettings, video_aspect_ratio: Callable[[], float]):
        super().__init__(can_target=False)
        self._video_aspect_ratio = video_aspect_ratio
        self._frame: tuple[float, ...] = ()  # Smoothed RGB channels from the current stream.
        self.set_draw_func(self._draw)
        self.apply_settings(settings)

    def apply_settings(self, settings: BackgroundSettings) -> None:
        self._settings = settings
        color = settings.rgba()
        self._solid_rgb = (color.red, color.green, color.blue)
        if settings.mode is BackgroundMode.GLOW:
            self.queue_draw()
        else:
            self.clear_frame()

    def push_frame(self, frame: bytes) -> None:
        if self._frame:
            self._frame = tuple(
                previous + (current - previous) * FRAME_BLEND
                for previous, current in zip(self._frame, frame, strict=True)
            )
        else:
            self._frame = tuple(map(float, frame))
        self.queue_draw()

    def clear_frame(self) -> None:
        self._frame = ()
        self.queue_draw()

    def _draw(self, _area, cr: cairo.Context, width: int, height: int, *_data) -> None:
        if self._settings.mode is BackgroundMode.THEME:
            return
        if self._settings.mode is BackgroundMode.SOLID:
            cr.set_source_rgb(*self._solid_rgb)
            cr.paint()
            return

        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        if self._frame:
            self._draw_glow(cr, width, height)

    def _draw_glow(self, cr: cairo.Context, width: int, height: int) -> None:
        aspect = self._video_aspect_ratio()
        sample_width = BACKGROUND_SAMPLE_SIZE
        last = sample_width - 1
        horizontal_depth = (width - height * aspect) / 2
        vertical_depth = (height - width / aspect) / 2

        if horizontal_depth > 0:
            left, right = horizontal_depth, width - horizontal_depth
            self._draw_bar(cr, (left, 0), (left, height), (-left, 0), 0, 1, sample_width)
            self._draw_bar(cr, (right, 0), (right, height), (left, 0), last, -1, sample_width)
        elif vertical_depth > 0:
            top, bottom = vertical_depth, height - vertical_depth
            self._draw_bar(cr, (0, top), (width, top), (0, -top), 0, sample_width, 1)
            self._draw_bar(
                cr, (0, bottom), (width, bottom), (0, top), last * sample_width, -sample_width, 1
            )

    def _draw_bar(
        self,
        cr: cairo.Context,
        start: tuple[float, float],
        end: tuple[float, float],
        outward: tuple[float, float],
        first_pixel: int,
        inset: int,
        step: int,
    ) -> None:
        edge_colors = []
        for index in range(BACKGROUND_SAMPLE_SIZE):
            edge_offset = 3 * (first_pixel + index * step)
            inner_offset = edge_offset + 3 * inset
            edge_colors.append(
                tuple(
                    (self._frame[edge_offset + channel] + self._frame[inner_offset + channel]) / 2
                    for channel in range(3)
                )
            )

        strip = _diffused_strip(edge_colors, self._settings.glow)
        width, depth = strip.get_width(), strip.get_height()
        cr.save()
        # Map the strip's width along the video edge and its depth outward into the bar.
        cr.transform(
            cairo.Matrix(
                (end[0] - start[0]) / width,
                (end[1] - start[1]) / width,
                outward[0] / depth,
                outward[1] / depth,
                *start,
            )
        )
        cr.set_source_surface(strip)
        pattern = cr.get_source()
        pattern.set_filter(cairo.Filter.BILINEAR)
        pattern.set_extend(cairo.Extend.PAD)
        cr.rectangle(0, 0, width, depth)
        cr.fill()
        cr.restore()


def _diffused_strip(
    edge_colors: Sequence[tuple[float, ...]], settings: GlowSettings
) -> cairo.ImageSurface:
    width = len(edge_colors)
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, GLOW_DEPTH_SAMPLES)
    pixels = surface.get_data().cast("I")
    stride = surface.get_stride() // pixels.itemsize
    brightness = settings.brightness / MAX_GLOW_PERCENT
    # Spread ranges from zero to two blur passes per row, with partial passes in between.
    spread = 2 * settings.spread / MAX_GLOW_PERCENT
    first_pass = min(spread, 1.0)
    second_pass = max(spread - 1.0, 0.0)

    for row in range(GLOW_DEPTH_SAMPLES):
        if row and first_pass:
            edge_colors = _blur_edge(edge_colors, first_pass)
            if second_pass:
                edge_colors = _blur_edge(edge_colors, second_pass)

        distance = row / (GLOW_DEPTH_SAMPLES - 1)
        light = brightness * (1 - distance**2 * (3 - 2 * distance))
        for column, rgb in enumerate(edge_colors):
            red, green, blue = (round(channel * light) for channel in rgb)
            pixels[row * stride + column] = (red << 16) | (green << 8) | blue

    surface.mark_dirty()
    return surface


def _blur_edge(colors: Sequence[tuple[float, ...]], amount: float) -> list[tuple[float, ...]]:
    # Extend the end colors so the blur also samples the edge color at the corners.
    padded = [colors[0], *colors, colors[-1]]
    return [
        tuple(
            center + amount * ((left + 2 * center + right) / 4 - center)
            for left, center, right in zip(left_rgb, center_rgb, right_rgb, strict=True)
        )
        for left_rgb, center_rgb, right_rgb in zip(padded[:-2], colors, padded[2:], strict=True)
    ]
