"""Calendar events tab."""

import os
import time
import subprocess
from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QLineEdit, QGroupBox, QFileDialog, QMessageBox,
    QScrollArea, QFrame, QDialog, QDialogButtonBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

from PyQt6.QtGui import QFont

from .dialogs import PassFailDialog, WaitForUploadDialog
from utils.helpers import extract_notion_url

class CalendarRefreshThread(QThread):
    """Thread for refreshing calendar events."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, calendar_service):
        super().__init__()
        self.calendar_service = calendar_service
    
    def run(self):
        try:
            events = self.calendar_service.fetch_events()
            self.finished.emit(events if events else [])
        except Exception as e:
            self.error.emit(str(e))

class SettingsDialog(QDialog):
    """Dialog for configuration settings."""
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Settings")
        self.setMinimumWidth(200)
        self.ui_elements = {}
        self.create_ui()
    
    def create_ui(self):
        """Create the settings dialog UI."""
        layout = QVBoxLayout(self)
        
        # Configuration section
        config_group = QGroupBox("Configuration")
        config_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        config_layout = QVBoxLayout()
        
        config_layout.addWidget(QLabel("Time Limit (minutes):"))
        self.ui_elements['timer_entry'] = QLineEdit()
        self.ui_elements['timer_entry'].setText(str(self.config_manager.get("wait_timer_minutes", 60)))
        self.ui_elements['timer_entry'].setMaximumWidth(100)
        config_layout.addWidget(self.ui_elements['timer_entry'])
        
        config_layout.addWidget(QLabel("Whisper Model:"))
        self.ui_elements['model_entry'] = QLineEdit()
        self.ui_elements['model_entry'].setText(self.config_manager.get("whisper_model", "base"))
        self.ui_elements['model_entry'].setMaximumWidth(100)
        config_layout.addWidget(self.ui_elements['model_entry'])
        
        config_layout.addWidget(QLabel("Device:"))
        self.ui_elements['device_entry'] = QLineEdit()
        self.ui_elements['device_entry'].setText(self.config_manager.get("whisper_device", "cpu"))
        self.ui_elements['device_entry'].setMaximumWidth(100)
        config_layout.addWidget(self.ui_elements['device_entry'])
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # File selection buttons
        file_buttons_row = QHBoxLayout()
        
        self.ui_elements['select_history_button'] = QPushButton("📁 Select ShareX History")
        self.ui_elements['select_history_button'].clicked.connect(self.select_history_file)
        file_buttons_row.addWidget(self.ui_elements['select_history_button'])
        
        self.ui_elements['select_sharex_button'] = QPushButton("🎯 Select ShareX.exe")
        self.ui_elements['select_sharex_button'].setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-size: 9pt;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.ui_elements['select_sharex_button'].clicked.connect(self.select_sharex_exe)
        file_buttons_row.addWidget(self.ui_elements['select_sharex_button'])
        
        layout.addLayout(file_buttons_row)
        
        # OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def select_history_file(self):
        """Select ShareX history file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ShareX history.json",
            "",
            "JSON Files (*.json)"
        )
        if path:
            self.config_manager.set("history_path", path)
            self.parent().update_file_labels()
            self.parent().update_submit_button_state()
            self.config_manager.save()
    
    def select_sharex_exe(self):
        """Select ShareX executable file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ShareX.exe",
            "",
            "Executable Files (*.exe);;All Files (*.*)"
        )
        if path:
            self.config_manager.set("sharex_exe_path", path)
            self.parent().update_file_labels()
            self.parent().update_submit_button_state()
            self.config_manager.save()
    
    def accept(self):
        """Save settings when OK is clicked."""
        try:
            wait_minutes = int(self.ui_elements['timer_entry'].text().strip())
            if wait_minutes <= 0:
                QMessageBox.critical(self, "Error", "Time limit must be greater than 0 minutes.")
                return
            self.config_manager.set("wait_timer_minutes", wait_minutes)
            self.config_manager.set("whisper_model", self.ui_elements['model_entry'].text().strip())
            self.config_manager.set("whisper_device", self.ui_elements['device_entry'].text().strip())
            self.config_manager.save()
            super().accept()
        except ValueError:
            QMessageBox.critical(self, "Error", "Please enter a valid number for time limit.")

class CalendarTab(QWidget):
    def __init__(self, parent, config_manager, calendar_service, sharex_service, 
                 webhook_service, monitoring_service, audio_processor):
        super().__init__(parent)
        self.config_manager = config_manager
        self.calendar_service = calendar_service
        self.sharex_service = sharex_service
        self.webhook_service = webhook_service
        self.monitoring_service = monitoring_service
        self.audio_processor = audio_processor
        
        self.ui_elements = {}
        self.event_data = []
        self.current_monitoring_params = None
        self.create_ui()
        
        # Auto-load calendar events on startup
        QTimer.singleShot(1000, self.refresh_calendar_events)
    
    def create_ui(self):
        """Create the calendar tab UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create scrollable area for the content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        
        # Container widget for scroll area
        container = QWidget()
        scroll_area.setWidget(container)
        layout = QVBoxLayout(container)
        
        # Calendar events section
        title_label = QLabel("Upcoming Calendar Events:")
        title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        layout.addWidget(title_label)
        
        # Calendar events listbox - MADE SMALLER
        self.cal_listbox = QListWidget()
        self.cal_listbox.setMaximumHeight(150)  # Smaller height
        self.cal_listbox.setFont(QFont("Arial", 9))
        self.cal_listbox.itemSelectionChanged.connect(self.on_calendar_select)
        layout.addWidget(self.cal_listbox)
        
        # Calendar refresh and settings buttons row
        button_row = QHBoxLayout()
        
        self.cal_refresh_button = QPushButton("🔄 Refresh Calendar Events")
        self.cal_refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 10pt;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.cal_refresh_button.clicked.connect(self.refresh_calendar_events)
        button_row.addWidget(self.cal_refresh_button)
        
        self.settings_button = QPushButton("⚙️ Settings")
        self.settings_button.setStyleSheet("""
            QPushButton {
                background-color: #666666;
                color: white;
                font-size: 10pt;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
        """)
        self.settings_button.clicked.connect(self.show_settings_dialog)
        button_row.addWidget(self.settings_button)
        
        layout.addLayout(button_row)
        
        # Auto-filled form section
        form_group = QGroupBox("Meeting Details (Auto-filled)")
        form_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        form_layout = QVBoxLayout()
        
        form_layout.addWidget(QLabel("Notion URL:"))
        self.ui_elements['notion_entry'] = QLineEdit()
        self.ui_elements['notion_entry'].setFont(QFont("Arial", 9))
        form_layout.addWidget(self.ui_elements['notion_entry'])
        
        form_layout.addWidget(QLabel("Description:"))
        self.ui_elements['description_entry'] = QLineEdit()
        self.ui_elements['description_entry'].setFont(QFont("Arial", 9))
        form_layout.addWidget(self.ui_elements['description_entry'])
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: blue; font-size: 10pt;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        # File labels section
        self.create_file_labels(layout)
        self.history_file_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.sharex_exe_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # Create control buttons
        self.create_control_buttons(layout)
        
        # Info section
        self.create_info_section(layout)
        
        # Initialize file labels
        self.update_file_labels()
        self.update_submit_button_state()
    
    def show_settings_dialog(self):
        """Show the settings dialog."""
        dialog = SettingsDialog(self, self.config_manager)
        dialog.exec()
    
    def create_file_labels(self, parent_layout):
        """Create file status labels."""
        # ShareX history file label
        self.history_file_label = QLabel("No ShareX history file selected")
        self.history_file_label.setStyleSheet("color: gray;")
        parent_layout.addWidget(self.history_file_label)
        
        # ShareX executable label
        self.sharex_exe_label = QLabel("No ShareX executable selected")
        self.sharex_exe_label.setStyleSheet("color: gray;")
        parent_layout.addWidget(self.sharex_exe_label)
    
    def create_control_buttons(self, parent_layout):
        """Create control buttons."""
        # Main control buttons row
        control_row = QHBoxLayout()
        
        self.ui_elements['submit_button'] = QPushButton("🚀 Start Monitoring + Recording")
        self.ui_elements['submit_button'].setEnabled(False)
        self.ui_elements['submit_button'].setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 10pt;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:hover:enabled {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.ui_elements['submit_button'].clicked.connect(self.handle_submission)
        control_row.addWidget(self.ui_elements['submit_button'])
        
        self.ui_elements['reset_button'] = QPushButton("🛑 Stop All")
        self.ui_elements['reset_button'].setEnabled(False)
        self.ui_elements['reset_button'].setStyleSheet("""
            QPushButton {
                background-color: #FF5722;
                color: white;
                font-size: 9pt;
                padding: 5px;
            }
            QPushButton:hover:enabled {
                background-color: #E64A19;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.ui_elements['reset_button'].clicked.connect(self.stop_monitoring)
        control_row.addWidget(self.ui_elements['reset_button'])
        
        parent_layout.addLayout(control_row)
        
        # Pass/Fail button row
        self.ui_elements['pass_fail_button'] = QPushButton("✅❌ Submit Pass/Fail Result")
        self.ui_elements['pass_fail_button'].setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                font-size: 10pt;
                font-weight: bold;
                padding: 5px 20px;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
            }
        """)
        self.ui_elements['pass_fail_button'].clicked.connect(self.handle_pass_fail)
        parent_layout.addWidget(self.ui_elements['pass_fail_button'], alignment=Qt.AlignmentFlag.AlignCenter)
    
    def create_info_section(self, parent_layout):
        """Create info sections."""
        # Info frame
        info_group = QGroupBox("ℹ️ How to Use")
        info_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        info_layout = QVBoxLayout()
        
        info_text = QLabel(
            "1. Click 'Refresh Calendar Events' to load your meetings\n"
            "2. Select a meeting from the list (upcoming meetings are highlighted)\n" 
            "3. Notion URL and description will auto-fill\n"
            "4. Configure settings using the ⚙️ Settings button\n"
            "5. Click 'Start Monitoring + Recording' to launch ShareX and begin recording\n"
            "6. When you upload an audio/video file, it will auto-transcribe and send to your webhook\n"
            "7. Click 'Stop All' to choose whether to wait for upload or stop completely\n"
            "8. Or use 'Submit Pass/Fail Result' to report meeting outcomes directly\n\n"
            "⚡ Meetings starting within 30 minutes are automatically highlighted and selected!\n"
            "🎯 ShareX will be launched automatically and screen recording will start with a 3-second delay"
        )
        info_text.setStyleSheet("color: gray; font-size: 8pt;")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        
        info_group.setLayout(info_layout)
        parent_layout.addWidget(info_group)
    
    def launch_sharex_and_start_recording(self):
        """Launch ShareX and trigger screen recording."""
        sharex_path = self.config_manager.get("sharex_exe_path")
        if not sharex_path or not os.path.exists(sharex_path):
            self.status_label.setText("❌ ShareX executable not found!")
            return False
        
        try:
            # Launch ShareX
            self.status_label.setText("🚀 Launching ShareX...")
            subprocess.Popen([sharex_path], shell=True)
            
            # Wait a moment for ShareX to fully load
            time.sleep(3)
            
            # Trigger screen recording using Shift+PrintScreen
            self.status_label.setText("🎥 Starting screen recording (Shift+PrintScreen)...")
            if self.sharex_service.trigger_recording():
                self.status_label.setText("✅ ShareX launched and screen recording started! Monitoring for uploads...")
                return True
            else:
                self.status_label.setText("⚠️ ShareX launched but recording trigger may have failed. Monitoring for uploads...")
                return True  # Continue anyway as ShareX is running
                
        except Exception as e:
            self.status_label.setText(f"❌ Failed to launch ShareX: {str(e)}")
            return False
    
    def update_file_labels(self):
        """Update file status labels."""
        # ShareX history file
        history_path = self.config_manager.get("history_path")
        if history_path and os.path.exists(history_path):
            self.history_file_label.setText(f"✅ History: {os.path.basename(history_path)}")
            self.history_file_label.setStyleSheet("color: green;")
        else:
            self.history_file_label.setText("❌ No ShareX history file selected")
            self.history_file_label.setStyleSheet("color: red;")
        
        # ShareX executable
        sharex_path = self.config_manager.get("sharex_exe_path")
        if sharex_path and os.path.exists(sharex_path):
            self.sharex_exe_label.setText(f"✅ ShareX: {os.path.basename(sharex_path)}")
            self.sharex_exe_label.setStyleSheet("color: green;")
        else:
            self.sharex_exe_label.setText("❌ No ShareX executable selected")
            self.sharex_exe_label.setStyleSheet("color: red;")
    
    def refresh_calendar_events(self):
        """Refresh the calendar events list."""
        self.cal_refresh_button.setText("Refreshing...")
        self.cal_refresh_button.setEnabled(False)
        
        # Create and start the refresh thread
        self.refresh_thread = CalendarRefreshThread(self.calendar_service)
        self.refresh_thread.finished.connect(self.on_events_loaded)
        self.refresh_thread.error.connect(self.on_events_error)
        self.refresh_thread.start()
    
    def on_events_loaded(self, events):
        """Handle loaded events."""
        self.cal_listbox.clear()
        self.event_data = events
        
        if events:
            upcoming_index = -1
            for i, event in enumerate(events):
                display_text = event['display_text']
                
                # Highlight upcoming meetings
                if event['is_upcoming']:
                    minutes_until = int(event['time_until'] / 60)
                    display_text += f" [STARTING IN {minutes_until} MIN!]"
                    if upcoming_index == -1:
                        upcoming_index = i
                
                self.cal_listbox.addItem(display_text)
            
            # Auto-select the most upcoming meeting
            if upcoming_index >= 0:
                self.cal_listbox.setCurrentRow(upcoming_index)
                self.auto_fill_from_selection()
        else:
            self.cal_listbox.addItem("No calendar events found")
        
        self.cal_refresh_button.setText("🔄 Refresh Calendar Events")
        self.cal_refresh_button.setEnabled(True)
    
    def on_events_error(self, error_msg):
        """Handle event loading error."""
        self.cal_listbox.clear()
        self.cal_listbox.addItem(f"Error loading events: {error_msg}")
        self.event_data = []
        self.cal_refresh_button.setText("🔄 Refresh Calendar Events")
        self.cal_refresh_button.setEnabled(True)
    
    def on_calendar_select(self):
        """Handle calendar selection."""
        self.auto_fill_from_selection()
    
    def auto_fill_from_selection(self):
        """Auto-fill form fields based on selected calendar event."""
        current_row = self.cal_listbox.currentRow()
        if current_row < 0 or current_row >= len(self.event_data):
            return
        
        event = self.event_data[current_row]
        
        # Auto-fill Notion URL
        notion_url = extract_notion_url(event['notion_url'])
        self.ui_elements['notion_entry'].setText(notion_url)
        
        # Auto-fill description
        self.ui_elements['description_entry'].setText(event['auto_description'])
    
    def update_submit_button_state(self):
        """Update submit button state based on configuration."""
        history_ok = self.config_manager.get("history_path") and os.path.exists(self.config_manager.get("history_path"))
        sharex_ok = self.config_manager.get("sharex_exe_path") and os.path.exists(self.config_manager.get("sharex_exe_path"))
        webhook_ok = os.getenv("WEBHOOK_URL", "").strip()
        
        if history_ok and sharex_ok and webhook_ok:
            self.ui_elements['submit_button'].setEnabled(True)
        else:
            self.ui_elements['submit_button'].setEnabled(False)
    
    def enable_ui_elements(self, enable=True):
        """Enable or disable UI elements."""
        for key in ['notion_entry', 'description_entry', 'submit_button', 'pass_fail_button']:
            self.ui_elements[key].setEnabled(enable)
        
        self.ui_elements['reset_button'].setEnabled(not enable)
        self.settings_button.setEnabled(enable)
    
    def handle_submission(self):
        """Handle monitoring submission."""
        notion_url = self.ui_elements['notion_entry'].text().strip()
        description = self.ui_elements['description_entry'].text().strip()
        
        if not notion_url or not description:
            QMessageBox.critical(self, "Error", "Please enter both Notion URL and description.")
            return
        
        if not self.config_manager.get("history_path"):
            QMessageBox.critical(self, "Error", "No ShareX history.json selected.")
            return
        
        if not self.config_manager.get("sharex_exe_path"):
            QMessageBox.critical(self, "Error", "No ShareX executable selected.")
            return
        
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()
        if not webhook_url:
            QMessageBox.critical(self, "Error", "Webhook URL not set in .env file.")
            return
        
        # Note: Time limit is now validated in SettingsDialog
        wait_minutes = self.config_manager.get("wait_timer_minutes", 60)
        
        submit_time = datetime.now(timezone.utc).astimezone()
        
        self.enable_ui_elements(False)
        
        # Launch ShareX and start recording
        if not self.launch_sharex_and_start_recording():
            self.enable_ui_elements(True)
            return
        
        def on_transcription_complete(transcription, drive_url, local_file_path):
            self.status_label.setText("✅ Transcription sent to webhook!")
        
        def status_update(message):
            self.status_label.setText(message)
        
        def on_monitoring_complete():
            self.enable_ui_elements(True)
            self.current_monitoring_params = None
        
        status_update(f"🚀 Starting monitoring with {wait_minutes} minute time limit...")
        
        # Store monitoring parameters for potential resume
        self.current_monitoring_params = {
            'submit_time': submit_time,
            'wait_minutes': wait_minutes,
            'notion_url': notion_url,
            'description': description,
            'on_transcription_complete': on_transcription_complete,
            'status_update': status_update,
            'on_monitoring_complete': on_monitoring_complete
        }
        
        self.monitoring_service.start_monitoring(
            submit_time,
            wait_minutes,
            notion_url,
            description,
            on_transcription_complete,
            status_update,
            on_monitoring_complete
        )
    
    def stop_monitoring(self):
        """Stop monitoring process with user confirmation."""
        dialog = WaitForUploadDialog(self)
        result = dialog.show()
        
        if result == "wait":
            # Continue monitoring - just update the status
            self.status_label.setText("⏳ Continuing to wait for Google Drive upload...")
            # Keep Stop All button enabled, monitoring continues
        elif result == "stop":
            # Stop monitoring completely
            self.monitoring_service.stop_monitoring()
            
            # Stop ShareX recording
            if self.sharex_service.stop_recording():
                self.status_label.setText("🛑 Monitoring stopped & ShareX recording stopped")
            else:
                self.status_label.setText("🛑 Monitoring stopped")
            
            self.enable_ui_elements(True)
            self.current_monitoring_params = None
    
    def handle_pass_fail(self):
        """Handle pass/fail submission."""
        notion_url = self.ui_elements['notion_entry'].text().strip()
        description = self.ui_elements['description_entry'].text().strip()
        
        if not notion_url or not description:
            QMessageBox.critical(
                self, 
                "Error", 
                "Please enter both Notion URL and description before submitting pass/fail."
            )
            return
        
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()
        if not webhook_url:
            QMessageBox.critical(self, "Error", "Webhook URL not set in .env file.")
            return
        
        # Show pass/fail dialog
        dialog = PassFailDialog(self)
        result, reason = dialog.show()
        
        if result and reason:
            self.status_label.setText("📤 Sending pass/fail result...")
            
            success = self.webhook_service.send_data(
                notion_url=notion_url,
                description=description,
                result=result,
                reason=reason
            )
            
            if success:
                self.status_label.setText(f"✅ {result.title()} result sent successfully!")
            else:
                self.status_label.setText("❌ Failed to send pass/fail result")
        else:
            self.status_label.setText("❌ Pass/fail submission cancelled")