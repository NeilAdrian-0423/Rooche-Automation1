from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QGroupBox, QFileDialog, QMessageBox, QDialogButtonBox
from PyQt6.QtGui import QFont
from utils.helpers import create_labeled_input, create_styled_button
import os
class PassFailDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Pass/Fail Result")
        self.result = None
        self.reason = ""
        self.create_ui()

    def create_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select Result:"))
        
        self.pass_button = create_styled_button("✅ Pass", "#4CAF50", "#45a049")
        self.pass_button.clicked.connect(lambda: self.set_result("Pass"))
        layout.addWidget(self.pass_button)
        
        self.fail_button = create_styled_button("❌ Fail", "#FF5722", "#E64A19")
        self.fail_button.clicked.connect(lambda: self.set_result("Fail"))
        layout.addWidget(self.fail_button)
        
        self.reason_entry = create_labeled_input(layout, "Reason:")
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def set_result(self, result):
        self.result = result

    def show(self):
        if self.exec():
            return self.result, self.reason_entry.text().strip()
        return None, None

class WaitForUploadDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Stop Monitoring")
        self.result = None
        self.create_ui()

    def create_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Do you want to wait for the upload to complete or stop immediately?"))
        
        self.wait_button = create_styled_button("⏳ Wait for Upload", "#2196F3", "#1976D2")
        self.wait_button.clicked.connect(lambda: self.set_result("wait"))
        layout.addWidget(self.wait_button)
        
        self.stop_button = create_styled_button("🛑 Stop Immediately", "#FF5722", "#E64A19")
        self.stop_button.clicked.connect(lambda: self.set_result("stop"))
        layout.addWidget(self.stop_button)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def set_result(self, result):
        self.result = result
        self.accept()

    def show(self):
        self.exec()
        return self.result

class SettingsDialog(QDialog):
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Settings")
        self.setMinimumWidth(200)
        self.ui_elements = {}
        self.create_ui()

    def create_ui(self):
        layout = QVBoxLayout(self)
        config_group = QGroupBox("Configuration")
        config_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        config_layout = QVBoxLayout()
        
        self.ui_elements['timer_entry'] = create_labeled_input(config_layout, "Time Limit (minutes):", str(self.config_manager.get("wait_timer_minutes", 60)), max_width=100)
        self.ui_elements['model_entry'] = create_labeled_input(config_layout, "Whisper Model:", self.config_manager.get("whisper_model", "base"), max_width=100)
        self.ui_elements['device_entry'] = create_labeled_input(config_layout, "Device:", self.config_manager.get("whisper_device", "cpu"), max_width=100)
        self.ui_elements['deeplive_dir_entry'] = create_labeled_input(config_layout, "DeepLive Directory:", self.config_manager.get("deeplive_dir", ""), max_width=200)
        self.ui_elements['select_deeplive_dir_button'] = create_styled_button("📁 Select DeepLive Directory", "#666666", "#555555")
        self.ui_elements['select_deeplive_dir_button'].clicked.connect(self.select_deeplive_dir)
        config_layout.addWidget(self.ui_elements['select_deeplive_dir_button'])
        
        self.ui_elements['deeplive_models_dir_entry'] = create_labeled_input(config_layout, "Deep Live Models Directory:", self.config_manager.get("deeplive_models_dir", ""), max_width=200)
        self.ui_elements['select_deeplive_models_dir_button'] = create_styled_button("📁 Select Deep Live Models Directory", "#666666", "#555555")
        self.ui_elements['select_deeplive_models_dir_button'].clicked.connect(self.select_deeplive_models_dir)
        config_layout.addWidget(self.ui_elements['select_deeplive_models_dir_button'])
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        file_buttons_row = QHBoxLayout()
        self.ui_elements['select_history_button'] = create_styled_button("📁 Select ShareX History", "#666666", "#555555")
        self.ui_elements['select_history_button'].clicked.connect(self.select_history_file)
        file_buttons_row.addWidget(self.ui_elements['select_history_button'])
        
        self.ui_elements['select_sharex_button'] = create_styled_button("🎯 Select ShareX.exe", "#FF9800", "#F57C00")
        self.ui_elements['select_sharex_button'].clicked.connect(self.select_sharex_exe)
        file_buttons_row.addWidget(self.ui_elements['select_sharex_button'])
        
        layout.addLayout(file_buttons_row)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def select_deeplive_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select DeepLive Directory", "")
        if path:
            self.ui_elements['deeplive_dir_entry'].setText(path)

    def select_deeplive_models_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Deep Live Models Directory", "")
        if path:
            self.ui_elements['deeplive_models_dir_entry'].setText(path)

    def select_history_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select ShareX history.json", "", "JSON Files (*.json)")
        if path:
            self.config_manager.set("history_path", path)
            self.parent().update_file_labels()
            self.parent().update_submit_button_state()

    def select_sharex_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select ShareX.exe", "", "Executable Files (*.exe);;All Files (*.*)")
        if path:
            self.config_manager.set("sharex_exe_path", path)
            self.parent().update_file_labels()
            self.parent().update_submit_button_state()

    def accept(self):
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
                
            self.config_manager.update({
                "wait_timer_minutes": wait_minutes,
                "whisper_model": self.ui_elements['model_entry'].text().strip(),
                "whisper_device": self.ui_elements['device_entry'].text().strip(),
                "deeplive_dir": deeplive_dir,
                "deeplive_models_dir": deeplive_models_dir
            })
            self.config_manager.save()
            super().accept()
        except ValueError:
            QMessageBox.critical(self, "Error", "Please enter a valid number for time limit.")