from unittest import mock

import pytest

from game_console_feed.config import load_config, save_config


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
