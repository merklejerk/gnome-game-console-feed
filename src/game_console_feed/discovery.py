import os
import re
import subprocess
from typing import Dict, List


def get_video_devices() -> List[Dict[str, str]]:
    devices = []
    try:
        # Try v4l2-ctl first for better names
        output = subprocess.check_output(["v4l2-ctl", "--list-devices"], text=True)
        current_name = None
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("/dev/video"):
                if current_name:
                    devices.append({"name": current_name, "path": line})
                    current_name = None
            else:
                current_name = line.rstrip(":")
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback to manual sysfs scan
        v4l_dir = "/sys/class/video4linux"
        if os.path.exists(v4l_dir):
            for dev in sorted(os.listdir(v4l_dir)):
                path = f"/dev/{dev}"
                name_file = os.path.join(v4l_dir, dev, "name")
                name = f"Unknown Device ({path})"
                try:
                    if os.path.exists(name_file):
                        with open(name_file, "r") as f:
                            name = f.read().strip()
                except Exception:
                    pass
                devices.append({"name": name, "path": path})

    return devices


def get_sysfs_parent(device_path: str) -> str:
    """Gets the physical hardware parent directory for a device node."""
    try:
        # e.g., /dev/video2 -> /sys/class/video4linux/video2/device
        # or /sys/class/sound/card4/device
        if device_path.startswith("/dev/"):
            dev_name = os.path.basename(device_path)
            if dev_name.startswith("video"):
                sys_path = f"/sys/class/video4linux/{dev_name}/device"
            else:
                # We don't really handle other /dev nodes directly here
                return ""
        else:
            sys_path = device_path

        if os.path.exists(sys_path):
            real_path = os.path.realpath(sys_path)
            # Return the parent directory of the interface
            # (e.g., strip :1.0 from 6-4:1.0)
            return os.path.dirname(real_path)
    except Exception:
        pass
    return ""


def get_matching_alsa_device(video_device_path: str, video_name: str) -> str:
    """
    Robustly pairs a video device with its corresponding ALSA capture card
    using physical hardware topology (sysfs) first, falling back to name matching.
    """
    video_parent = get_sysfs_parent(video_device_path)

    # Pass 1: Physical Topology Match (The "Senior Dev" Way)
    if video_parent:
        sound_dir = "/sys/class/sound"
        if os.path.exists(sound_dir):
            for entry in os.listdir(sound_dir):
                if entry.startswith("card"):
                    card_parent = get_sysfs_parent(f"/sys/class/sound/{entry}/device")
                    if card_parent and card_parent == video_parent:
                        match = re.search(r"card(\d+)", entry)
                        if match:
                            return f"hw:{match.group(1)}"

    # Pass 2: Strict Name Matching Fallback
    try:
        output = subprocess.check_output(["arecord", "-l"], text=True)
        base_name = video_name.split(":")[0].strip().lower()
        for line in output.splitlines():
            line_lower = line.lower()
            if "card" in line_lower and base_name in line_lower:
                match = re.search(r"card (\d+):", line)
                if match:
                    return f"hw:{match.group(1)}"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Pass 3: Keyword Fallback
    try:
        output = subprocess.check_output(["arecord", "-l"], text=True)
        for line in output.splitlines():
            line_lower = line.lower()
            if "card" in line_lower and ("video" in line_lower or "capture" in line_lower):
                match = re.search(r"card (\d+):", line)
                if match:
                    return f"hw:{match.group(1)}"
    except Exception:
        pass

    return "hw:Video"
