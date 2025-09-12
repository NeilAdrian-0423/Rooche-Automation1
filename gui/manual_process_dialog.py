import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QDesktopServices


class FileProcessingThread(QThread):
    """Thread for processing selected files."""
    status_update = pyqtSignal(str)
    processing_complete = pyqtSignal()
    
    def __init__(self, audio_processor, webhook_service, file_info, 
                 notion_url, description, local_file_path):
        super().__init__()
        self.audio_processor = audio_processor
        self.webhook_service = webhook_service
        self.file_info = file_info
        self.notion_url = notion_url
        self.description = description
        self.local_file_path = local_file_path
    
    def run(self):
        try:
            self.status_update.emit(f"🎬 Processing: {self.file_info['filename']}")
            
            transcription = self.audio_processor.process_file(
                self.local_file_path, 
                lambda msg: self.status_update.emit(msg)
            )
            
            if transcription:
                self.webhook_service.send_data(
                    self.notion_url, 
                    self.description, 
                    transcription,
                    self.file_info['url'], 
                    self.local_file_path
                )
                self.status_update.emit("✅ File processed and sent to webhook!")
            else:
                self.status_update.emit("❌ File processing failed")
                
        except Exception as e:
            self.status_update.emit(f"❌ Error: {str(e)}")
        finally:
            self.processing_complete.emit()


class ManualDialog(QDialog):
    def __init__(self, parent, config_manager, sharex_service, audio_processor, 
                 webhook_service, calendar_tab):
        super().__init__(parent)
        self.setWindowTitle("Manual Processing")
        self.setMinimumWidth(400)

        self.config_manager = config_manager
        self.sharex_service = sharex_service
        self.audio_processor = audio_processor
        self.webhook_service = webhook_service
        self.calendar_tab = calendar_tab
        
        self.file_data = []
        self.create_ui()
    
    def create_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title_label = QLabel("Recent Audio/Video Files (Last 24 Hours):")
        title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        layout.addWidget(title_label)
        
        # File list
        self.manual_listbox = QListWidget()
        self.manual_listbox.setMinimumHeight(300)
        self.manual_listbox.setFont(QFont("Arial", 9))
        self.manual_listbox.itemSelectionChanged.connect(self.on_file_select)
        layout.addWidget(self.manual_listbox)
        
        # Refresh button
        self.manual_refresh_button = QPushButton("🔄 Refresh File List")
        self.manual_refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 9pt;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.manual_refresh_button.clicked.connect(self.refresh_file_list)
        layout.addWidget(self.manual_refresh_button)
        
        # Preview button
        self.preview_button = QPushButton("▶ Preview File")
        self.preview_button.setEnabled(False)
        self.preview_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 9pt;
                font-weight: bold;
                padding: 6px;
            }
            QPushButton:hover:enabled {
                background-color: #388E3C;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.preview_button.clicked.connect(self.preview_selected_file)
        layout.addWidget(self.preview_button)
        
        # Process button
        self.process_selected_button = QPushButton("🎯 Process Selected File")
        self.process_selected_button.setEnabled(False)
        self.process_selected_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-size: 10pt;
                font-weight: bold;
                padding: 8px;
            }
            QPushButton:hover:enabled {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.process_selected_button.clicked.connect(self.process_selected_file)
        layout.addWidget(self.process_selected_button)
        
        # Info label
        info_label = QLabel(
            "Use this dialog if you forgot to start monitoring before uploading.\n"
            "Select a recent file, preview it if needed, then click 'Process Selected File'\n"
            "to transcribe and send it to your webhook. Make sure to fill in the meeting details\n"
            "in the Calendar Events tab first."
        )
        info_label.setStyleSheet("color: gray; font-size: 8pt;")
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)
    
    def on_file_select(self):
        """Enable/disable action buttons based on selection."""
        valid_selection = self.manual_listbox.currentRow() >= 0 and bool(self.file_data)
        self.preview_button.setEnabled(valid_selection)
        self.process_selected_button.setEnabled(valid_selection)
    
    def refresh_file_list(self):
        """Refresh recent files."""
        self.manual_refresh_button.setText("Refreshing...")
        self.manual_refresh_button.setEnabled(False)
        
        self.manual_listbox.clear()
        recent_files = self.sharex_service.get_recent_files()
        
        if recent_files:
            for file_info in recent_files:
                self.manual_listbox.addItem(file_info['display_text'])
            self.file_data = recent_files
        else:
            self.manual_listbox.addItem("No recent audio/video files found")
            self.file_data = []
        
        self.manual_refresh_button.setText("🔄 Refresh File List")
        self.manual_refresh_button.setEnabled(True)
        self.on_file_select()
    
    def preview_selected_file(self):
        """Preview the selected file using the system's default player."""
        current_row = self.manual_listbox.currentRow()
        if current_row < 0 or not self.file_data:
            QMessageBox.warning(self, "Error", "Please select a file to preview.")
            return
        
        file_info = self.file_data[current_row]
        local_file_path = file_info['filepath']
        
        if not os.path.exists(local_file_path):
            QMessageBox.critical(self, "Error", f"File not found: {local_file_path}")
            return
        
        QDesktopServices.openUrl(QUrl.fromLocalFile(local_file_path))
    
    def process_selected_file(self):
        """Process selected file from list."""
        current_row = self.manual_listbox.currentRow()
        
        if current_row < 0 or not self.file_data or current_row >= len(self.file_data):
            QMessageBox.warning(self, "Error", "Please select a valid file.")
            return
        
        # Collect meeting data
        try:
            notion_url = self.calendar_tab.ui_elements['notion_entry'].text().strip()
            description = self.calendar_tab.ui_elements['description_entry'].text().strip()
        except KeyError as e:
            QMessageBox.critical(
                self, "Error", 
                f"Missing required field in Calendar Events tab: {str(e)}"
            )
            return
        
        if not notion_url or not description:
            QMessageBox.critical(self, "Error", "Please enter Notion URL and description.")
            return
        
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()
        if not webhook_url:
            QMessageBox.critical(self, "Error", "Webhook URL not set in .env file.")
            return
        
        file_info = self.file_data[current_row]
        local_file_path = file_info['filepath']
        
        if not os.path.exists(local_file_path):
            QMessageBox.critical(self, "Error", f"File not found: {local_file_path}")
            return
        
        # Update config defaults
        self.config_manager.set("whisper_model", self.config_manager.get("whisper_model", "small"))
        self.config_manager.set("whisper_device", self.config_manager.get("whisper_device", "cuda"))
        self.config_manager.save()
        
        self.process_selected_button.setEnabled(False)
        
        # Start background processing
        self.processing_thread = FileProcessingThread(
            self.audio_processor,
            self.webhook_service,
            file_info,
            notion_url,
            description,
            local_file_path
        )
        self.processing_thread.status_update.connect(self.update_status)
        self.processing_thread.processing_complete.connect(self.on_processing_complete)
        self.processing_thread.start()
    
    def update_status(self, message):
        """Update status label in calendar tab."""
        if hasattr(self.calendar_tab, 'status_label'):
            self.calendar_tab.status_label.setText(message)
    
    def on_processing_complete(self):
        """Re-enable process button and clean up."""
        self.process_selected_button.setEnabled(True)
        if hasattr(self, 'processing_thread'):
            self.processing_thread.quit()
            self.processing_thread.wait()
            self.processing_thread.deleteLater()
            self.processing_thread = None
