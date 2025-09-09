import sys
import ctypes
from ctypes import wintypes
from PyQt6.QtWidgets import QApplication
from core.logging_config import setup_logging
from gui.main_window import MainApplication

def main():
    """Initialize and run the application."""
    # Set DPI awareness
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-2)  # DPI_AWARENESS_CONTEXT_SYSTEM_AWARE
    except Exception as e:
        print(f"Failed to set DPI awareness: {e}")
    
    # Set up logging
    setup_logging()
    
    # Create QApplication
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