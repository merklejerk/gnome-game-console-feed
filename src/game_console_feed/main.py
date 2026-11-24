import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gst", "1.0")

from gi.repository import Adw, Gio, Gst, Gtk  # noqa: E402

from game_console_feed.window import ConsoleWindow  # noqa: E402

MIN_GTK = (4, 10)
MIN_ADWAITA = (1, 5)
MIN_GSTREAMER = (1, 24)


def _unsupported_runtime() -> list[str]:
    """Check the versions that supply the app's GTK and GStreamer APIs."""
    libraries = (
        ("GTK", (Gtk.get_major_version(), Gtk.get_minor_version()), MIN_GTK),
        ("Libadwaita", (Adw.get_major_version(), Adw.get_minor_version()), MIN_ADWAITA),
        ("GStreamer", Gst.version()[:2], MIN_GSTREAMER),
    )
    return [
        f"{name} {minimum[0]}.{minimum[1]} or newer required (found {found[0]}.{found[1]})"
        for name, found, minimum in libraries
        if found < minimum
    ]


class ConsoleApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.merklejerk.GameConsoleFeed",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = ConsoleWindow(application=self)
        win.present()


def main() -> int:
    Gst.init(None)
    issues = _unsupported_runtime()
    if issues:
        for issue in issues:
            print(f"Game Console Feed: {issue}", file=sys.stderr)
        return 1
    app = ConsoleApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
