"""Configuration management module."""

import json
import os
import logging
from typing import Dict, Any, Optional
from threading import Lock
from .constants import CONFIG_FILE, DEFAULT_CONFIG

VALID_WHISPER_MODELS = {"tiny", "base", "small", "medium", "large"}
VALID_WHISPER_DEVICES = {"cpu", "cuda", "auto"}

class ConfigManager:
    def __init__(self):
        """Initialize ConfigManager with default configuration and file lock."""
        self.logger = logging.getLogger(__name__)
        self.config = DEFAULT_CONFIG.copy()
        self._file_lock = Lock()  # Thread-safe file operations
        self.load()

    def load(self) -> None:
        """Load configuration from file."""
        with self._file_lock:
            if not os.path.exists(CONFIG_FILE):
                self.logger.warning(f"[Config] Config file {CONFIG_FILE} not found, using defaults")
                return
            
            try:
                with open(CONFIG_FILE, "r", encoding='utf-8') as f:
                    loaded = json.load(f)
                    if not isinstance(loaded, dict):
                        self.logger.error(f"[Config] Invalid config format in {CONFIG_FILE}: not a dictionary")
                        return
                    self.validate_config(loaded)
                    self.config.update(loaded)
                    self.logger.debug(f"[Config] Loaded configuration from {CONFIG_FILE}")
            except json.JSONDecodeError as e:
                self.logger.error(f"[Config] Failed to parse config file {CONFIG_FILE}: {e}")
            except Exception as e:
                self.logger.error(f"[Config] Unexpected error loading config file {CONFIG_FILE}: {e}")

    def save(self) -> None:
        """Save configuration to file."""
        with self._file_lock:
            try:
                # Ensure the directory exists
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                with open(CONFIG_FILE, "w", encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4)
                self.logger.debug(f"[Config] Saved configuration to {CONFIG_FILE}")
            except Exception as e:
                self.logger.error(f"[Config] Failed to save config file {CONFIG_FILE}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        value = self.config.get(key, default)
        self.logger.debug(f"[Config] Retrieved key '{key}': {value}")
        return value

    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        # Validate specific keys
        if key in ['history_path', 'sharex_exe_path', 'deeplive_dir', 'deeplive_models_dir']:
            if value and not os.path.exists(value):
                self.logger.warning(f"[Config] Path for key '{key}' does not exist: {value}")
        elif key == 'wait_timer_minutes' and isinstance(value, (int, float)) and value <= 0:
            self.logger.warning(f"[Config] Invalid value for '{key}': {value} (must be positive)")
        
        self.config[key] = value
        self.logger.debug(f"[Config] Set key '{key}' to {value}")

    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple configuration values."""
        for key, value in updates.items():
            self.set(key, value)
        self.logger.debug(f"[Config] Updated configuration with {len(updates)} key(s)")


    def validate_config(self, config: Dict[str, Any]) -> None:
        """Validate configuration values and log warnings for invalid entries."""
        
        def check_path(path, check_type, key):
            if path:
                if check_type == "file" and not os.path.isfile(path):
                    self.logger.warning(f"[Config] Invalid file path for '{key}': {path}")
                elif check_type == "dir" and not os.path.isdir(path):
                    self.logger.warning(f"[Config] Invalid directory path for '{key}': {path}")
        
        for key, value in config.items():
            if key in ("history_path", "sharex_exe_path"):
                check_path(value, "file", key)
            
            elif key in ("deeplive_dir", "deeplive_models_dir"):
                check_path(value, "dir", key)
            
            elif key == "wait_timer_minutes":
                if not isinstance(value, (int, float)) or value <= 0:
                    self.logger.warning(f"[Config] Invalid wait_timer_minutes: {value} (must be positive number)")
            
            elif key == "whisper_model":
                if not isinstance(value, str) or value.lower() not in VALID_WHISPER_MODELS:
                    self.logger.warning(f"[Config] Invalid whisper_model: {value} (must be one of {VALID_WHISPER_MODELS})")
            
            elif key == "whisper_device":
                if value not in VALID_WHISPER_DEVICES:
                    self.logger.warning(f"[Config] Invalid whisper_device: {value} (must be one of {VALID_WHISPER_DEVICES})")
            
            elif key in ("mouth_mask", "many_faces"):
                if not isinstance(value, bool):
                    self.logger.warning(f"[Config] Invalid {key}: {value} (must be boolean)")
            
            elif key == "camera_index":
                if value is not None and not isinstance(value, int):
                    self.logger.warning(f"[Config] Invalid camera_index: {value} (must be integer or None)")