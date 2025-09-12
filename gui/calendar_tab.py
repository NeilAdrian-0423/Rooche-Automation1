import os
import time
import subprocess
import requests
import json
from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QScrollArea, QCheckBox, QComboBox, QMessageBox, QMenu, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QDesktopServices
from .dialogs import SettingsDialog, PassFailDialog, WaitForUploadDialog
from .threads import CalendarRefreshThread, DeepLiveWorker
from utils.helpers import extract_notion_url, create_labeled_input, create_styled_button
from core.config import ConfigManager 
from .manual_process_dialog import ManualDialog


class CalendarTab(QWidget):
    def __init__(self, parent, calendar_service, sharex_service, 
                 webhook_service, monitoring_service, audio_processor, deep_live_service):
        super().__init__(parent)
        self.config_manager = ConfigManager()  # Initialize ConfigManager directly
        self.calendar_service = calendar_service
        self.sharex_service = sharex_service
        self.webhook_service = webhook_service
        self.monitoring_service = monitoring_service
        self.audio_processor = audio_processor
        self.deep_live_service = deep_live_service
        self.ui_elements = {}
        self.event_data = []
        self.current_monitoring_params = None
        self.drive_path = None
        self.camera_index_map = {}
        self.create_ui()
        QTimer.singleShot(1000, self.refresh_calendar_events)

    def create_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        container = QWidget()
        scroll_area.setWidget(container)
        layout = QVBoxLayout(container)
        
        # Calendar events section
        layout.addWidget(QLabel("Upcoming Calendar Events:", styleSheet="font-size: 12pt; font-weight: bold;"))
        self.cal_listbox = QListWidget()
        self.cal_listbox.setMaximumHeight(150)
        self.cal_listbox.setFont(QFont("Arial", 9))
        self.cal_listbox.itemSelectionChanged.connect(self.on_calendar_select)
        layout.addWidget(self.cal_listbox)
        
        # Buttons
        button_row = QHBoxLayout()
        self.cal_refresh_button = create_styled_button("🔄 Refresh Calendar Events", "#2196F3", "#1976D2")
        self.cal_refresh_button.clicked.connect(self.refresh_calendar_events)
        button_row.addWidget(self.cal_refresh_button)
        
        self.settings_button = create_styled_button("⚙️ Settings", "#666666", "#555555")
        self.settings_button.clicked.connect(self.show_settings_dialog)
        button_row.addWidget(self.settings_button)
        layout.addLayout(button_row)
        
        # Meeting details
        form_group = QGroupBox("Meeting Details (Auto-filled)")
        form_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        form_layout = QVBoxLayout()
        
        self.ui_elements['meeting_link_entry'] = create_labeled_input(form_layout, "Meeting Link:", read_only=True)
        self.ui_elements['meeting_link_entry'].setCursor(Qt.CursorShape.PointingHandCursor)
        def open_meeting_link(event):
            QDesktopServices.openUrl(QUrl(self.ui_elements['meeting_link_entry'].text()))
            event.accept()

        self.ui_elements['meeting_link_entry'].mousePressEvent = open_meeting_link

        
        self.ui_elements['identity_entry'] = create_labeled_input(form_layout, "Identity:", read_only=True)
        
        self.ui_elements['notion_entry'] = create_labeled_input(form_layout, "Notion URL:")
        self.ui_elements['description_entry'] = create_labeled_input(form_layout, "Description:")
        
        self.ui_elements['start_deeplive_button'] = create_styled_button("Start Deep Live for this meeting", "#3F51B5", "#303F9F", disabled_style="background-color: white; color: grey")
        self.ui_elements['start_deeplive_button'].clicked.connect(self.start_deeplive_clicked)
        self.ui_elements['start_deeplive_button'].setVisible(False)
        form_layout.addWidget(self.ui_elements['start_deeplive_button'])
        
        self.ui_elements['stop_deeplive_button'] = create_styled_button("Stop Deep Live", "#FF5722", "#E64A19", disabled_style="background-color: white; color: grey")
        self.ui_elements['stop_deeplive_button'].clicked.connect(self.stop_deeplive_clicked)
        self.ui_elements['stop_deeplive_button'].setVisible(False)
        self.ui_elements['stop_deeplive_button'].setEnabled(False)
        form_layout.addWidget(self.ui_elements['stop_deeplive_button'])
        
        self.ui_elements['mouth_mask_checkbox'] = QCheckBox("Enable Mouth Mask")
        self.ui_elements['mouth_mask_checkbox'].setChecked(self.config_manager.get("mouth_mask", False))
        self.ui_elements['mouth_mask_checkbox'].stateChanged.connect(self.update_mouth_mask_config)
        form_layout.addWidget(self.ui_elements['mouth_mask_checkbox'])
        
        self.ui_elements['many_faces_checkbox'] = QCheckBox("Enable Many Faces")
        self.ui_elements['many_faces_checkbox'].setChecked(self.config_manager.get("many_faces", True))
        self.ui_elements['many_faces_checkbox'].stateChanged.connect(self.update_many_faces_config)
        form_layout.addWidget(self.ui_elements['many_faces_checkbox'])
        
        self.ui_elements['camera_dropdown'] = QComboBox()
        form_layout.addWidget(QLabel("Select Camera:"))
        form_layout.addWidget(self.ui_elements['camera_dropdown'])
        self.populate_camera_dropdown()
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: blue; font-size: 10pt;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        self.create_file_labels(layout)
        self.create_control_buttons(layout)
        self.create_info_section(layout)
        main_layout.addWidget(scroll_area)
        # Update file labels and submit button state after UI creation
        self.update_file_labels()
        self.update_submit_button_state()

    def populate_camera_dropdown(self):
        try:
            from pygrabber.dshow_graph import FilterGraph
            graph = FilterGraph()
            device_names = graph.get_input_devices()
            if device_names:
                self.camera_index_map = {name: i for i, name in enumerate(device_names)}
                self.ui_elements['camera_dropdown'].addItems(device_names)
                saved_camera_index = self.config_manager.get("camera_index")
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
        self.ui_elements['camera_dropdown'].currentIndexChanged.connect(self.update_camera_config)

    def update_camera_config(self):
        camera_name = self.ui_elements['camera_dropdown'].currentText()
        camera_index = self.camera_index_map.get(camera_name)
        self.config_manager.set("camera_index", camera_index)
        self.config_manager.save()
        self.status_label.setText(f"Selected camera: {camera_name} (Index: {camera_index})")

    def update_mouth_mask_config(self, state):
        self.config_manager.set("mouth_mask", bool(state))
        self.config_manager.save()
        self.status_label.setText(f"{'Enabled' if state else 'Disabled'} Mouth Mask")

    def update_many_faces_config(self, state):
        self.config_manager.set("many_faces", bool(state))
        self.config_manager.save()
        self.status_label.setText(f"{'Enabled' if state else 'Disabled'} Many Faces")

    def show_settings_dialog(self):
        dialog = SettingsDialog(self, self.config_manager)
        if dialog.exec():
            self.update_file_labels()
            self.update_submit_button_state()

    def create_file_labels(self, parent_layout):
        self.history_file_label = QLabel("No ShareX history file selected")
        self.history_file_label.setStyleSheet("color: gray;")
        parent_layout.addWidget(self.history_file_label)
        
        self.sharex_exe_label = QLabel("No ShareX executable selected")
        self.sharex_exe_label.setStyleSheet("color: gray;")
        parent_layout.addWidget(self.sharex_exe_label)

    def manual_transcribe_clicked(self):
        """Open the Manual Transcribe dialog."""
        dialog = ManualDialog(
            parent=self,
            config_manager=self.config_manager,
            sharex_service=self.sharex_service,
            audio_processor=self.audio_processor,
            webhook_service=self.webhook_service,
            calendar_tab=self
        )
        dialog.exec()


    def create_control_buttons(self, parent_layout):
        control_row = QHBoxLayout()
        self.ui_elements['submit_menu_button'] = QPushButton("🚀 Start Options")
        self.ui_elements['submit_menu_button'].setStyleSheet(
            "background-color: #4CAF50; color: white; border-radius: 6px; padding: 6px; font-weight: bold;"
        )
        self.ui_elements['submit_menu_button'].setEnabled(False)

        menu = QMenu(self)

        start_automation_action = menu.addAction("Start Automation")
        start_automation_action.triggered.connect(self.handle_submission)

        manual_transcribe_action = menu.addAction("Manual Transcribe + n8n")
        manual_transcribe_action.triggered.connect(self.manual_transcribe_clicked)

        self.ui_elements['submit_menu_button'].setMenu(menu)
        control_row.addWidget(self.ui_elements['submit_menu_button'])
        
        self.ui_elements['reset_button'] = create_styled_button("🛑 Stop All", "#FF5722", "#E64A19", disabled_style="#cccccc; color: white")
        self.ui_elements['reset_button'].clicked.connect(self.stop_monitoring)
        self.ui_elements['reset_button'].setEnabled(False)
        control_row.addWidget(self.ui_elements['reset_button'])
        
        parent_layout.addLayout(control_row)
        
        self.ui_elements['pass_fail_button'] = create_styled_button("✅❌ Submit Pass/Fail Result", "#9C27B0", "#7B1FA2")
        self.ui_elements['pass_fail_button'].clicked.connect(self.handle_pass_fail)
        parent_layout.addWidget(self.ui_elements['pass_fail_button'], alignment=Qt.AlignmentFlag.AlignCenter)

    def create_info_section(self, parent_layout):
        info_group = QGroupBox("ℹ️ How to Use")
        info_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        info_layout = QVBoxLayout()
        info_text = QLabel(
            "1. Refresh calendar events\n"
            "2. Select a meeting\n"
            "3. Configure settings\n"
            "4. Start monitoring/recording\n"
            "5. Submit pass/fail results"
        )
        info_text.setStyleSheet("color: gray; font-size: 8pt;")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        info_group.setLayout(info_layout)
        parent_layout.addWidget(info_group)

    def start_deeplive_clicked(self):
        deeplive_dir = self.config_manager.get("deeplive_dir", "")
        models_dir = self.config_manager.get("deeplive_models_dir", "")
        if not deeplive_dir or not models_dir or not self.drive_path:
            self.status_label.setText("❌ Missing configuration or drive path!")
            return
        
        full_image_path = os.path.normpath(os.path.join(models_dir, self.drive_path.replace("\\", os.sep)))
        camera_name = self.ui_elements['camera_dropdown'].currentText()
        camera_index = self.camera_index_map.get(camera_name)
        
        settings = {
            "mouth_mask": self.config_manager.get("mouth_mask", False),
            "many_faces": self.config_manager.get("many_faces", True),
            "camera_index": camera_index,
            "startup_delay": self.config_manager.get("startup_delay", 60)
        }
        
        if not os.path.exists(full_image_path):
            self.status_label.setText(f"⚠️ Image file not found at {full_image_path}")
        
        self.status_label.setText("⏳ Starting Deep Live...")
        self.ui_elements['start_deeplive_button'].setEnabled(False)
        self.ui_elements['stop_deeplive_button'].setEnabled(True)
        self.worker = DeepLiveWorker(self.deep_live_service, deeplive_dir, full_image_path, settings)
        self.worker.finished.connect(self.on_deeplive_finished)
        self.worker.start()

    def on_deeplive_finished(self, process, error):
        if error:
            self.status_label.setText(f"❌ Failed to start Deep Live: {error}")
            self.ui_elements['start_deeplive_button'].setEnabled(True)
            return
        self.status_label.setText("✅ Deep Live started!")
        self.ui_elements['start_deeplive_button'].setEnabled(False)
        self.ui_elements['stop_deeplive_button'].setEnabled(True)
        parent = self.parent()
        if parent and hasattr(parent, 'parent') and parent.parent():
            parent.parent().deeplive_process = process

    def stop_deeplive_clicked(self):
        try:
            self.deep_live_service.stop_deeplive()
            self.status_label.setText("✅ Deep Live stopped!")
        except Exception as e:
            self.status_label.setText(f"❌ Error stopping Deep Live: {e}")
        finally:
            self.ui_elements['start_deeplive_button'].setEnabled(True)
            self.ui_elements['stop_deeplive_button'].setEnabled(False)

    def refresh_calendar_events(self):
        self.cal_refresh_button.setText("Refreshing...")
        self.cal_refresh_button.setEnabled(False)
        self.refresh_thread = CalendarRefreshThread(self.calendar_service)
        self.refresh_thread.finished.connect(self.on_events_loaded)
        self.refresh_thread.error.connect(self.on_events_error)
        self.refresh_thread.start()

    def on_events_loaded(self, events):
        self.cal_listbox.clear()
        self.event_data = events
        for ev in events:
            item = QListWidgetItem(ev['display_text'])
            item.setData(Qt.ItemDataRole.UserRole, ev)
            if ev.get("is_past", False):
                item.setForeground(Qt.gray)
            self.cal_listbox.addItem(item)
        self.status_label.setText(f"Loaded {len(events)} events.")
        self.cal_refresh_button.setText("🔄 Refresh Calendar Events")
        self.cal_refresh_button.setEnabled(True)

    def on_events_error(self, error_msg):
        self.cal_listbox.clear()
        self.cal_listbox.addItem(f"Error loading events: {error_msg}")
        self.event_data = []
        self.cal_refresh_button.setText("🔄 Refresh Calendar Events")
        self.cal_refresh_button.setEnabled(True)

    def on_calendar_select(self):
        is_event_selected = self.cal_listbox.currentRow() >= 0
        self.ui_elements['start_deeplive_button'].setVisible(is_event_selected)
        self.ui_elements['stop_deeplive_button'].setVisible(is_event_selected)
        self.auto_fill_from_selection()

    def auto_fill_from_selection(self):
        current_row = self.cal_listbox.currentRow()
        if current_row < 0 or current_row >= len(self.event_data):
            return
        event = self.event_data[current_row]
        self.ui_elements['meeting_link_entry'].setText(event.get('meeting_link', '').strip())
        notion_url = extract_notion_url(event['notion_url'])
        self.ui_elements['notion_entry'].setText(notion_url)
        self.ui_elements['description_entry'].setText(event['auto_description'])
        self.ui_elements['identity_entry'].setText("")
        
        if notion_url:
            webhook_url = os.getenv("WEBHOOK_URL3", "").strip()
            try:
                response = requests.post(webhook_url, json={"notion_url": notion_url})
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data:
                        props = data[0].get("properties", {})
                        name = props.get("Name", {}).get("title", [{}])[0].get("text", {}).get("content")
                        drive_path = props.get("Local Path sa Google Drive", {}).get("rich_text", [{}])[0].get("text", {}).get("content")
                        self.drive_path = drive_path
                        if name:
                            self.ui_elements['identity_entry'].setText(f"Identity: {name}")
                            self.status_label.setText(f"✅ Identity loaded! {'(Drive Path: ' + drive_path + ')' if drive_path else ''}")
                        else:
                            self.status_label.setText("❌ Webhook response invalid: Name not found")
                    else:
                        self.status_label.setText("❌ Webhook response invalid: Empty list")
                else:
                    self.status_label.setText(f"❌ Webhook error: HTTP {response.status_code}")
            except Exception as e:
                self.status_label.setText(f"❌ Webhook error: {str(e)}")

    def update_file_labels(self):
        history_path = self.config_manager.get("history_path")
        self.history_file_label.setText(f"{'✅' if history_path and os.path.exists(history_path) else '❌'} History: {os.path.basename(history_path) if history_path else 'None'}")
        self.history_file_label.setStyleSheet(f"color: {'green' if history_path and os.path.exists(history_path) else 'red'};")
        
        sharex_path = self.config_manager.get("sharex_exe_path")
        self.sharex_exe_label.setText(f"{'✅' if sharex_path and os.path.exists(sharex_path) else '❌'} ShareX: {os.path.basename(sharex_path) if sharex_path else 'None'}")
        self.sharex_exe_label.setStyleSheet(f"color: {'green' if sharex_path and os.path.exists(sharex_path) else 'red'};")

    def update_submit_button_state(self):
        conditions = [
            self.config_manager.get("history_path") and os.path.exists(self.config_manager.get("history_path")),
            self.config_manager.get("sharex_exe_path") and os.path.exists(self.config_manager.get("sharex_exe_path")),
            self.config_manager.get("deeplive_dir") and os.path.isdir(self.config_manager.get("deeplive_dir")),
            self.config_manager.get("deeplive_models_dir") and os.path.isdir(self.config_manager.get("deeplive_models_dir")),
            os.getenv("WEBHOOK_URL", "").strip()
        ]
        self.ui_elements['submit_menu_button'].setEnabled(all(conditions))

    def launch_sharex_and_start_recording(self):
        sharex_path = self.config_manager.get("sharex_exe_path")
        if not sharex_path or not os.path.exists(sharex_path):
            self.status_label.setText("❌ ShareX executable not found!")
            return False
        try:
            self.status_label.setText("🚀 Launching ShareX...")
            subprocess.Popen(f'"{sharex_path}"')
            time.sleep(3)
            self.status_label.setText("🎥 Starting screen recording...")
            success = self.sharex_service.trigger_recording()
            self.status_label.setText(f"✅ ShareX launched{' and recording started' if success else ' but recording may have failed'}!")
            return True
        except Exception as e:
            self.status_label.setText(f"❌ Failed to launch ShareX: {str(e)}")
            return False

    def handle_submission(self):
        notion_url = self.ui_elements['notion_entry'].text().strip()
        description = self.ui_elements['description_entry'].text().strip()
        history_path = self.config_manager.get("history_path")
        sharex_path = self.config_manager.get("sharex_exe_path")
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()

        if not notion_url:
            QMessageBox.critical(self, "Error", "Missing Notion URL")
            return
        if not description:
            QMessageBox.critical(self, "Error", "Missing description")
            return
        if not history_path or not os.path.exists(history_path):
            QMessageBox.critical(self, "Error", "Invalid or missing ShareX history path")
            return
        if not sharex_path or not os.path.exists(sharex_path):
            QMessageBox.critical(self, "Error", "Invalid or missing ShareX executable path")
            return
        if not webhook_url:
            QMessageBox.critical(self, "Error", "WEBHOOK_URL environment variable is missing")
            return

        submit_time = datetime.now(timezone.utc).astimezone()
        wait_minutes = self.config_manager.get("wait_timer_minutes", 60)
        self.enable_ui_elements(False)

        if not self.launch_sharex_and_start_recording():
            self.enable_ui_elements(True)
            return

        self.current_monitoring_params = {
                'after_dt': submit_time,
                'timeout_minutes': wait_minutes,
                'notion_url': notion_url,
                'description': description,
                'callback': lambda transcription, drive_url, local_file_path: self.status_label.setText("✅ Transcription sent!"),
                'status_callback': self.status_label.setText,
                'completion_callback': lambda: (self.enable_ui_elements(True), setattr(self, 'current_monitoring_params', None))
            }

        self.monitoring_service.start_monitoring(**self.current_monitoring_params)

        self.status_label.setText(f"🚀 Monitoring started with {wait_minutes} minute limit...")

    def stop_monitoring(self):
        dialog = WaitForUploadDialog(self)
        result = dialog.show()
        if result == "wait":
            self.status_label.setText("⏳ Waiting for upload...")
        elif result == "stop":
            self.monitoring_service.stop_monitoring()
            self.sharex_service.stop_recording()
            self.status_label.setText("🛑 Monitoring and recording stopped")
            self.enable_ui_elements(True)
            self.current_monitoring_params = None

    def handle_pass_fail(self):
        notion_url = self.ui_elements['notion_entry'].text().strip()
        description = self.ui_elements['description_entry'].text().strip()
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()
        if not all([notion_url, description, webhook_url]):
            QMessageBox.critical(self, "Error", "Missing required fields or webhook URL!")
            return
        
        dialog = PassFailDialog(self)
        result, reason = dialog.show()
        if result and reason:
            self.status_label.setText("📤 Sending pass/fail result...")
            success = self.webhook_service.send_data(notion_url, description, result, reason)
            self.status_label.setText(f"{'✅' if success else '❌'} {result.title()} result sent!")
        else:
            self.status_label.setText("❌ Pass/fail submission cancelled")

    def enable_ui_elements(self, enable=True):
        for key in ['notion_entry', 'description_entry', 'submit_menu_button', 'pass_fail_button', 'identity_entry']:
            self.ui_elements[key].setEnabled(enable)
        self.ui_elements['reset_button'].setEnabled(not enable)
        self.settings_button.setEnabled(enable)