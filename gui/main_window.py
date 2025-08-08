"""Main application window."""

import os
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, 
    QVBoxLayout, QWidget, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from dotenv import load_dotenv

from core.config import ConfigManager
from services.audio_processor import AudioProcessor
from services.calendar_service import CalendarService
from services.sharex_service import ShareXService
from services.webhook_service import WebhookService
from services.monitoring_service import MonitoringService
from .calendar_tab import CalendarTab
from .manual_tab import ManualTab

# Load environment variables
load_dotenv()

class MainApplication(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Initialize services
        self.config_manager = ConfigManager()
        self.audio_processor = AudioProcessor(self.config_manager)
        self.calendar_service = CalendarService()
        self.sharex_service = ShareXService(self.config_manager)
        self.webhook_service = WebhookService()
        self.monitoring_service = MonitoringService(
            self.config_manager,
            self.audio_processor,
            self.webhook_service
        )
        
        # Setup main window
        self.setWindowTitle("Calendar-Integrated ShareX Monitor")
        self.setGeometry(100, 100, 700, 1000)
        
        # Create UI
        self.create_ui()
    
    def create_ui(self):
        """Create the main UI."""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Create calendar tab
        self.calendar_tab = CalendarTab(
            self.tab_widget,
            self.config_manager,
            self.calendar_service,
            self.sharex_service,
            self.webhook_service,
            self.monitoring_service,
            self.audio_processor
        )
        
        # Create manual tab
        self.manual_tab = ManualTab(
            self.tab_widget,
            self.config_manager,
            self.sharex_service,
            self.audio_processor,
            self.webhook_service,
            self.calendar_tab
        )
        
        # Add tabs to tab widget
        self.tab_widget.addTab(self.calendar_tab, "📅 Calendar Events")
        self.tab_widget.addTab(self.manual_tab, "📁 Manual Files")
    
    def closeEvent(self, event):
        """Handle application close event."""
        # Stop monitoring service if running
        if hasattr(self, 'monitoring_service') and self.monitoring_service:
            self.monitoring_service.stop()
        event.accept()

def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    
    # Set application style (optional)
    app.setStyle('Fusion')
    
    # Create and show main window
    main_window = MainApplication()
    main_window.show()
    
    # Run the application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()