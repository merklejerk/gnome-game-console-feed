import json
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
    config = {"last_device_path": "/dev/video0", "audio_muted": True}
    save_config(config)

    loaded = load_config()
    assert loaded == config

    # Ensure it was saved to the correct file
    with open(mock_config_dir / "settings.json", "r") as f:
        data = json.load(f)
        assert data == config
