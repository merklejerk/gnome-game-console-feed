import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from gi.repository import GLib

logger = logging.getLogger(__name__)

# Use GLib to get the proper config directory (XDG compliant and Flatpak friendly)
CONFIG_DIR = Path(GLib.get_user_config_dir()) / "game-console-feed"
CONFIG_FILE = CONFIG_DIR / "settings.json"
SAVE_DELAY_MS = 200  # Let a burst of UI changes settle before writing.


class SettingsWriter:
    """Coalesce GTK updates and serialize atomic writes on one worker."""

    def __init__(self) -> None:
        self._worker = ThreadPoolExecutor(max_workers=1)
        self._pending: dict | None = None  # Latest settings snapshot waiting to be written.
        self._timer: int | None = None  # GTK main-context timeout for the pending snapshot.
        self._write: Future[None] | None = None  # Most recent write submitted to the worker.

    def queue(self, config: dict) -> None:
        self._pending = config.copy()
        if self._timer is not None:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(SAVE_DELAY_MS, self._write_when_ready)

    def _write_when_ready(self) -> bool:
        if self._write is not None and not self._write.done():
            return GLib.SOURCE_CONTINUE
        self._timer = None
        self._submit_pending()
        return GLib.SOURCE_REMOVE

    def _submit_pending(self) -> None:
        if self._pending is not None:
            self._write = self._worker.submit(save_config, self._pending)
            self._pending = None

    def close(self) -> None:
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self._submit_pending()
        self._worker.shutdown(wait=True)


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
