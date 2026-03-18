# Game Console Feed

![screenshot](/screenshot.png)

Game Console Feed is a native GNOME utility designed for casual console gaming on your Linux desktop. It turns any UVC-compliant capture card into a "native game window," allowing your Nintendo Switch, PlayStation, or Xbox to coexist with your workspace without dedicating an entire monitor to an HDMI input.

## Why this exists

If you've ever tried to use a capture card to play console games in the background while working or using Discord, existing solutions often fall short:
- **Input Swapping is Inconvenient**: Dedicating a hardware HDMI port to your console takes over an entire monitor, making it impossible to use that screen for desktop tasks.
- **Generic Tools have Poor UX**: While powerful, tools like `ffplay`, `mpv`, or `guvcview` often require manual configuration via CLI flags to synchronize audio and video or to set the correct aspect ratio.
- **OBS Studio is Overkill**: OBS is designed for production and streaming; it is unnecessarily complex when you simply want a low-latency window to play a game.

Game Console Feed is a "Just Works" solution. It automatically pairs video and audio feeds, snaps the window to the correct aspect ratio, and provides a native GTK experience.

## Features

- **Automatic Device Pairing**: Discovers capture cards and robustly pairs them with their corresponding ALSA audio nodes using hardware topology.
- **Native GNOME Experience**: Built with GTK4 and Libadwaita for a seamless modern aesthetic.
- **Aspect Ratio Snapping**: A dedicated control to perfectly size the window to the console's output (e.g., 16:9), handling Wayland resizing quirks automatically.
- **Low Latency**: Utilizes a streamlined GStreamer pipeline to ensure minimal input lag.
- **Persistence**: Remembers your last selected device (via unique hardware IDs), volume levels, and mute status across sessions.

## Installation

### Flatpak (Recommended)

Flatpak is the recommended way to run this application as it bundles all necessary GStreamer and hardware utility dependencies.

1. **Build and Install Locally**:
   ```bash
   flatpak-builder --user --install --force-clean build-dir io.github.merklejerk.GameConsoleFeed.yaml
   ```

2. **Run**:
   ```bash
   flatpak run io.github.merklejerk.GameConsoleFeed
   ```

### Manual Installation

To run natively, ensure your system has the following dependencies:
- **Python**: 3.12+
- **Libraries**: `PyGObject` (3.50.1+), `libadwaita-1`
- **GStreamer**: `gstreamer1.0-plugins-good`
- **Utilities**: `v4l-utils`, `alsa-utils`

```bash
pip install .
game-console-feed
```

## Development

This project uses [uv](https://docs.astral.sh/uv/) for Python package management.

### Setup
```bash
uv sync
```

### Running from source
```bash
uv run app
```

### Tests & Linting
```bash
# Run tests
uv run pytest

# Check types
uv run mypy .

# Lint and Format
uv run ruff check . --fix
uv run ruff format .
```

## How it works

Game Console Feed uses **GStreamer** to construct an efficient media pipeline:
- **Video**: `v4l2src` -> `videoconvert` -> `gtk4paintablesink`
- **Audio**: `alsasrc` -> `audioconvert` -> `audioresample` -> `autoaudiosink`

To solve the issue of shifting device paths (e.g., `/dev/video0` changing to `/dev/video2`), the application performs a hardware topology scan in `/sys` to pair video devices with their associated physical audio cards.

## License

MIT
