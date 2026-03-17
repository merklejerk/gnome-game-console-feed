import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gst", "1.0")

from gi.repository import Adw, Gio, Gst  # noqa: E402

from game_console_feed.window import ConsoleWindow  # noqa: E402


class ConsoleApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.github.game_console_feed",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = ConsoleWindow(application=self)
        win.present()


def main():
    Gst.init(None)
    app = ConsoleApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
