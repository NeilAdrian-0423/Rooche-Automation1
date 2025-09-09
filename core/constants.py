# In core/constants.py
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs.txt")

DEFAULT_CONFIG = {
    "history_file_path": None,       # file for history logs
    "sharex_exe_path": None,         # ShareX executable
    "whisper_model": "small",        # tiny | base | small | medium | large
    "whisper_device": "auto",        # cpu | cuda | auto
    "wait_timer_minutes": 60,        # idle timeout
    "deeplive_dir": None,            # DeepLive installation directory
    "deeplive_models_dir": None,     # Models directory
    "mouth_mask": False,             # enable mouth mask
    "many_faces": True,              # multi-face support
    "camera_index": 0,               # default camera
    "startup_delay": 3,              # seconds to wait for GUI
    "log_level": "INFO"              # DEBUG | INFO | WARNING | ERROR
}


VALID_AUDIO_VIDEO_EXTENSIONS = [
    '.mp3', '.mp4', '.wav', '.m4a', '.flac', 
    '.ogg', '.webm', '.avi', '.mov', '.wmv'
]