"""Core module for configuration and logging."""

from .config import ConfigManager
from .logging_config import setup_logging
from .constants import (
    CONFIG_FILE,
    LOG_FILE,
    DEFAULT_CONFIG,
    VALID_AUDIO_VIDEO_EXTENSIONS
)

__all__ = [
    'ConfigManager',
    'setup_logging',
    'CONFIG_FILE',
    'LOG_FILE',
    'DEFAULT_CONFIG',
    'VALID_AUDIO_VIDEO_EXTENSIONS'
]