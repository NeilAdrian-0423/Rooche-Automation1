import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

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
            
            # Process the file
            transcription = self.audio_processor.process_file(
                self.local_file_path, 
                lambda msg: self.status_update.emit(msg)
            )
            
            if transcription:
                # Send to webhook
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

class ManualTab(QWidget):
    def __init__(self, parent, config_manager, sharex_service, audio_processor, 
                 webhook_service, calendar_tab):
        super().__init__(parent)
        self.config_manager = config_manager
        self.sharex_service = sharex_service
        self.audio_processor = audio_processor
        self.webhook_service = webhook_service
        self.calendar_tab = calendar_tab
        
        self.file_data = []
        self.create_ui()
    
    def create_ui(self):
        """Create the manual tab UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Title label
        title_label = QLabel("Recent Audio/Video Files (Last 24 Hours):")
        title_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        layout.addWidget(title_label)
        
        # Create listbox (QListWidget has built-in scrollbar)
        self.manual_listbox = QListWidget()
        self.manual_listbox.setMinimumHeight(300)
        self.manual_listbox.setFont(QFont("Arial", 9))
        self.manual_listbox.itemSelectionChanged.connect(self.on_file_select)
        layout.addWidget(self.manual_listbox)
        
        # Manual refresh button
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
        
        # Process selected button
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
            "Use this tab if you forgot to start monitoring before uploading.\n"
            "Select a recent file and click 'Process Selected File' to transcribe\n"
            "and send it to your webhook. Make sure to fill in the meeting details\n"
            "in the Calendar Events tab first."
        )
        info_label.setStyleSheet("color: gray; font-size: 8pt;")
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)
        
        # Add stretch to push everything to the top
        layout.addStretch()
    
    def on_file_select(self):
        """Handle file selection."""
        if self.manual_listbox.currentRow() >= 0 and self.file_data:
            self.process_selected_button.setEnabled(True)
        else:
            self.process_selected_button.setEnabled(False)
    
    def refresh_file_list(self):
        """Refresh the list of recent audio/video files."""
        self.manual_refresh_button.setText("Refreshing...")
        self.manual_refresh_button.setEnabled(False)
        
        # Clear current list
        self.manual_listbox.clear()
        
        # Get recent files
        recent_files = self.sharex_service.get_recent_files()
        
        if recent_files:
            for file_info in recent_files:
                self.manual_listbox.addItem(file_info['display_text'])
            
            # Store file info
            self.file_data = recent_files
        else:
            self.manual_listbox.addItem("No recent audio/video files found")
            self.file_data = []
        
        self.manual_refresh_button.setText("🔄 Refresh File List")
        self.manual_refresh_button.setEnabled(True)
        
        # Update button state
        self.on_file_select()
    
    def process_selected_file(self):
        """Process the selected file from the list."""
        current_row = self.manual_listbox.currentRow()
        
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a file from the list.")
            return
        
        if not self.file_data:
            QMessageBox.critical(self, "Error", "No file data available. Please refresh the list.")
            return
        
        if current_row >= len(self.file_data):
            QMessageBox.critical(self, "Error", "Invalid selection. Please refresh the list.")
            return
        
        # Get form data from calendar tab
        try:
            notion_url = self.calendar_tab.ui_elements['notion_entry'].text().strip()
            description = self.calendar_tab.ui_elements['description_entry'].text().strip()
        except KeyError as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"Missing required field in Calendar Events tab: {str(e)}. Please ensure all fields are properly set up."
            )
            return
        
        if not notion_url or not description:
            QMessageBox.critical(
                self, 
                "Error", 
                "Please enter both Notion URL and description in the Calendar Events tab."
            )
            return
        
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()
        if not webhook_url:
            QMessageBox.critical(self, "Error", "Webhook URL not set in .env file.")
            return
        
        # Get selected file info
        file_info = self.file_data[current_row]
        local_file_path = file_info['filepath']
        
        if not os.path.exists(local_file_path):
            QMessageBox.critical(self, "Error", f"File not found: {local_file_path}")
            return
        
        # Update config with hardcoded values
        self.config_manager.set("whisper_model", "small")
        self.config_manager.set("whisper_device", "cuda")
        self.config_manager.save()
        
        # Disable button during processing
        self.process_selected_button.setEnabled(False)
        
        # Create and start processing thread
        self.processing_thread = FileProcessingThread(
            self.audio_processor,
            self.webhook_service,
            file_info,
            notion_url,
            description,
            local_file_path
        )
        
        # Connect signals
        self.processing_thread.status_update.connect(self.update_status)
        self.processing_thread.processing_complete.connect(self.on_processing_complete)
        
        # Start the thread
        self.processing_thread.start()
    
    def update_status(self, message):
        """Update the status label in the calendar tab."""
        if hasattr(self.calendar_tab, 'status_label'):
            self.calendar_tab.status_label.setText(message)
    
    def on_processing_complete(self):
        """Re-enable the process button when processing is complete."""
        self.process_selected_button.setEnabled(True)
        
        # Clean up the thread
        if hasattr(self, 'processing_thread'):
            self.processing_thread.quit()
            self.processing_thread.wait()
            self.processing_thread.deleteLater()
            self.processing_thread = None