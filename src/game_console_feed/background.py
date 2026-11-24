import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

from game_console_feed.pipeline import BACKGROUND_SAMPLE_SIZE  # noqa: E402

DEFAULT_FILL = "#000000"
FRAME_BLEND = 0.25  # Weight of a fresh sample when smoothing successive frames.
MAX_GLOW_PERCENT = 100
DEFAULT_GLOW_BRIGHTNESS = 60
DEFAULT_GLOW_SPREAD = 50
GLOW_DEPTH_SAMPLES = 12  # Rows of progressively mixed color between the picture and window edge.
MIN_BAR_DEPTH = 0.5  # Ignore bars smaller than half a logical pixel.


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


class VideoBackground(Gtk.Widget):
    """Draw the fill under the video picture using the same aspect ratio as playback."""

    def __init__(self, settings: BackgroundSettings, video_aspect_ratio: Callable[[], float]):
        super().__init__(can_target=False)
        self._video_aspect_ratio = video_aspect_ratio
        self._frame: tuple[float, ...] = ()  # Smoothed RGB channels from the current stream.
        self.apply_settings(settings)

    def apply_settings(self, settings: BackgroundSettings) -> None:
        self._settings = settings
        self._solid_color = settings.rgba()  # A GTK color node for solid fill.
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
        if max(self._bar_depths(self.get_width(), self.get_height())) >= MIN_BAR_DEPTH:
            self.queue_draw()

    def clear_frame(self) -> None:
        self._frame = ()
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        if self._settings.mode is BackgroundMode.THEME:
            return
        width, height = self.get_width(), self.get_height()
        bounds = Graphene.Rect().init(0, 0, width, height)
        if self._settings.mode is BackgroundMode.SOLID:
            snapshot.append_color(self._solid_color, bounds)
            return

        # The constant black base stays independent from the changing bar textures.
        black = Gdk.RGBA()
        black.parse(DEFAULT_FILL)
        snapshot.append_color(black, bounds)
        if self._frame:
            self._snapshot_glow(snapshot, width, height)

    def _bar_depths(self, width: int, height: int) -> tuple[float, float]:
        aspect = self._video_aspect_ratio()
        return (width - height * aspect) / 2, (height - width / aspect) / 2

    def _snapshot_glow(self, snapshot: Gtk.Snapshot, width: int, height: int) -> None:
        sample_width = BACKGROUND_SAMPLE_SIZE
        last = sample_width - 1
        horizontal_depth, vertical_depth = self._bar_depths(width, height)

        if horizontal_depth >= MIN_BAR_DEPTH:
            left, right = horizontal_depth, width - horizontal_depth
            self._append_bar(snapshot, (left, 0), (0, height), (-left, 0), 0, 1, sample_width)
            self._append_bar(snapshot, (right, 0), (0, height), (left, 0), last, -1, sample_width)
        elif vertical_depth >= MIN_BAR_DEPTH:
            top, bottom = vertical_depth, height - vertical_depth
            self._append_bar(snapshot, (0, top), (width, 0), (0, -top), 0, sample_width, 1)
            self._append_bar(
                snapshot, (0, bottom), (width, 0), (0, top), last * sample_width, -sample_width, 1
            )

    def _append_bar(
        self,
        snapshot: Gtk.Snapshot,
        start: tuple[float, float],
        along: tuple[float, float],
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

        width, depth = BACKGROUND_SAMPLE_SIZE, GLOW_DEPTH_SAMPLES
        pixels = _diffused_strip(edge_colors, self._settings.glow)
        texture = Gdk.MemoryTexture.new(
            width, depth, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(pixels), width * 3
        )
        snapshot.save()
        # Map the strip's width along the video edge and its depth outward into the bar.
        snapshot.transform_matrix(
            Graphene.Matrix().init_from_2d(
                along[0] / width, along[1] / width, outward[0] / depth, outward[1] / depth, *start
            )
        )
        snapshot.append_scaled_texture(
            texture, Gsk.ScalingFilter.LINEAR, Graphene.Rect().init(0, 0, width, depth)
        )
        snapshot.restore()


def _diffused_strip(edge_colors: Sequence[tuple[float, ...]], settings: GlowSettings) -> bytes:
    pixels = bytearray()
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
        for rgb in edge_colors:
            pixels.extend(round(channel * light) for channel in rgb)

    return bytes(pixels)


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
