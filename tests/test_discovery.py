from unittest.mock import patch

from game_console_feed.discovery import get_matching_alsa_device


@patch("subprocess.check_output")
def test_get_matching_alsa_device_found_strict(mock_check_output):
    mock_check_output.return_value = """
**** List of CAPTURE Hardware Devices ****
card 0: C200 [Anker PowerConf C200], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 4: Video [C3A USB3 Video], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
"""
    # Strict matching should pick card 0 for Anker
    device = get_matching_alsa_device("/dev/video0", "Anker PowerConf C200: Anker Pow (usb...)")
    assert device == "hw:0"

    # Strict matching should pick card 4 for C3A
    device = get_matching_alsa_device("/dev/video2", "C3A USB3 Video: C3A USB3 Video (usb...)")
    assert device == "hw:4"


@patch("subprocess.check_output")
def test_get_matching_alsa_device_fallback(mock_check_output):
    mock_check_output.return_value = """
**** List of CAPTURE Hardware Devices ****
card 1: PCH [HDA Intel PCH], device 0: ALC892 Analog [ALC892 Analog]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 2: Video [Generic Capture Video], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
"""
    # Should fallback to 'Video' keyword match (card 2) because name doesn't match
    device = get_matching_alsa_device("/dev/nonexistent", "Unknown Card")
    assert device == "hw:2"


@patch("subprocess.check_output")
def test_get_matching_alsa_device_not_found(mock_check_output):
    mock_check_output.side_effect = FileNotFoundError()
    device = get_matching_alsa_device("/dev/nonexistent", "Unknown")
    assert device == "hw:Video"
