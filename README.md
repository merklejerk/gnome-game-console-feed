# Game Console Feed

![screenshot](/screenshot.png)

Game Console Feed is a native Linux utility designed to display a low-latency video and audio feed from a UVC-compliant capture card. It is built using GTK4, Libadwaita, and GStreamer to provide a "windowed" gaming experience that feels like a native OS component.

This application is specifically optimized for playing game consoles (like the Nintendo Switch, PlayStation, or Xbox) in a desktop window without the overhead of complex streaming software like OBS.

## Features

- **Low Latency:** Uses GStreamer with non-synchronized sinks to prioritize real-time frames.
- **Hardware Topology Pairing:** Robustly pairs video nodes with their corresponding ALSA audio nodes by tracking physical hardware bus addresses (sysfs).
- **Auto-Snapping:** Automatically calculates and resizes the window to match the native aspect ratio of the incoming feed.
- **Persistent Settings:** Remembers your last-used device, volume level, and mute status.
- **Native Integration:** Follows system dark/light mode preferences and uses standard GNOME design patterns.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `s` | Snap window to current feed's aspect ratio |
| `m` | Toggle Mute/Unmute |
| `+` / `=` | Increase Volume (5%) |
| `-` / `_` | Decrease Volume (5%) |
| `F11` | Toggle Fullscreen |
| `Ctrl+Q` / `Ctrl+W` | Quit Application |

## Requirements

### System Dependencies
The application requires the following system-level libraries:
- **Python 3.12+**
- **GTK 4** and **Libadwaita**
- **GStreamer 1.0** (with `v4l2src`, `alsasrc`, and `gtk4paintablesink` elements)
- **v4l-utils** (for `v4l2-ctl` discovery)
- **alsa-utils** (for `arecord` discovery)

On Arch Linux:
```bash
sudo pacman -S python-gobject gtk4 libadwaita gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugin-gtk4 v4l-utils alsa-utils
```

On Fedora/RHEL:
```bash
sudo dnf install python3-gobject gtk4 libadwaita gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-bad-free v4l-utils alsa-utils
```

On Ubuntu/Debian:
```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libgstreamer1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad v4l-utils alsa-utils
```

### Verified Hardware
Successfully tested against the **Dcyfol HDMI to USB 3.0 Video Capture Card** (recognizes as `USB Video` / `C3A USB3 Video`). This is a common, cheap (~$26), generic capture card that supports up to 1080p @ 60fps capture.

## Installation & Usage

This project uses `uv` for modern Python package management.

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd gnome-game-console-feed
   ```

2. **Run the application:**
   ```bash
   uv run app
   ```

3. **Run tests:**
   ```bash
   uv run pytest
   ```

## Technical Notes

- **Aspect Ratio:** The application does not hardcode 16:9. It queries the GdkPaintable's intrinsic dimensions to support any hardware-negotiated resolution (4:3, 16:9, 21:9, etc.).
- **Window Resizing:** Programmatic resizing under Wayland is handled by briefly hiding and re-showing the window to reset compositor-cached bounds.
- **Audio Routing:** Audio is captured directly from the hardware ALSA node and routed to your default system output via GStreamer.
