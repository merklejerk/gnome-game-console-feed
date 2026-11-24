from threading import Event, get_ident
from time import monotonic, sleep
from unittest import mock

import pytest
from gi.repository import GLib

from game_console_feed.config import SettingsWriter, load_config, save_config


@pytest.fixture
def mock_config_dir(tmp_path):
    with mock.patch("game_console_feed.config.CONFIG_DIR", tmp_path):
        with mock.patch("game_console_feed.config.CONFIG_FILE", tmp_path / "settings.json"):
            yield tmp_path


def test_load_config_empty(mock_config_dir):
    assert load_config() == {}


def test_save_and_load_config(mock_config_dir):
    config = {"last_device_id": "/dev/video0", "audio_muted": True}
    save_config(config)
    assert load_config() == config

    save_config({"audio_muted": False})
    assert load_config() == {"audio_muted": False}


def test_load_config_requires_an_object(mock_config_dir):
    (mock_config_dir / "settings.json").write_text("[]", encoding="utf-8")
    assert load_config() == {}


def test_save_config_updates_a_linked_settings_file(mock_config_dir):
    settings = mock_config_dir / "settings.json"
    target = mock_config_dir / "linked.json"
    settings.symlink_to(target)

    save_config({"audio_muted": False})

    assert settings.is_symlink()
    assert load_config() == {"audio_muted": False}


def test_settings_writer_flushes_only_the_latest_pending_settings_on_close(mock_config_dir):
    writer = SettingsWriter()
    try:
        writer.queue({"audio_muted": True})
        writer.queue({"audio_muted": False, "volume": 1.0})
        assert load_config() == {}
    finally:
        writer.close()

    assert load_config() == {"audio_muted": False, "volume": 1.0}


def test_settings_writer_writes_off_the_main_thread(monkeypatch):
    main_thread = get_ident()
    written = Event()
    writes: list[tuple[int, dict]] = []

    def record_write(config: dict) -> None:
        writes.append((get_ident(), config))
        written.set()

    monkeypatch.setattr("game_console_feed.config.save_config", record_write)
    writer = SettingsWriter()
    try:
        writer.queue({"volume": 1.0})
        writer.queue({"volume": 1.5})
        context = GLib.MainContext.default()
        deadline = monotonic() + 2
        while not written.is_set():
            assert monotonic() < deadline, "Timed out waiting for the settings writer"
            context.iteration(False)
            sleep(0.005)
        [(worker_thread, config)] = writes
        assert worker_thread != main_thread
        assert config == {"volume": 1.5}
    finally:
        writer.close()
