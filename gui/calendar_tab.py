import os
import time
import subprocess
import requests  # Added for webhook request
import json  # Added for parsing webhook response
from datetime import datetime, timezone
from pygrabber.dshow_graph import FilterGraph
import pythoncom
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QLineEdit, QGroupBox, QFileDialog, QMessageBox,
    QScrollArea, QFrame, QDialog, QDialogButtonBox, QSizePolicy, QListWidgetItem,
    QCheckBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QFont, QDesktopServices
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

    
class FileDialogThread(QThread):
    """Thread for handling file/directory selection dialogs."""
    result = pyqtSignal(str)
    
    def __init__(self, parent, dialog_type, title, filter_str=None):
        super().__init__(parent)
        self.dialog_type = dialog_type
        self.title = title
        self.filter_str = filter_str
    
    def run(self):
        if self.dialog_type == "directory":
            path = QFileDialog.getExistingDirectory(
                self.parent(),
                self.title,
                ""
            )
        elif self.dialog_type == "file":
            path, _ = QFileDialog.getOpenFileName(
                self.parent(),
                self.title,
                "",
                self.filter_str
            )
        else:
            path = ""
        self.result.emit(path)
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
        
        config_layout.addWidget(QLabel("DeepLive Directory:"))
        self.ui_elements['deeplive_dir_entry'] = QLineEdit()
        self.ui_elements['deeplive_dir_entry'].setText(self.config_manager.get("deeplive_dir", ""))
        self.ui_elements['deeplive_dir_entry'].setMaximumWidth(200)
        config_layout.addWidget(self.ui_elements['deeplive_dir_entry'])
        
        self.ui_elements['select_deeplive_dir_button'] = QPushButton("📁 Select DeepLive Directory")
        self.ui_elements['select_deeplive_dir_button'].clicked.connect(self.select_deeplive_dir)
        config_layout.addWidget(self.ui_elements['select_deeplive_dir_button'])
        
        config_layout.addWidget(QLabel("Deep Live Models Directory:"))
        self.ui_elements['deeplive_models_dir_entry'] = QLineEdit()
        self.ui_elements['deeplive_models_dir_entry'].setText(self.config_manager.get("deeplive_models_dir", ""))
        self.ui_elements['deeplive_models_dir_entry'].setMaximumWidth(200)
        config_layout.addWidget(self.ui_elements['deeplive_models_dir_entry'])
        
        self.ui_elements['select_deeplive_models_dir_button'] = QPushButton("📁 Select Deep Live Models Directory")
        self.ui_elements['select_deeplive_models_dir_button'].clicked.connect(self.select_deeplive_models_dir)
        config_layout.addWidget(self.ui_elements['select_deeplive_models_dir_button'])
        
        
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


    def select_deeplive_dir(self):
        """Select DeepLive directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select DeepLive Directory",
            ""
        )
        if path:
            self.ui_elements['deeplive_dir_entry'].setText(path)      

    def select_deeplive_models_dir(self):
        """Select Deep Live Models directory."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Deep Live Models Directory",
            ""
        )
        if path:
            self.ui_elements['deeplive_models_dir_entry'].setText(path)
    
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
            
            deeplive_dir = self.ui_elements['deeplive_dir_entry'].text().strip()
            if deeplive_dir and not os.path.isdir(deeplive_dir):
                QMessageBox.critical(self, "Error", "DeepLive directory does not exist.")
                return
                
            deeplive_models_dir = self.ui_elements['deeplive_models_dir_entry'].text().strip()
            if deeplive_models_dir and not os.path.isdir(deeplive_models_dir):
                QMessageBox.critical(self, "Error", "Deep Live Models directory does not exist.")
                return
                
            self.config_manager.set("wait_timer_minutes", wait_minutes)
            self.config_manager.set("whisper_model", self.ui_elements['model_entry'].text().strip())
            self.config_manager.set("whisper_device", self.ui_elements['device_entry'].text().strip())
            self.config_manager.set("deeplive_dir", deeplive_dir)
            self.config_manager.set("deeplive_models_dir", deeplive_models_dir)
            self.config_manager.save()
            super().accept()
        except ValueError:
            QMessageBox.critical(self, "Error", "Please enter a valid number for time limit.")

class CalendarTab(QWidget):
    def __init__(self, parent, config_manager, calendar_service, sharex_service, 
                 webhook_service, monitoring_service, audio_processor, deep_live_service):
        super().__init__(parent)
        self.config_manager = config_manager
        self.calendar_service = calendar_service
        self.sharex_service = sharex_service
        self.webhook_service = webhook_service
        self.monitoring_service = monitoring_service
        self.audio_processor = audio_processor
        self.deep_live_service = deep_live_service
        self.ui_elements = {}
        self.event_data = []
        self.current_monitoring_params = None
        self.create_ui()
        
        # Auto-load calendar events on startup
        QTimer.singleShot(1000, self.refresh_calendar_events)

    def start_deeplive_clicked(self):
        """Handle Start Deep Live button click by calling the external function."""
        deeplive_dir = self.config_manager.get("deeplive_dir", "")
        models_dir = self.config_manager.get("deeplive_models_dir", "")
        
        if not deeplive_dir:
            self.status_label.setText("❌ Deep Live directory not set in config!")
            return
        if not models_dir:
            self.status_label.setText("❌ Deep Live models directory not set in config!")
            return
        if not self.drive_path:
            self.status_label.setText("❌ No Google Drive path available for the selected meeting!")
            return
        
        drive_path_normalized = self.drive_path.replace("\\", os.sep).replace("/", os.sep)
        full_image_path = os.path.normpath(os.path.join(models_dir, drive_path_normalized))
        
        camera_name = self.ui_elements['camera_dropdown'].currentText()
        camera_index = None
        if camera_name not in ("No cameras found", ""):
            camera_index = self.camera_index_map.get(camera_name, None)

        settings = {
            "mouth_mask": self.config_manager.get("mouth_mask", False),
            "many_faces": self.config_manager.get("many_faces", True),
            "camera_index": camera_index,
            "startup_delay": self.config_manager.get("startup_delay", 3)
        }
        
        if not os.path.exists(full_image_path):
            self.status_label.setText(f"⚠️ Warning: Image file not found at {full_image_path} (starting anyway)")
        
        try:
            # Start Deep Live and store the subprocess
            process = self.deep_live_service.start_deeplive(deeplive_dir, full_image_path, settings)
            self.parent().parent().deeplive_process = process  # Store in MainApplication
            self.status_label.setText("✅ Deep Live started successfully!")
            self.ui_elements['start_deeplive_button'].setEnabled(False)
            self.ui_elements['stop_deeplive_button'].setEnabled(True)
        except Exception as e:
            self.status_label.setText(f"❌ Failed to start Deep Live: {str(e)}")
    
    def stop_deeplive_clicked(self):
        service = getattr(self.parent().parent(), 'deeplive_service', None)
        if service and service.process is not None:
            try:
                service.stop_deeplive()
                self.status_label.setText("✅ Deep Live stopped successfully!")
            except Exception as e:
                logger.error(f"Error stopping Deep Live: {e}")
                self.status_label.setText(f"❌ Error stopping Deep Live: {e}")
            finally:
                self.ui_elements['start_deeplive_button'].setEnabled(True)
                self.ui_elements['stop_deeplive_button'].setEnabled(False)


    def update_camera_config(self):
        """Update camera_index in config when dropdown selection changes."""
        camera_name = self.ui_elements['camera_dropdown'].currentText()
        camera_index = self.camera_index_map.get(camera_name, None)
        self.config_manager.set("camera_index", camera_index)
        self.config_manager.save()
        self.status_label.setText(f"Selected camera: {camera_name} (Index: {camera_index}) and saved to config")

    def update_mouth_mask_config(self, state):
            """Update mouth_mask in config when checkbox is toggled."""
            self.config_manager.set("mouth_mask", bool(state))
            self.config_manager.save()
            self.status_label.setText(f"{'Enabled' if state else 'Disabled'} Mouth Mask and saved to config")

    def update_many_faces_config(self, state):
            """Update many_faces in config when checkbox is toggled."""
            self.config_manager.set("many_faces", bool(state))
            self.config_manager.save()
            self.status_label.setText(f"{'Enabled' if state else 'Disabled'} Many Faces and saved to config")
            
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
        
        # Meeting Link field
        form_layout.addWidget(QLabel("Meeting Link:"))
        self.ui_elements['meeting_link_entry'] = QLineEdit()
        self.ui_elements['meeting_link_entry'].setFont(QFont("Arial", 9))
        self.ui_elements['meeting_link_entry'].setReadOnly(True)  # display only
        self.ui_elements['meeting_link_entry'].setCursor(Qt.CursorShape.PointingHandCursor)
        original_mousePressEvent = self.ui_elements['meeting_link_entry'].mousePressEvent
        def open_link_on_click(e):
            QDesktopServices.openUrl(QUrl(self.ui_elements['meeting_link_entry'].text()))
            original_mousePressEvent(e)  # keep default
        self.ui_elements['meeting_link_entry'].mousePressEvent = open_link_on_click
        form_layout.addWidget(self.ui_elements['meeting_link_entry'])
        
        # Identity field (new)
        form_layout.addWidget(QLabel("Identity:"))
        self.ui_elements['identity_entry'] = QLineEdit()
        self.ui_elements['identity_entry'].setFont(QFont("Arial", 9))
        self.ui_elements['identity_entry'].setReadOnly(True)  # display only
        self.ui_elements['identity_entry'].setCursor(Qt.CursorShape.PointingHandCursor)
        original_identity_mousePressEvent = self.ui_elements['identity_entry'].mousePressEvent
        def open_identity_on_click(e):
            text = self.ui_elements['identity_entry'].text().strip()
            if text.startswith("Identity: "):
                identity = text.replace("Identity: ", "", 1).strip()
                self._handle_identity_click(identity)
            original_identity_mousePressEvent(e)  # preserve default selection

        self.ui_elements['identity_entry'].mousePressEvent = open_identity_on_click
        form_layout.addWidget(self.ui_elements['identity_entry'])
        
        # Notion URL field
        form_layout.addWidget(QLabel("Notion URL:"))
        self.ui_elements['notion_entry'] = QLineEdit()
        self.ui_elements['notion_entry'].setFont(QFont("Arial", 9))
        form_layout.addWidget(self.ui_elements['notion_entry'])
        
        # Description field
        form_layout.addWidget(QLabel("Description:"))
        self.ui_elements['description_entry'] = QLineEdit()
        self.ui_elements['description_entry'].setFont(QFont("Arial", 9))
        form_layout.addWidget(self.ui_elements['description_entry'])
                # Start Deep Live button
        self.ui_elements['start_deeplive_button'] = QPushButton("Start Deep Live for this meeting")
        self.ui_elements['start_deeplive_button'].setStyleSheet("""
            QPushButton {
                background-color: #3F51B5;
                color: white;
                font-size: 10pt;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #303F9F;
            }
        """)
        self.ui_elements['start_deeplive_button'].clicked.connect(self.start_deeplive_clicked)
        self.ui_elements['start_deeplive_button'].setVisible(False)  # Hidden by default
        form_layout.addWidget(self.ui_elements['start_deeplive_button'])
        self.ui_elements['stop_deeplive_button'] = QPushButton("Stop Deep Live")
        self.ui_elements['stop_deeplive_button'].setStyleSheet("""
            QPushButton {
                background-color: #FF5722;
                color: white;
                font-size: 10pt;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #E64A19;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.ui_elements['stop_deeplive_button'].clicked.connect(self.stop_deeplive_clicked)
        self.ui_elements['stop_deeplive_button'].setVisible(False)  # Hidden by default
        self.ui_elements['stop_deeplive_button'].setEnabled(False)  # Disabled by default
        form_layout.addWidget(self.ui_elements['stop_deeplive_button'])
        # Mouth Mask checkbox
        self.ui_elements['mouth_mask_checkbox'] = QCheckBox("Enable Mouth Mask")
        self.ui_elements['mouth_mask_checkbox'].setFont(QFont("Arial", 9))
        self.ui_elements['mouth_mask_checkbox'].setChecked(self.config_manager.get("mouth_mask", False))
        self.ui_elements['mouth_mask_checkbox'].stateChanged.connect(self.update_mouth_mask_config)
        form_layout.addWidget(self.ui_elements['mouth_mask_checkbox'])

        # Many Faces checkbox
        self.ui_elements['many_faces_checkbox'] = QCheckBox("Enable Many Faces")
        self.ui_elements['many_faces_checkbox'].setFont(QFont("Arial", 9))
        self.ui_elements['many_faces_checkbox'].setChecked(self.config_manager.get("many_faces", True))
        self.ui_elements['many_faces_checkbox'].stateChanged.connect(self.update_many_faces_config)
        form_layout.addWidget(self.ui_elements['many_faces_checkbox'])

        # Camera selection dropdown
        self.ui_elements['camera_label'] = QLabel("Select Camera:")
        self.ui_elements['camera_label'].setFont(QFont("Arial", 9))
        form_layout.addWidget(self.ui_elements['camera_label'])

        self.ui_elements['camera_dropdown'] = QComboBox()
        self.ui_elements['camera_dropdown'].setFont(QFont("Arial", 9))

        try:
            graph = FilterGraph()
            device_names = graph.get_input_devices()  # e.g. ["Logitech HD Webcam", "Integrated Camera"]

            if device_names:
                self.camera_index_map = {name: i for i, name in enumerate(device_names)}
                self.ui_elements['camera_dropdown'].addItems(device_names)
                # Load saved camera index
                saved_camera_index = self.config_manager.get("camera_index", None)
                if saved_camera_index is not None:
                    for name, index in self.camera_index_map.items():
                        if index == saved_camera_index:
                            self.ui_elements['camera_dropdown'].setCurrentText(name)
                            break
            else:
                self.ui_elements['camera_dropdown'].addItems(["No cameras found"])
                self.ui_elements['camera_dropdown'].setEnabled(False)
        except Exception as e:
            self.ui_elements['camera_dropdown'].addItems([f"Error: {e}"])
            self.ui_elements['camera_dropdown'].setEnabled(False)

        # Connect dropdown change to save config
        self.ui_elements['camera_dropdown'].currentIndexChanged.connect(self.update_camera_config)
        form_layout.addWidget(self.ui_elements['camera_dropdown'])

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

    def _handle_identity_click(self, identity: str):
        from gui.deep_live_cam_tab import DeepLiveCamTab  # ensure class is accessible

        # Find the DeepLiveCamTab from parent tabs
        deeplive_tab = None
        parent = self.parent()
        while parent:
            if isinstance(parent, QWidget) and hasattr(parent, "findChild"):
                deeplive_tab = parent.findChild(DeepLiveCamTab)
                if deeplive_tab:
                    break
            parent = parent.parent()

        if not deeplive_tab:
            QMessageBox.warning(self, "Not Found", "Deep Live Cam tab is not available.")
            return

        # Check if identity matches a preset
        if identity in deeplive_tab.presets:
            reply = QMessageBox.question(
                self,
                "Preset Match Found",
                f"Preset '{identity}' found. Do you want to start Deep Live automation?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                deeplive_tab.ui['preset_list'].setCurrentRow(
                    list(deeplive_tab.presets.keys()).index(identity)
                )
                deeplive_tab._start_automation()
        else:
            reply = QMessageBox.question(
                self,
                "No Preset Found",
                f"No preset for '{identity}' was found.\nDo you want to create one?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                deeplive_tab._add_preset()

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
            "3. Notion URL, identity, and description will auto-fill\n"
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

        if not events:
            self.status_label.setText("No events found.")
        else:
            for ev in events:  # show ALL processed events
                item = QListWidgetItem(ev['display_text'])
                item.setData(Qt.ItemDataRole.UserRole, ev)

                # Optional: gray out past events
                if ev.get("is_past", False):
                    item.setForeground(Qt.gray)

                self.cal_listbox.addItem(item)

            self.status_label.setText(f"Loaded {len(events)} events.")

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
        is_event_selected = self.cal_listbox.currentRow() >= 0
        self.ui_elements['start_deeplive_button'].setVisible(is_event_selected)
        self.ui_elements['stop_deeplive_button'].setVisible(is_event_selected)
        # Only enable start button if Deep Live is not running
        self.ui_elements['start_deeplive_button'].setEnabled(
            is_event_selected and not hasattr(self.parent().parent(), 'deeplive_process') or self.parent().parent().deeplive_process is None
        )
        # Only enable stop button if Deep Live is running
        self.ui_elements['stop_deeplive_button'].setEnabled(
            is_event_selected and hasattr(self.parent().parent(), 'deeplive_process') and self.parent().parent().deeplive_process is not None
        )

    def auto_fill_from_selection(self):
        """Auto-fill form fields based on selected calendar event and send Notion URL to webhook."""
        current_row = self.cal_listbox.currentRow()
        if current_row < 0 or current_row >= len(self.event_data):
            return

        event = self.event_data[current_row]

        # Auto-fill Meeting Link
        self.ui_elements['meeting_link_entry'].setText(event.get('meeting_link', '').strip())

        # Auto-fill Notion URL
        notion_url = extract_notion_url(event['notion_url'])
        self.ui_elements['notion_entry'].setText(notion_url)

        # Auto-fill description
        self.ui_elements['description_entry'].setText(event['auto_description'])

        # Clear identity field initially
        self.ui_elements['identity_entry'].setText("")

        # Send Notion URL to webhook and get identity
        if notion_url:
            webhook_url = os.getenv("WEBHOOK_URL3", "").strip()
            try:
                response = requests.post(webhook_url, json={"notion_url": notion_url})
                if response.status_code == 200:
                    try:
                        # Parse webhook response
                        data = response.json()
                        if isinstance(data, list) and len(data) > 0:
                            first = data[0]
                            props = first.get("properties", {})

                            # Extract Name
                            name = None
                            name_prop = props.get("Name", {}).get("title", [])
                            if name_prop and "text" in name_prop[0] and "content" in name_prop[0]["text"]:
                                name = name_prop[0]["text"]["content"]

                            # Extract Google Drive path
                            drive_path = None
                            drive_prop = props.get("Local Path sa Google Drive", {}).get("rich_text", [])
                            if drive_prop and "text" in drive_prop[0] and "content" in drive_prop[0]["text"]:
                                drive_path = drive_prop[0]["text"]["content"]
                            self.drive_path = drive_path  # Store drive_path

                            if name:
                                self.ui_elements['identity_entry'].setText(f"Identity: {name}")
                                msg = f"✅ Notion URL sent to webhook and identity loaded!"
                                if drive_path:
                                    msg += f" (Drive Path: {drive_path})"
                                self.status_label.setText(msg)
                            else:
                                self.status_label.setText("❌ Webhook response invalid: Name not found")

                            if name:
                                self.ui_elements['identity_entry'].setText(f"Identity: {name}")
                                msg = f"✅ Notion URL sent to webhook and identity loaded!"
                                if drive_path:
                                    msg += f" (Drive Path: {drive_path})"
                                self.status_label.setText(msg)
                            else:
                                self.status_label.setText("❌ Webhook response invalid: Name not found")
                        else:
                            self.status_label.setText("❌ Webhook response invalid: Empty list")
                    except json.JSONDecodeError:
                        self.status_label.setText("❌ Failed to parse webhook response as JSON")
                else:
                    self.status_label.setText(
                        f"❌ Failed to send Notion URL to webhook: HTTP {response.status_code} - {response.text}"
                    )
            except Exception as e:
                self.status_label.setText(f"❌ Error sending Notion URL to webhook: {str(e)}")

    
    def update_submit_button_state(self):
        """Update submit button state based on configuration."""
        history_ok = self.config_manager.get("history_path") and os.path.exists(self.config_manager.get("history_path"))
        sharex_ok = self.config_manager.get("sharex_exe_path") and os.path.exists(self.config_manager.get("sharex_exe_path"))
        deeplive_dir_ok = self.config_manager.get("deeplive_dir") and os.path.isdir(self.config_manager.get("deeplive_dir"))
        deeplive_models_dir_ok = self.config_manager.get("deeplive_models_dir") and os.path.isdir(self.config_manager.get("deeplive_models_dir"))
        webhook_ok = os.getenv("WEBHOOK_URL", "").strip()
        
        if history_ok and sharex_ok and deeplive_dir_ok and deeplive_models_dir_ok and webhook_ok:
            self.ui_elements['submit_button'].setEnabled(True)
        else:
            self.ui_elements['submit_button'].setEnabled(False)
    
    def enable_ui_elements(self, enable=True):
        """Enable or disable UI elements."""
        for key in ['notion_entry', 'description_entry', 'submit_button', 'pass_fail_button', 'identity_entry']:
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