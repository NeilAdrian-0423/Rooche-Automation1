"""Main entry point for the application."""

import sys
from PyQt6.QtWidgets import QApplication
from core.logging_config import setup_logging
from gui.main_window import MainApplication

def main():
    """Initialize and run the application."""
    # Set up logging
    setup_logging()
    
    # Create QApplication FIRST (required by PyQt)
    app = QApplication(sys.argv)
    
    # Optional: Set application style
    app.setStyle('Fusion')
    
    # Create and show the main window
    main_window = MainApplication()
    main_window.show()
    
    # Run the event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()