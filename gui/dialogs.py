"""Dialog windows for the application."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QTextEdit, QGroupBox, QMessageBox, QButtonGroup
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

class PassFailDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.reason = None
        
        self.setWindowTitle("Meeting Result")
        self.setFixedSize(500, 400)
        self.setModal(True)
        
        # Center the dialog over parent
        if parent:
            self.center_dialog(parent)
        
        self.create_widgets()
        
    def center_dialog(self, parent):
        """Center the dialog over the parent window."""
        parent_rect = parent.geometry()
        parent_center = parent_rect.center()
        dialog_rect = self.rect()
        dialog_rect.moveCenter(parent_center)
        self.move(dialog_rect.topLeft())
    
    def create_widgets(self):
        """Create all widgets for the dialog."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(main_layout)
        
        # Title label
        title_label = QLabel("Meeting Result")
        title_font = QFont("Arial", 16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #333;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        main_layout.addSpacing(20)
        
        # Result selection group
        result_group = QGroupBox("Select Result")
        result_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        result_layout = QVBoxLayout()
        result_layout.setContentsMargins(15, 15, 15, 15)
        
        # Create radio buttons
        self.pass_radio = QRadioButton("✅ Pass - Meeting was successful")
        self.pass_radio.setStyleSheet("color: green; font-size: 10pt;")
        result_layout.addWidget(self.pass_radio)
        
        self.fail_radio = QRadioButton("❌ Fail - Meeting had issues")
        self.fail_radio.setStyleSheet("color: red; font-size: 10pt;")
        result_layout.addWidget(self.fail_radio)
        
        # Create button group for radio buttons
        self.button_group = QButtonGroup()
        self.button_group.addButton(self.pass_radio, 0)
        self.button_group.addButton(self.fail_radio, 1)
        
        result_group.setLayout(result_layout)
        main_layout.addWidget(result_group)
        main_layout.addSpacing(15)
        
        # Reason input group
        reason_group = QGroupBox("Reason (Required)")
        reason_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        reason_layout = QVBoxLayout()
        reason_layout.setContentsMargins(15, 15, 15, 15)
        
        self.reason_text = QTextEdit()
        self.reason_text.setMaximumHeight(100)
        self.reason_text.setFont(QFont("Arial", 10))
        self.reason_text.setPlaceholderText("Enter the reason for this result...")
        
        reason_layout.addWidget(self.reason_text)
        reason_group.setLayout(reason_layout)
        main_layout.addWidget(reason_group)
        main_layout.addSpacing(20)
        
        # Button container
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Cancel button
        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                font-size: 11pt;
                padding: 10px 20px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
            QPushButton:pressed {
                background-color: #424242;
            }
        """)
        self.cancel_btn.clicked.connect(self.cancel)
        button_layout.addWidget(self.cancel_btn)
        
        button_layout.addSpacing(20)
        
        # Submit button
        self.submit_btn = QPushButton("✅ Submit Result")
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 11pt;
                font-weight: bold;
                padding: 10px 20px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.submit_btn.clicked.connect(self.submit)
        self.submit_btn.setDefault(True)
        button_layout.addWidget(self.submit_btn)
        
        main_layout.addLayout(button_layout)
        
        # Add stretch to push everything to the top
        main_layout.addStretch()
        
        # Set keyboard shortcuts
        self.cancel_btn.setShortcut("Escape")
        self.submit_btn.setShortcut("Return")
        
        # Set initial focus
        self.pass_radio.setFocus()
    
    def submit(self):
        """Validate and submit the form."""
        # Check if a radio button is selected
        if not self.pass_radio.isChecked() and not self.fail_radio.isChecked():
            QMessageBox.critical(self, "Error", "Please select Pass or Fail.")
            return
        
        # Get the result
        if self.pass_radio.isChecked():
            result = "pass"
        else:
            result = "fail"
        
        # Get and validate reason
        reason = self.reason_text.toPlainText().strip()
        
        if not reason:
            QMessageBox.critical(self, "Error", "Please enter a reason.")
            self.reason_text.setFocus()
            return
        
        if len(reason) < 5:
            QMessageBox.critical(self, "Error", "Reason must be at least 5 characters long.")
            self.reason_text.setFocus()
            return
        
        # Set results and accept dialog
        self.result = result
        self.reason = reason
        self.accept()
    
    def cancel(self):
        """Cancel the dialog."""
        self.result = None
        self.reason = None
        self.reject()
    
    def show(self):
        """Show the dialog and wait for result."""
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.result, self.reason
        else:
            return None, None


class WaitForUploadDialog(QDialog):
    """Dialog to ask user whether to wait for upload or stop completely."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        
        self.setWindowTitle("Stop Monitoring?")
        self.setFixedSize(450, 200)
        self.setModal(True)
        
        if parent:
            self.center_dialog(parent)
        
        self.create_widgets()
    
    def center_dialog(self, parent):
        """Center the dialog over the parent window."""
        parent_rect = parent.geometry()
        parent_center = parent_rect.center()
        dialog_rect = self.rect()
        dialog_rect.moveCenter(parent_center)
        self.move(dialog_rect.topLeft())
    
    def create_widgets(self):
        """Create dialog widgets."""
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(layout)
        
        # Question label
        question_label = QLabel(
            "Do you want to continue waiting for Google Drive upload?\n\n"
            "• Yes - Continue monitoring for file uploads\n"
            "• No - Stop monitoring and recording completely"
        )
        question_label.setWordWrap(True)
        question_label.setFont(QFont("Arial", 10))
        layout.addWidget(question_label)
        
        layout.addSpacing(20)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Stop button
        stop_btn = QPushButton("❌ No, Stop Completely")
        stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF5722;
                color: white;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #E64A19;
            }
        """)
        stop_btn.clicked.connect(self.stop_completely)
        button_layout.addWidget(stop_btn)
        
        button_layout.addSpacing(20)
        
        # Wait button
        wait_btn = QPushButton("✅ Yes, Keep Waiting")
        wait_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        wait_btn.clicked.connect(self.keep_waiting)
        wait_btn.setDefault(True)
        button_layout.addWidget(wait_btn)
        
        layout.addLayout(button_layout)
    
    def stop_completely(self):
        """Stop monitoring completely."""
        self.result = "stop"
        self.accept()
    
    def keep_waiting(self):
        """Continue waiting for upload."""
        self.result = "wait"
        self.accept()
    
    def show(self):
        """Show dialog and return result."""
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.result
        return "stop"  # Default to stop if dialog is closed


class ConfirmationDialog(QDialog):
    """A simple confirmation dialog."""
    
    def __init__(self, parent=None, title="Confirm", message="Are you sure?"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(400, 150)
        
        # Center the dialog
        if parent:
            self.center_dialog(parent)
        
        self.create_widgets(message)
    
    def center_dialog(self, parent):
        """Center the dialog over the parent window."""
        parent_rect = parent.geometry()
        parent_center = parent_rect.center()
        dialog_rect = self.rect()
        dialog_rect.moveCenter(parent_center)
        self.move(dialog_rect.topLeft())
    
    def create_widgets(self, message):
        """Create dialog widgets."""
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(layout)
        
        # Message label
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setFont(QFont("Arial", 10))
        layout.addWidget(message_label)
        
        layout.addSpacing(20)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                padding: 8px 20px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        button_layout.addSpacing(10)
        
        confirm_btn = QPushButton("Confirm")
        confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 20px;
                min-width: 80px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        confirm_btn.clicked.connect(self.accept)
        confirm_btn.setDefault(True)
        button_layout.addWidget(confirm_btn)
        
        layout.addLayout(button_layout)
    
    @staticmethod
    def confirm(parent=None, title="Confirm", message="Are you sure?"):
        """Static method to show confirmation dialog."""
        dialog = ConfirmationDialog(parent, title, message)
        return dialog.exec() == QDialog.DialogCode.Accepted


class InfoDialog(QDialog):
    """An information dialog."""
    
    def __init__(self, parent=None, title="Information", message=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(400, 200)
        
        # Center the dialog
        if parent:
            self.center_dialog(parent)
        
        self.create_widgets(message)
    
    def center_dialog(self, parent):
        """Center the dialog over the parent window."""
        parent_rect = parent.geometry()
        parent_center = parent_rect.center()
        dialog_rect = self.rect()
        dialog_rect.moveCenter(parent_center)
        self.move(dialog_rect.topLeft())
    
    def create_widgets(self, message):
        """Create dialog widgets."""
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(layout)
        
        # Message label
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setFont(QFont("Arial", 10))
        layout.addWidget(message_label)
        
        layout.addStretch()
        
        # OK button
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 30px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
    
    @staticmethod
    def show_info(parent=None, title="Information", message=""):
        """Static method to show info dialog."""
        dialog = InfoDialog(parent, title, message)
        dialog.exec()