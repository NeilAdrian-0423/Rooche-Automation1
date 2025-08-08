"""Configuration management module."""

import json
import os
from typing import Dict, Any
from .constants import CONFIG_FILE, DEFAULT_CONFIG

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load()
    
    def load(self) -> None:
        """Load configuration from file."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded = json.load(f)
                    self.config.update(loaded)
            except Exception as e:
                print(f"[Config] Failed to load config: {e}")
    
    def save(self) -> None:
        """Save configuration to file."""
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self.config[key] = value
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple configuration values."""
        self.config.update(updates)