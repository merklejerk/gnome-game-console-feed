from game_console_feed import main


def test_startup_reports_unsupported_libraries_before_creating_a_window(monkeypatch, capsys):
    monkeypatch.setattr(main.Gtk, "get_major_version", lambda: main.MIN_GTK[0])
    monkeypatch.setattr(main.Gtk, "get_minor_version", lambda: main.MIN_GTK[1] - 1)
    monkeypatch.setattr(main.Adw, "get_major_version", lambda: main.MIN_ADWAITA[0])
    monkeypatch.setattr(main.Adw, "get_minor_version", lambda: main.MIN_ADWAITA[1] - 1)
    monkeypatch.setattr(
        main.Gst, "version", lambda: (main.MIN_GSTREAMER[0], main.MIN_GSTREAMER[1] - 1, 0, 0)
    )

    assert main.main() == 1
    errors = capsys.readouterr().err.splitlines()
    for error, name in zip(errors, ("GTK", "Libadwaita", "GStreamer"), strict=True):
        assert f"Game Console Feed: {name}" in error and "or newer required" in error
