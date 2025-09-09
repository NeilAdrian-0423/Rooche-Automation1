import os
import json
import subprocess
import time
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QLineEdit, QGroupBox, QFileDialog, QMessageBox, QScrollArea, QSpinBox,
    QCheckBox, QDialog, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QImage
from PIL import Image
import pyautogui
import pygetwindow as gw
from pywinauto import Desktop, Application
from pywinauto.findwindows import ElementNotFoundError
import psutil
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deep_live_cam_automation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

PRESETS_FILE = "face_presets.json"
SETTINGS_FILE = "app_settings.json"
LOG_FILE = "deep_live_cam_automation.log"

class AutomationWorker(QThread):
    """Enhanced automation worker with full functionality"""
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished_success = pyqtSignal()
    finished_failure = pyqtSignal(str)

    def __init__(self, image_path, script_path, obs_path, settings):
        super().__init__()
        self.image_path = image_path
        self.script_path = script_path
        self.obs_path = obs_path
        self.settings = settings
        self.should_stop = False
        self.processes = []
        self.logger = logging.getLogger(__name__)

    def request_stop(self):
        self.should_stop = True
        self.stop_all_processes()

    def run(self):
        try:
            if self.should_stop:
                return

            # Step 1: Start Deep Live Cam
            self.status_changed.emit("Starting Deep Live Cam...")
            if not self._start_deep_live_cam():
                self.finished_failure.emit("Failed to start Deep Live Cam")
                return

            if self.should_stop:
                return

            # Step 2: Configure Deep Live Cam
            self.status_changed.emit("Configuring Deep Live Cam...")
            if not self._configure_deep_live_cam():
                self.finished_failure.emit("Failed to configure Deep Live Cam")
                return

            if self.should_stop:
                return

            # Step 3: Start OBS if enabled
            if self.settings.get('auto_start_obs', True):
                self.status_changed.emit("Starting OBS...")
                if not self._start_obs():
                    self.finished_failure.emit("Failed to start OBS")
                    return

            self.status_changed.emit("Automation completed successfully!")
            self.finished_success.emit()

        except Exception as e:
            self.logger.exception("Automation failed")
            self.error_occurred.emit(str(e))
            self.finished_failure.emit(str(e))

    def _start_deep_live_cam(self):
        """Start Deep Live Cam application"""
        try:
            dlc_dir = self.settings.get("deep_live_cam_dir", "")
            venv_python = os.path.join(dlc_dir, "venv", "Scripts", "python.exe")
            run_py = os.path.join(dlc_dir, "run.py")

            if not os.path.exists(venv_python) or not os.path.exists(run_py):
                raise FileNotFoundError(f"Invalid Deep Live Cam directory: {dlc_dir}")

            # Preconfigure switch_states.json
            switch_file = os.path.join(dlc_dir, "switch_states.json")
            if self.settings.get('switch_json_path'):
                try:
                    shutil.copy(self.settings['switch_json_path'], switch_file)
                except Exception as e:
                    self.logger.error(f"Failed to copy switch json: {e}")

            try:
                with open(switch_file, 'r') as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}

            data['mouth_mask'] = self.settings.get('mouth_mask', False)
            data['many_faces'] = self.settings.get('many_faces', True)

            with open(switch_file, 'w') as f:
                json.dump(data, f, indent=4)

            process = subprocess.Popen(
                [venv_python, run_py, "--execution-provider", "cuda"],
                cwd=dlc_dir
            )
            self.processes.append(process)
            time.sleep(self.settings.get('startup_delay', 3))

            # Wait for window with timeout...
            timeout = self.settings.get('window_timeout', 30)
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.should_stop:
                    return False
                titles = gw.getAllTitles()
                windows = [t for t in titles if "deep-live-cam" in t.lower()]
                if windows:
                    self.logger.info(f"Deep Live Cam window found: {windows[0]}")
                    return True
                time.sleep(1)

            self.logger.error("Deep Live Cam window not found within timeout")
            return False

        except Exception as e:
            self.logger.error(f"Failed to start Deep Live Cam: {e}")
            return False

    def _configure_deep_live_cam(self):
        """Configure Deep Live Cam with selected image"""
        try:
            # Wait for UI to be ready
            time.sleep(2)

            # Click 'Select a face' button using image recognition
            if not self._click_button_by_image("select_face.png", "Select a face button"):
                return False
            time.sleep(1)

            # Handle file dialog
            if not self._select_image_file():
                return False
            time.sleep(2)

            # Click 'Live' button
            if not self._click_button_by_image("live.png", "Live button"):
                return False

            # Verify with user if enabled
            if self.settings.get('require_confirmation', True):
                # In a real implementation, this would use a custom dialog
                # For now, we'll assume success
                pass

            return True

        except Exception as e:
            self.logger.error(f"Failed to configure Deep Live Cam: {e}")
            return False

    def _click_button_by_image(self, image_name, description):
        """Click button using image recognition"""
        try:
            confidence = self.settings.get('image_confidence', 0.9)
            button = pyautogui.locateOnScreen(image_name, confidence=confidence)
            if button:
                pyautogui.click(pyautogui.center(button))
                self.logger.info(f"Clicked {description}")
                return True
            else:
                self.logger.warning(f"Could not locate {description}")
                return False
        except Exception as e:
            self.logger.error(f"Error clicking {description}: {e}")
            return False

    def _select_image_file(self) -> bool:
        """Select image file in Deep Live Cam's file dialog"""
        try:
            filename = os.path.basename(self.image_path)
            dirname = os.path.dirname(self.image_path)
            self.logger.info(f"Selecting image file: {filename}")

            # Focus address bar and navigate to directory
            pyautogui.hotkey('alt', 'd')
            time.sleep(0.5)
            pyautogui.write(dirname)
            pyautogui.press('enter')
            time.sleep(1)

            # Wait for Deep Live Cam window
            main_win = Desktop(backend="uia").window(title_re=".*Deep-Live-Cam.*")
            if not main_win.exists(timeout=10):
                self.logger.error("Deep Live Cam window not found")
                return False
            main_win.set_focus()

            # Search for file item and Open button
            file_item = None
            open_button = None
            for ctrl in main_win.descendants():
                try:
                    name = ctrl.element_info.name
                    if name == filename and ctrl.element_info.control_type == "ListItem":
                        file_item = ctrl
                    if name.lower() == "open" and ctrl.element_info.control_type == "Button":
                        open_button = ctrl
                except Exception:
                    continue

            # Interact with file item
            if file_item:
                file_item.click_input()
                time.sleep(0.5)
            else:
                self.logger.warning("File item not found. Trying filename input")
                try:
                    name_field = main_win.child_window(control_type="Edit", auto_id="1148")
                    name_field.type_keys(filename)
                except Exception as e:
                    self.logger.error(f"Failed to input filename: {e}")
                    return False

            # Click Open
            if open_button:
                open_button.click_input()
            else:
                self.logger.warning("Open button not found. Using Enter key")
                pyautogui.press('enter')

            time.sleep(1)
            return True

        except Exception as e:
            self.logger.exception(f"Error selecting image file: {e}")
            return False

    def _start_obs(self):
        """Start OBS application"""
        try:
            if not os.path.exists(self.obs_path):
                raise FileNotFoundError(f"OBS not found: {self.obs_path}")

            obs_dir = os.path.dirname(self.obs_path)
            process = subprocess.Popen([self.obs_path], cwd=obs_dir)
            self.processes.append(process)
            time.sleep(2)
            return True

        except Exception as e:
            self.logger.error(f"Failed to start OBS: {e}")
            return False

    def stop_all_processes(self):
        """Terminate Deep Live Cam and OBS processes"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = " ".join(proc.info['cmdline']) if proc.info['cmdline'] else ""
                    # Kill DLC (match run.py path)
                    if self.script_path and "run.py" in cmdline and self.script_path in cmdline:
                        self.logger.info(f"Killing Deep Live Cam PID {proc.info['pid']} Cmdline: {cmdline}")
                        proc.terminate()
                        proc.wait(timeout=5)
                    # Kill OBS
                    elif self.obs_path and self.obs_path in cmdline:
                        self.logger.info(f"Killing OBS PID {proc.info['pid']} Cmdline: {cmdline}")
                        proc.terminate()
                        proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    continue
        except Exception as e:
            self.logger.error(f"Error during process cleanup: {e}")

class DeepLiveCamTab(QWidget):
    """Enhanced Deep Live Cam automation tab with redesigned UI"""
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.config_manager = config_manager
        self.ui = {}
        self.presets = {}
        self.settings = {}
        self.image_cache = {}
        self.worker = None
        self.logger = logging.getLogger(__name__)

        # Disable pyautogui failsafe
        pyautogui.FAILSAFE = False

        self._load_data()
        self._create_ui()
        self._refresh_preset_list()
        self._update_file_labels()  # Call after UI is created

    def _load_data(self):
        """Load presets and settings"""
        try:
            if os.path.exists(PRESETS_FILE):
                with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                    self.presets = json.load(f) or {}
        except Exception as e:
            self.logger.error(f"Failed to load presets: {e}")
            self.presets = {}

        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    self.settings = json.load(f) or {}
        except Exception as e:
            self.logger.error(f"Failed to load settings: {e}")
            self.settings = {}

        self.settings.setdefault('deep_live_cam_dir', 'E:\\Deep-Live-Cam')
        self.settings.setdefault('obs_path', 'obs64.exe')
        self.settings.setdefault('startup_delay', 3)
        self.settings.setdefault('window_timeout', 30)
        self.settings.setdefault('image_confidence', 0.9)
        self.settings.setdefault('auto_start_obs', True)
        self.settings.setdefault('require_confirmation', True)
        self.settings.setdefault('mouth_mask', False)
        self.settings.setdefault('many_faces', True)
        self.settings.setdefault('switch_json_path', '')

    def _save_presets(self):
        """Save presets to file"""
        try:
            with open(PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save presets: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save presets:\n{e}")
            return False

    def _save_settings(self):
        """Save settings to file"""
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save settings: {e}")
            return False

    def _create_ui(self):
        """Create redesigned user interface similar to CalendarTab"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Create scrollable area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        # Container widget for scroll area
        container = QWidget()
        scroll_area.setWidget(container)
        layout = QVBoxLayout(container)

        # Title
        title = QLabel("Deep Live Cam Automation")
        title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # Preset panel
        preset_widget = self._create_preset_panel()
        layout.addWidget(preset_widget)

        # Control panel
        control_widget = self._create_control_panel()
        layout.addWidget(control_widget)

        # Status bar
        self._create_status_bar(layout)

        # Info section
        self._create_info_section(layout)

    def _create_preset_panel(self):
        """Create preset management panel with CalendarTab-style design"""
        presets_group = QGroupBox("Face Presets")
        presets_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        layout = QVBoxLayout(presets_group)

        # Preset list (smaller height like CalendarTab)
        self.ui['preset_list'] = QListWidget()
        self.ui['preset_list'].setMaximumHeight(150)  # Match CalendarTab's listbox height
        self.ui['preset_list'].setFont(QFont("Arial", 9))
        self.ui['preset_list'].itemSelectionChanged.connect(self._on_preset_select)
        self.ui['preset_list'].itemDoubleClicked.connect(self._edit_preset)
        layout.addWidget(self.ui['preset_list'])

        # Preset buttons row
        button_row = QHBoxLayout()
        self.ui['btn_add'] = QPushButton("📁 Add Preset")
        self.ui['btn_add'].clicked.connect(self._add_preset)
        self.ui['btn_add'].setStyleSheet("""
            QPushButton { background-color: #2196F3; color: white; font-size: 9pt; padding: 5px; }
            QPushButton:hover { background-color: #1976D2; }
        """)
        button_row.addWidget(self.ui['btn_add'])

        self.ui['btn_edit'] = QPushButton("✏️ Edit Preset")
        self.ui['btn_edit'].setEnabled(False)
        self.ui['btn_edit'].clicked.connect(self._edit_preset)
        self.ui['btn_edit'].setStyleSheet("""
            QPushButton { background-color: #666666; color: white; font-size: 9pt; padding: 5px; }
            QPushButton:hover:enabled { background-color: #555555; }
            QPushButton:disabled { background-color: #cccccc; color: #666666; }
        """)
        button_row.addWidget(self.ui['btn_edit'])

        self.ui['btn_delete'] = QPushButton("🗑️ Delete Preset")
        self.ui['btn_delete'].setEnabled(False)
        self.ui['btn_delete'].clicked.connect(self._delete_preset)
        self.ui['btn_delete'].setStyleSheet("""
            QPushButton { background-color: #FF5722; color: white; font-size: 9pt; padding: 5px; }
            QPushButton:hover:enabled { background-color: #E64A19; }
            QPushButton:disabled { background-color: #cccccc; color: #666666; }
        """)
        button_row.addWidget(self.ui['btn_delete'])

        layout.addLayout(button_row)
        return presets_group

    def _create_control_panel(self):
        """Create control and preview panel with CalendarTab-style design"""
        control_group = QGroupBox("Automation Controls")
        control_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        layout = QVBoxLayout(control_group)

        # Preview section
        preview_group = QGroupBox("Preset Preview")
        preview_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        pv_layout = QVBoxLayout(preview_group)
        self.ui['preview'] = QLabel("Select a preset to preview")
        self.ui['preview'].setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ui['preview'].setFixedHeight(150)  # Smaller preview to match compact design
        self.ui['preview'].setStyleSheet("background-color: #ecf0f1; border: 2px dashed #bdc3c7; font-size: 9pt;")
        pv_layout.addWidget(self.ui['preview'])

        self.ui['info_label'] = QLabel("")
        self.ui['info_label'].setWordWrap(True)
        self.ui['info_label'].setStyleSheet("color: #2c3e50; font-size: 8pt;")
        pv_layout.addWidget(self.ui['info_label'])
        layout.addWidget(preview_group)

        # File selection section
        file_group = QGroupBox("File Configuration")
        file_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        file_layout = QVBoxLayout(file_group)

        # Script path
        self.ui['script_file_label'] = QLabel("❌ No Deep Live Cam directory selected")
        self.ui['script_file_label'].setStyleSheet("color: red; font-size: 9pt;")
        file_layout.addWidget(self.ui['script_file_label'])

        script_layout = QHBoxLayout()
        self.ui['script_path'] = QLineEdit(self.settings.get('deep_live_cam_dir', ''))
        self.ui['script_path'].setFont(QFont("Arial", 9))
        self.ui['script_path'].textChanged.connect(self._on_script_path_changed)
        script_layout.addWidget(self.ui['script_path'])

        self.ui['btn_browse_script'] = QPushButton("📁 Browse")
        self.ui['btn_browse_script'].clicked.connect(self._browse_script)
        self.ui['btn_browse_script'].setStyleSheet("""
            QPushButton { background-color: #2196F3; color: white; font-size: 9pt; padding: 5px; }
            QPushButton:hover { background-color: #1976D2; }
        """)
        script_layout.addWidget(self.ui['btn_browse_script'])
        file_layout.addLayout(script_layout)

        # OBS path
        self.ui['obs_file_label'] = QLabel("❌ No OBS executable selected")
        self.ui['obs_file_label'].setStyleSheet("color: red; font-size: 9pt;")
        file_layout.addWidget(self.ui['obs_file_label'])

        obs_layout = QHBoxLayout()
        self.ui['obs_path'] = QLineEdit(self.settings.get('obs_path', ''))
        self.ui['obs_path'].setFont(QFont("Arial", 9))
        self.ui['obs_path'].textChanged.connect(self._on_obs_path_changed)
        obs_layout.addWidget(self.ui['obs_path'])

        self.ui['btn_browse_obs'] = QPushButton("📁 Browse")
        self.ui['btn_browse_obs'].clicked.connect(self._browse_obs)
        self.ui['btn_browse_obs'].setStyleSheet("""
            QPushButton { background-color: #2196F3; color: white; font-size: 9pt; padding: 5px; }
            QPushButton:hover { background-color: #1976D2; }
        """)
        obs_layout.addWidget(self.ui['btn_browse_obs'])
        file_layout.addLayout(obs_layout)

        layout.addWidget(file_group)

        # Advanced settings
        advanced_group = QGroupBox("Advanced Settings")
        advanced_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        adv_layout = QVBoxLayout(advanced_group)

        self.ui['auto_obs'] = QCheckBox("Auto-start OBS")
        self.ui['auto_obs'].setChecked(self.settings.get('auto_start_obs', True))
        self.ui['auto_obs'].setFont(QFont("Arial", 9))
        self.ui['auto_obs'].toggled.connect(self._on_auto_obs_changed)
        adv_layout.addWidget(self.ui['auto_obs'])

        self.ui['require_confirm'] = QCheckBox("Require confirmation before starting OBS")
        self.ui['require_confirm'].setChecked(self.settings.get('require_confirmation', True))
        self.ui['require_confirm'].setFont(QFont("Arial", 9))
        self.ui['require_confirm'].toggled.connect(self._on_require_confirm_changed)
        adv_layout.addWidget(self.ui['require_confirm'])

        # Mouth Mask switch
        self.ui['mouth_mask'] = QCheckBox("Enable Mouth Mask")
        self.ui['mouth_mask'].setChecked(self.settings.get('mouth_mask', False))
        self.ui['mouth_mask'].setFont(QFont("Arial", 9))
        self.ui['mouth_mask'].toggled.connect(self._on_mouth_mask_changed)
        adv_layout.addWidget(self.ui['mouth_mask'])

        # Many Faces switch
        self.ui['many_faces'] = QCheckBox("Enable Many Faces")
        self.ui['many_faces'].setChecked(self.settings.get('many_faces', True))
        self.ui['many_faces'].setFont(QFont("Arial", 9))
        self.ui['many_faces'].toggled.connect(self._on_many_faces_changed)
        adv_layout.addWidget(self.ui['many_faces'])

        timeout_layout = QHBoxLayout()
        lbl = QLabel("Window timeout (seconds):")
        lbl.setFont(QFont("Arial", 9))
        timeout_layout.addWidget(lbl)
        self.ui['timeout'] = QSpinBox()
        self.ui['timeout'].setFont(QFont("Arial", 9))
        self.ui['timeout'].setRange(5, 120)
        self.ui['timeout'].setValue(self.settings.get('window_timeout', 30))
        self.ui['timeout'].valueChanged.connect(self._on_timeout_changed)
        timeout_layout.addWidget(self.ui['timeout'])
        timeout_layout.addStretch()
        adv_layout.addLayout(timeout_layout)

        confidence_layout = QHBoxLayout()
        lbl = QLabel("Image recognition confidence:")
        lbl.setFont(QFont("Arial", 9))
        confidence_layout.addWidget(lbl)
        self.ui['confidence'] = QSpinBox()
        self.ui['confidence'].setFont(QFont("Arial", 9))
        self.ui['confidence'].setRange(50, 100)
        self.ui['confidence'].setValue(int(self.settings.get('image_confidence', 0.9) * 100))
        self.ui['confidence'].setSuffix("%")
        self.ui['confidence'].valueChanged.connect(self._on_confidence_changed)
        confidence_layout.addWidget(self.ui['confidence'])
        confidence_layout.addStretch()
        adv_layout.addLayout(confidence_layout)

        # Custom switch json
        switch_layout = QHBoxLayout()
        lbl = QLabel("Custom Switch JSON:")
        lbl.setFont(QFont("Arial", 9))
        switch_layout.addWidget(lbl)
        self.ui['switch_json'] = QLineEdit(self.settings.get('switch_json_path', ''))
        self.ui['switch_json'].setFont(QFont("Arial", 9))
        self.ui['switch_json'].textChanged.connect(self._on_switch_json_changed)
        switch_layout.addWidget(self.ui['switch_json'])
        self.ui['btn_browse_switch'] = QPushButton("📁 Browse")
        self.ui['btn_browse_switch'].clicked.connect(self._browse_switch_json)
        self.ui['btn_browse_switch'].setStyleSheet("""
            QPushButton { background-color: #2196F3; color: white; font-size: 9pt; padding: 5px; }
            QPushButton:hover { background-color: #1976D2; }
        """)
        switch_layout.addWidget(self.ui['btn_browse_switch'])
        adv_layout.addLayout(switch_layout)

        # Button for separate modal
        self.ui['btn_edit_switches'] = QPushButton("Edit Switch States Modal")
        self.ui['btn_edit_switches'].clicked.connect(self._open_switch_modal)
        self.ui['btn_edit_switches'].setStyleSheet("""
            QPushButton { background-color: #2196F3; color: white; font-size: 9pt; padding: 5px; }
            QPushButton:hover { background-color: #1976D2; }
        """)
        adv_layout.addWidget(self.ui['btn_edit_switches'])

        layout.addWidget(advanced_group)

        # Control buttons
        control_layout = QHBoxLayout()
        self.ui['btn_start'] = QPushButton("🚀 Start Automation")
        self.ui['btn_start'].setEnabled(False)
        self.ui['btn_start'].clicked.connect(self._start_automation)
        self.ui['btn_start'].setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white; font-size: 10pt; font-weight: bold; padding: 5px; }
            QPushButton:hover:enabled { background-color: #45a049; }
            QPushButton:disabled { background-color: #cccccc; color: #666666; }
        """)
        control_layout.addWidget(self.ui['btn_start'])

        self.ui['btn_stop'] = QPushButton("🛑 Stop All")
        self.ui['btn_stop'].setEnabled(True)
        self.ui['btn_stop'].clicked.connect(self._stop_automation)
        self.ui['btn_stop'].setStyleSheet("""
            QPushButton { background-color: #FF5722; color: white; font-size: 10pt; font-weight: bold; padding: 5px; }
            QPushButton:hover:enabled { background-color: #E64A19; }
            QPushButton:disabled { background-color: #cccccc; color: #666666; }
        """)
        control_layout.addWidget(self.ui['btn_stop'])

        layout.addLayout(control_layout)
        return control_group

    def _create_status_bar(self, parent_layout):
        """Create status bar with CalendarTab-style design"""
        self.ui['status'] = QLabel("Ready")
        self.ui['status'].setStyleSheet("color: blue; font-size: 10pt;")
        self.ui['status'].setWordWrap(True)
        parent_layout.addWidget(self.ui['status'])

    def _create_info_section(self, parent_layout):
        """Create info section with usage instructions"""
        info_group = QGroupBox("ℹ️ How to Use")
        info_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        info_layout = QVBoxLayout()
        info_text = QLabel(
            "1. Add or select a face preset from the list above\n"
            "2. Configure the Deep Live Cam script and OBS executable paths\n"
            "3. Adjust advanced settings (timeout, confidence, etc.) as needed\n"
            "4. Click 'Start Automation' to launch Deep Live Cam and OBS\n"
            "5. Use 'Stop All' to terminate all running processes\n"
            "⚡ Presets are saved automatically and can be edited or deleted\n"
            "🎯 Automation will select the face image and start live mode"
        )
        info_text.setStyleSheet("color: gray; font-size: 8pt;")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        info_group.setLayout(info_layout)
        parent_layout.addWidget(info_group)

    def _refresh_preset_list(self):
        """Refresh preset list"""
        self.ui['preset_list'].clear()
        for name in sorted(self.presets.keys()):
            self.ui['preset_list'].addItem(name)

    def _selected_preset(self):
        """Get selected preset"""
        items = self.ui['preset_list'].selectedItems()
        if not items:
            return None, None
        name = items[0].text()
        return name, self.presets.get(name)

    def _on_preset_select(self):
        """Handle preset selection"""
        name, preset = self._selected_preset()
        has_selection = bool(name and preset)
        self.ui['btn_edit'].setEnabled(has_selection)
        self.ui['btn_delete'].setEnabled(has_selection)
        self.ui['btn_start'].setEnabled(has_selection and not self.worker)
        if has_selection:
            self._display_image(preset.get("image_path"))
            self._show_preset_info(name, preset)
        else:
            self.ui['preview'].setText("Select a preset to preview")
            self.ui['info_label'].setText("")

    def _display_image(self, image_path):
        """Display image preview with caching"""
        if not image_path or not os.path.exists(image_path):
            self.ui['preview'].setText("Image not found")
            return

        try:
            if image_path in self.image_cache:
                pixmap = self.image_cache[image_path]
            else:
                # Open image with PIL
                image = Image.open(image_path).convert('RGB')  # Convert to RGB to ensure compatibility
                # Resize image while maintaining aspect ratio
                image.thumbnail((320, 240), Image.Resampling.LANCZOS)  # Use LANCZOS for better quality
                # Convert PIL image to QImage
                qimage = QImage(
                    image.tobytes(),  # Use tobytes() for raw RGB data
                    image.width,
                    image.height,
                    image.width * 3,  # Bytes per line (3 bytes per pixel for RGB)
                    QImage.Format.Format_RGB888  # Correct format constant for PyQt6
                )
                # Convert to QPixmap and cache
                pixmap = QPixmap.fromImage(qimage)
                self.image_cache[image_path] = pixmap

            # Set the pixmap to the preview label and scale it
            self.ui['preview'].setPixmap(pixmap.scaled(
                self.ui['preview'].size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

        except Exception as e:
            self.logger.error(f"Failed to display image: {e}")
            self.ui['preview'].setText(f"Error loading image:\n{str(e)}")

    def _show_preset_info(self, name, preset):
        """Show preset information"""
        info_text = (
            f"Name: {name}\n"
            f"Created: {preset.get('created', 'Unknown')}\n"
            f"Last Used: {preset.get('last_used', 'Never')}\n"
            f"Image: {preset.get('image_path', 'Not set')}"
        )
        self.ui['info_label'].setText(info_text)

    def _add_preset(self):
        """Add new preset"""
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Add Preset", "Enter preset name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.presets:
            QMessageBox.warning(self, "Warning", f"Preset '{name}' already exists!")
            return

        image_path, _ = QFileDialog.getOpenFileName(
            self, "Select Face Image", "", "Image files (*.png *.jpg *.jpeg *.gif *.bmp);;All files (*.*)"
        )
        if not image_path:
            return

        self.presets[name] = {
            "image_path": os.path.normpath(image_path),
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_used": None
        }

        if self._save_presets():
            self.logger.info(f"Added preset '{name}' with image '{image_path}'")
            self._refresh_preset_list()
            for i in range(self.ui['preset_list'].count()):
                if self.ui['preset_list'].item(i).text() == name:
                    self.ui['preset_list'].setCurrentRow(i)
                    break
            QMessageBox.information(self, "Success", f"Preset '{name}' added successfully!")

    def _edit_preset(self):
        """Edit selected preset"""
        name, preset = self._selected_preset()
        if not preset:
            QMessageBox.warning(self, "Warning", "Please select a preset to edit")
            return

        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(self, "Edit Preset", "Edit preset name:", text=name)
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name != name and new_name in self.presets:
            QMessageBox.warning(self, "Warning", f"Preset '{new_name}' already exists!")
            return

        reply = QMessageBox.question(
            self, "Change Image", "Do you want to change the image for this preset?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            image_path, _ = QFileDialog.getOpenFileName(
                self, "Select New Face Image", "", "Image files (*.png *.jpg *.jpeg *.gif *.bmp);;All files (*.*)"
            )
            if image_path:
                preset["image_path"] = os.path.normpath(image_path)
                if image_path in self.image_cache:
                    del self.image_cache[image_path]

        if new_name != name:
            self.presets[new_name] = preset
            del self.presets[name]

        if self._save_presets():
            self.logger.info(f"Edited preset '{name}' -> '{new_name}'")
            self._refresh_preset_list()
            for i in range(self.ui['preset_list'].count()):
                if self.ui['preset_list'].item(i).text() == new_name:
                    self.ui['preset_list'].setCurrentRow(i)
                    break
            QMessageBox.information(self, "Success", "Preset updated successfully!")

    def _delete_preset(self):
        """Delete selected preset"""
        name, _ = self._selected_preset()
        if not name:
            QMessageBox.warning(self, "Warning", "Please select a preset to delete")
            return

        reply = QMessageBox.question(
            self, "Confirm Delete", f"Are you sure you want to delete preset '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self.presets[name]
            if self._save_presets():
                self.logger.info(f"Deleted preset '{name}'")
                self._refresh_preset_list()
                self.ui['preview'].setText("Select a preset to preview")
                self.ui['info_label'].setText("")
                QMessageBox.information(self, "Success", f"Preset '{name}' deleted successfully!")

    def _on_script_path_changed(self, path):
        self.settings['deep_live_cam_dir'] = path
        self._update_file_labels()
        self._save_settings()

    def _on_obs_path_changed(self, path):
        self.settings['obs_path'] = path
        self._update_file_labels()
        self._save_settings()

    def _on_auto_obs_changed(self, checked):
        self.settings['auto_start_obs'] = checked
        self._save_settings()

    def _on_require_confirm_changed(self, checked):
        self.settings['require_confirmation'] = checked
        self._save_settings()

    def _on_timeout_changed(self, value):
        self.settings['window_timeout'] = value
        self._save_settings()

    def _on_confidence_changed(self, value):
        self.settings['image_confidence'] = value / 100.0
        self._save_settings()

    def _on_mouth_mask_changed(self, checked):
        self.settings['mouth_mask'] = checked
        self._save_settings()

    def _on_many_faces_changed(self, checked):
        self.settings['many_faces'] = checked
        self._save_settings()

    def _on_switch_json_changed(self, path):
        self.settings['switch_json_path'] = path
        self._save_settings()

    def _browse_script(self):
        """Browse for Deep Live Cam directory"""
        dialog = QFileDialog(self, "Select Deep Live Cam Folder")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        if dialog.exec():
            paths = dialog.selectedFiles()
            if paths:
                path = paths[0]
                self.ui['script_path'].setText(path)
                self.settings['deep_live_cam_dir'] = path
                self._save_settings()
                self._update_file_labels()

    def _browse_obs(self):
        """Browse for OBS executable"""
        dialog = QFileDialog(self, "Select OBS Executable")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter("Executable files (*.exe);;All files (*.*)")
        if dialog.exec():
            paths = dialog.selectedFiles()
            if paths:
                self.ui['obs_path'].setText(paths[0])
                self._update_file_labels()

    def _browse_switch_json(self):
        """Browse for custom switch_states.json"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Switch States JSON", "", "JSON files (*.json);;All files (*.*)"
        )
        if path:
            self.ui['switch_json'].setText(path)
            self.settings['switch_json_path'] = path
            self._save_settings()

    def _update_file_labels(self):
        """Update file selection labels"""
        logger = logging.getLogger(__name__)

        # Deep Live Cam directory check
        dlc_dir = self.ui['script_path'].text() or self.settings.get("deep_live_cam_dir", "")
        logger.info(f"🔍 Deep Live Cam dir: {dlc_dir}")
        venv_python = os.path.join(dlc_dir, "venv", "Scripts", "python.exe")
        run_py = os.path.join(dlc_dir, "run.py")
        logger.info(f"Checking paths:")
        logger.info(f" venv_python = {venv_python} -> exists: {os.path.exists(venv_python)}")
        logger.info(f" run_py = {run_py} -> exists: {os.path.exists(run_py)}")

        if dlc_dir and os.path.exists(venv_python) and os.path.exists(run_py):
            self.ui['script_file_label'].setText(f"✅ Deep Live Cam: {os.path.basename(dlc_dir)}")
            self.ui['script_file_label'].setStyleSheet("color: green; font-size: 9pt;")
            logger.info("✅ Deep Live Cam directory is valid.")
        else:
            self.ui['script_file_label'].setText("❌ No valid Deep Live Cam directory selected")
            self.ui['script_file_label'].setStyleSheet("color: red; font-size: 9pt;")
            logger.warning("❌ Deep Live Cam directory is invalid (missing venv or run.py).")

        # OBS executable check
        obs_path = self.ui['obs_path'].text() or self.settings.get("obs_path", "")
        logger.info(f"OBS path: {obs_path} -> exists: {os.path.exists(obs_path)}")
        if obs_path and os.path.exists(obs_path):
            self.ui['obs_file_label'].setText(f"✅ OBS: {os.path.basename(obs_path)}")
            self.ui['obs_file_label'].setStyleSheet("color: green; font-size: 9pt;")
            logger.info("✅ OBS executable found.")
        else:
            self.ui['obs_file_label'].setText("❌ No OBS executable selected")
            self.ui['obs_file_label'].setStyleSheet("color: red; font-size: 9pt;")
            logger.warning("❌ OBS executable not found.")

    def _open_switch_modal(self):
        """Open modal to edit switch_states.json"""
        dlc_dir = self.settings.get('deep_live_cam_dir', '')
        if not dlc_dir:
            QMessageBox.warning(self, "Warning", "Deep Live Cam directory not set")
            return

        switch_file = os.path.join(dlc_dir, "switch_states.json")
        if os.path.exists(switch_file):
            with open(switch_file, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "{}"

        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Switch States")
        dialog.setMinimumSize(400, 300)
        lay = QVBoxLayout(dialog)

        editor = QTextEdit()
        editor.setText(content)
        lay.addWidget(editor)

        btn_save = QPushButton("Save")
        btn_save.clicked.connect(lambda: self._save_switch_modal(editor.toPlainText(), switch_file, dialog))
        lay.addWidget(btn_save)

        dialog.exec()

    def _save_switch_modal(self, text, switch_file, dialog):
        """Save edited switch_states.json from modal"""
        try:
            data = json.loads(text)  # Validate JSON
            with open(switch_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "Success", "Switch states saved successfully!")
            dialog.close()
        except json.JSONDecodeError:
            QMessageBox.error(self, "Error", "Invalid JSON format!")

    def _start_automation(self):
        """Start automation process"""
        name, preset = self._selected_preset()
        if not preset:
            QMessageBox.warning(self, "Warning", "Please select a face preset first")
            return

        image_path = preset.get('image_path')
        if not image_path or not os.path.exists(image_path):
            QMessageBox.critical(self, "Error", f"Image file not found:\n{image_path}")
            return

        script_path = self.ui['script_path'].text()
        obs_path = self.ui['obs_path'].text()

        if not script_path or not os.path.exists(script_path):
            QMessageBox.critical(self, "Error", f"Deep Live Cam directory not found:\n{script_path}")
            return

        if self.settings.get('auto_start_obs', True) and (not obs_path or not os.path.exists(obs_path)):
            QMessageBox.critical(self, "Error", f"OBS executable not found:\n{obs_path}")
            return

        preset['last_used'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_presets()

        self._set_ui_enabled(False)
        self.worker = AutomationWorker(image_path, script_path, obs_path, self.settings)
        self.worker.status_changed.connect(self._update_status)
        self.worker.error_occurred.connect(self._on_automation_error)
        self.worker.finished_success.connect(self._on_automation_success)
        self.worker.finished_failure.connect(self._on_automation_failure)
        self.worker.start()
        self._update_status("🚀 Starting automation...")

    def _stop_automation(self):
        """Stop automation process and terminate running applications"""
        self.logger.info("Initiating stop all processes")
        try:
            # --- Step 1: Close Preview window ---
            try:
                logging.info("Connecting to 'Preview' window...")
                app = Application(backend="uia").connect(title="Preview")
                dlg = app.window(title="Preview")
                logging.info("Setting focus to 'Preview' window...")
                dlg.set_focus()
                logging.info("Closing 'Preview' window using dlg.close()...")
                dlg.close()
                logging.info("✅ 'Preview' window closed successfully")
            except ElementNotFoundError:
                logging.warning("⚠️ 'Preview' window not found")
            except Exception as e:
                logging.error(f"❌ Failed to close 'Preview' window: {e}")

            # --- Step 2: Close Deep Live Cam window ---
            try:
                logging.info("Connecting to 'Deep Live Cam' window...")
                app = Application(backend="uia").connect(title="Deep-Live-Cam 1.8 GitHub Edition")
                dlg = app.window(title="Deep-Live-Cam 1.8 GitHub Edition")
                logging.info("Setting focus to 'Deep Live Cam' window...")
                dlg.set_focus()
                logging.info("Closing 'Deep Live Cam' window using dlg.close()...")
                dlg.close()
                logging.info("✅ 'Deep Live Cam' window closed successfully")
            except ElementNotFoundError:
                logging.warning("⚠️ 'Deep Live Cam' window not found")
            except Exception as e:
                logging.error(f"❌ Failed to close 'Deep Live Cam' window: {e}")

            # --- Step 3: Kill leftover Deep Live Cam + OBS processes ---
            worker_script_path = getattr(self.worker, "script_path", None) if hasattr(self, "worker") else None
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = " ".join(proc.info['cmdline']) if proc.info['cmdline'] else ""
                    pname = proc.info['name'] or ""
                    # Kill Deep Live Cam (match run.py path from worker)
                    if worker_script_path and "run.py" in cmdline and worker_script_path.replace("\\", "/") in cmdline.replace("\\", "/"):
                        self.logger.info(f"Killing Deep Live Cam PID {proc.info['pid']} Cmdline: {cmdline}")
                        proc.terminate()
                        proc.wait(timeout=5)
                    # Kill OBS with taskkill
                    elif pname.lower() in ["obs.exe", "obs64.exe"]:
                        self.logger.info(f"Force killing OBS PID {proc.info['pid']}")
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(proc.info['pid'])],
                            capture_output=True, text=True
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    continue

            # --- Step 4: Update UI and log ---
            self._update_status("🛑 Stopped all processes")
            self.logger.info("All processes stopped successfully")
            self._set_ui_enabled(True)

        except Exception as e:
            self.logger.error(f"Error stopping processes: {e}")
            self._update_status(f"❌ Error stopping processes: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to stop processes: {str(e)}")

    def _on_automation_error(self, error_msg):
        """Handle automation error"""
        QMessageBox.critical(self, "Automation Error", error_msg)
        self._update_status(f"❌ Error: {error_msg}")

    def _on_automation_success(self):
        """Handle successful automation"""
        self._update_status("✅ Automation completed successfully!")
        self._set_ui_enabled(True)
        self.worker = None

    def _on_automation_failure(self, error_msg):
        """Handle failed automation"""
        self._update_status(f"❌ Automation failed: {error_msg}")
        self._set_ui_enabled(True)
        self.worker = None

    def _update_status(self, message):
        """Update status message"""
        self.ui['status'].setText(message)
        self.logger.info(message)

    def _set_ui_enabled(self, enabled):
        """Enable/disable UI controls"""
        has_selection = bool(self.ui['preset_list'].selectedItems())
        self.ui['btn_add'].setEnabled(enabled)
        self.ui['btn_edit'].setEnabled(enabled and has_selection)
        self.ui['btn_delete'].setEnabled(enabled and has_selection)
        self.ui['btn_start'].setEnabled(enabled and has_selection)
        self.ui['btn_stop'].setEnabled(True)  # Always keep Stop All button enabled
        self.ui['preset_list'].setEnabled(enabled)
        self.ui['script_path'].setEnabled(enabled)
        self.ui['obs_path'].setEnabled(enabled)
        self.ui['btn_browse_script'].setEnabled(enabled)
        self.ui['btn_browse_obs'].setEnabled(enabled)
        self.ui['auto_obs'].setEnabled(enabled)
        self.ui['require_confirm'].setEnabled(enabled)
        self.ui['timeout'].setEnabled(enabled)
        self.ui['confidence'].setEnabled(enabled)
        self.ui['mouth_mask'].setEnabled(enabled)
        self.ui['many_faces'].setEnabled(enabled)
        self.ui['switch_json'].setEnabled(enabled)
        self.ui['btn_browse_switch'].setEnabled(enabled)
        self.ui['btn_edit_switches'].setEnabled(enabled)