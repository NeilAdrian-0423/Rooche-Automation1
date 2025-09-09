"""Dialog windows for the application."""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QTextEdit, QGroupBox, QMessageBox, QButtonGroup,
    QDialogButtonBox, QPlainTextEdit
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


# ------------------------------
# Pass/Fail Dialog
# ------------------------------
class PassFailDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.reason = None
        self.setWindowTitle("Mark Test Result")
        self.resize(400, 300)

        layout = QVBoxLayout(self)

        group_box = QGroupBox("Result")
        group_layout = QVBoxLayout()

        self.pass_radio = QRadioButton("Pass")
        self.fail_radio = QRadioButton("Fail")
        self.radio_group = QButtonGroup(self)
        self.radio_group.addButton(self.pass_radio)
        self.radio_group.addButton(self.fail_radio)

        group_layout.addWidget(self.pass_radio)
        group_layout.addWidget(self.fail_radio)
        group_box.setLayout(group_layout)

        self.reason_edit = QTextEdit()
        self.reason_edit.setPlaceholderText("Enter reason...")

        self.submit_btn = QPushButton("Submit")
        self.submit_btn.clicked.connect(self._on_submit)

        layout.addWidget(group_box)
        layout.addWidget(QLabel("Reason (if Fail):"))
        layout.addWidget(self.reason_edit)
        layout.addWidget(self.submit_btn)

    def _validate(self) -> bool:
        if not (self.pass_radio.isChecked() or self.fail_radio.isChecked()):
            QMessageBox.warning(self, "Validation Error", "Please select Pass or Fail.")
            return False
        if self.fail_radio.isChecked() and not self.reason_edit.toPlainText().strip():
            QMessageBox.warning(self, "Validation Error", "Please provide a reason for Fail.")
            return False
        return True

    def _on_submit(self):
        if not self._validate():
            return
        self.result = "Pass" if self.pass_radio.isChecked() else "Fail"
        self.reason = self.reason_edit.toPlainText().strip()
        self.accept()

    def exec_and_get_result(self):
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.result, self.reason
        return None, None


# ------------------------------
# Wait for Upload Dialog
# ------------------------------
class WaitForUploadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Waiting for Upload")
        self.setModal(True)
        self.resize(300, 100)

        layout = QVBoxLayout(self)
        label = QLabel("Waiting for the next file upload...\nPlease upload the required file to Google Drive.")
        label.setWordWrap(True)
        layout.addWidget(label)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def exec_and_wait(self):
        return self.exec() == QDialog.DialogCode.Accepted


# ------------------------------
# DeepLiveCam Settings Dialog
# ------------------------------
class DeepLiveSettingsDialog(QDialog):
    def __init__(self, parent=None, config_manager=None):
        super().__init__(parent)
        self.cm = config_manager
        self.setWindowTitle("Deep Live Cam Settings")
        self.resize(400, 300)

        layout = QVBoxLayout(self)

        self.setting_edit = QTextEdit()
        self.setting_edit.setPlainText(self.cm.get("deep_live_cam.setting", ""))
        layout.addWidget(QLabel("Deep Live Cam Setting:"))
        layout.addWidget(self.setting_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _save(self):
        try:
            self.cm.set("deep_live_cam.setting", self.setting_edit.toPlainText().strip())
            self.cm.save()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")
            self.reject()


# ------------------------------
# DeepLiveCam Log Viewer
# ------------------------------
class DeepLiveLogDialog(QDialog):
    def __init__(self, parent=None, log_path=""):
        super().__init__(parent)
        self.log_path = log_path
        self.setWindowTitle("Deep Live Cam Logs")
        self.resize(600, 400)

        layout = QVBoxLayout(self)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Courier", 10))
        layout.addWidget(self.log_view)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._load_logs()

    def _load_logs(self):
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                    # Only read last 200 KB to avoid freezing on big logs
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - 200_000))
                    self.log_view.setPlainText(f.read())
                    self.log_view.moveCursor(self.log_view.textCursor().End)
            except Exception as e:
                self.log_view.setPlainText(f"Failed to load log: {e}")
        else:
            self.log_view.setPlainText("No logs available.")
