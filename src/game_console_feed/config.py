import json
import logging
from pathlib import Path

from gi.repository import GLib

logger = logging.getLogger(__name__)

# Use GLib to get the proper config directory (XDG compliant and Flatpak friendly)
CONFIG_DIR = Path(GLib.get_user_config_dir()) / "game-console-feed"
CONFIG_FILE = CONFIG_DIR / "settings.json"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}


def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving config: {e}")
