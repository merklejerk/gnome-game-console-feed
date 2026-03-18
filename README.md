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

Flatpak is the recommended way to run Game Console Feed. Pre-built bundles are available for every release.

1. **Download**: Grab the latest `.flatpak` bundle from the [Releases](https://github.com/merklejerk/gnome-game-console-feed/releases) page.
2. **Install**:
   ```bash
   flatpak install --user GameConsoleFeed.flatpak
   ```
3. **Run**:
   ```bash
   flatpak run io.github.merklejerk.GameConsoleFeed
   ```

### Manual Installation (via uv)

If you prefer to run from source, this project requires [uv](https://docs.astral.sh/uv/) for Python package management.

**System Requirements**:
You must have the following libraries installed on your host system:
- `libadwaita-1`
- `gstreamer1.0-plugins-good`
- `v4l-utils`
- `alsa-utils`

**Setup & Run**:
```bash
# Clone and sync environment
git clone https://github.com/merklejerk/gnome-game-console-feed.git
cd gnome-game-console-feed
uv sync

# Launch the app
uv run app
```

## Development

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
