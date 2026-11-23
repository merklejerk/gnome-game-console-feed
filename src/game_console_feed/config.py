import json
import logging
from pathlib import Path

from gi.repository import GLib

logger = logging.getLogger(__name__)

# Use GLib to get the proper config directory (XDG compliant and Flatpak friendly)
CONFIG_DIR = Path(GLib.get_user_config_dir()) / "game-console-feed"
CONFIG_FILE = CONFIG_DIR / "settings.json"


def load_config() -> dict:
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as err:
        logger.error("Error loading config: %s", err)
        return {}
    if not isinstance(config, dict):
        logger.error("Expected a JSON object in %s", CONFIG_FILE)
        return {}
    return config


def save_config(config: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        contents = json.dumps(config, indent=4).encode("utf-8")
        # Resolve a symlink before GLib atomically replaces the file.
        GLib.file_set_contents(str(CONFIG_FILE.resolve()), contents)
    except (OSError, RuntimeError, TypeError, ValueError, GLib.Error) as err:
        logger.error("Error saving config: %s", err)
