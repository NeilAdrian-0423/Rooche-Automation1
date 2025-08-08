"""Application constants and configuration defaults."""

CONFIG_FILE = "config.json"
LOG_FILE = "logs.txt"

DEFAULT_CONFIG = {
    "history_path": None,
    "whisper_model": "base",
    "whisper_device": "cpu",
    "wait_timer_minutes": 60,
}

VALID_AUDIO_VIDEO_EXTENSIONS = [
    '.mp3', '.mp4', '.wav', '.m4a', '.flac', 
    '.ogg', '.webm', '.avi', '.mov', '.wmv'
]