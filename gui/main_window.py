"""Main application window."""

import os
import sys
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
    QVBoxLayout, QWidget
)
from PyQt6.QtCore import Qt
from dotenv import load_dotenv

from core.config import ConfigManager
from services.audio_processor import AudioProcessor
from services.calendar_service import CalendarService
from services.sharex_service import ShareXService
from services.webhook_service import WebhookService
from services.monitoring_service import MonitoringService
from services.deep_live_service import DeepLiveService

from gui.calendar_tab import CalendarTab
from gui.manual_tab import ManualTab
# from gui.deep_live_cam_tab import DeepLiveCamTab

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)


class MainApplication(QMainWindow):
    def __init__(self):
        super().__init__()

        # Initialize services
        self.config_manager = ConfigManager()
        try:
            self.config_manager.load()  # 👈 make sure config values are loaded from file
            logger.info("Config loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

        self.audio_processor = AudioProcessor(self.config_manager)
        self.calendar_service = CalendarService()  # change to CalendarService(self.config_manager) if it requires config
        self.sharex_service = ShareXService(self.config_manager)
        self.webhook_service = WebhookService()
        self.monitoring_service = MonitoringService(
            self.config_manager,
            self.audio_processor,
            self.webhook_service
        )

        # Shared DeepLive service (so tabs can use it)
        self.deep_live_service = DeepLiveService()

        # Setup main window
        self.setWindowTitle("Calendar-Integrated ShareX Monitor")
        self.setGeometry(100, 100, 700, 900)

        # Create UI
        self.create_ui()

        # Debug: log loaded config values
        logger.info("Loaded config values at startup: %s", {
            "mouth_mask": self.config_manager.get("mouth_mask"),
            "many_faces": self.config_manager.get("many_faces"),
            "camera_index": self.config_manager.get("camera_index"),
            "deeplive_dir": self.config_manager.get("deeplive_dir"),
            "deeplive_models_dir": self.config_manager.get("deeplive_models_dir"),
            "history_path": self.config_manager.get("history_path"),
            "sharex_exe_path": self.config_manager.get("sharex_exe_path"),
            "wait_timer_minutes": self.config_manager.get("wait_timer_minutes"),
            "startup_delay": self.config_manager.get("startup_delay"),
        })

    def create_ui(self):
        """Create the main UI."""
        # Central widget + layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Calendar tab
        self.calendar_tab = CalendarTab(
            self.tab_widget,
            self.calendar_service,
            self.sharex_service,
            self.webhook_service,
            self.monitoring_service,
            self.audio_processor,
            self.deep_live_service  # 👈 pass shared service
        )

        # Manual tab
        self.manual_tab = ManualTab(
            self.tab_widget,
            self.config_manager,
            self.sharex_service,
            self.audio_processor,
            self.webhook_service,
            self.calendar_tab
        )

        # Optional Deep Live Cam tab (if you want later)
        # self.deep_live_cam_tab = DeepLiveCamTab(
        #     self.tab_widget,
        #     self.config_manager
        # )

        # Add tabs
        self.tab_widget.addTab(self.calendar_tab, "📅 Calendar Events")
        self.tab_widget.addTab(self.manual_tab, "📁 Manual Files")
        # self.tab_widget.addTab(self.deep_live_cam_tab, "🎥 Deep Live Cam")

    def closeEvent(self, event):
        """Stop Deep Live safely when closing."""
        try:
            if self.deep_live_service:
                self.deep_live_service.stop_deeplive()
                logger.info("Deep Live terminated on exit")
        except Exception as e:
            logger.error(f"Error shutting down Deep Live: {e}")
        finally:
            event.accept()
