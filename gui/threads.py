from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QFileDialog

class CalendarRefreshThread(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, calendar_service):
        super().__init__()
        self.calendar_service = calendar_service

    def run(self):
        try:
            events = self.calendar_service.fetch_events() or []
            self.finished.emit(events)
        except Exception as e:
            self.error.emit(str(e))

class FileDialogThread(QThread):
    result = pyqtSignal(str)

    def __init__(self, parent, dialog_type, title, filter_str=None):
        super().__init__(parent)
        self.dialog_type = dialog_type
        self.title = title
        self.filter_str = filter_str

    def run(self):
        path = ""
        if self.dialog_type == "directory":
            path = QFileDialog.getExistingDirectory(self.parent(), self.title, "")
        elif self.dialog_type == "file":
            path, _ = QFileDialog.getOpenFileName(self.parent(), self.title, "", self.filter_str)
        self.result.emit(path)

class DeepLiveWorker(QThread):
    finished = pyqtSignal(object, str)

    def __init__(self, service, deeplive_dir, full_image_path, settings):
        super().__init__()
        self.service = service
        self.deeplive_dir = deeplive_dir
        self.full_image_path = full_image_path
        self.settings = settings

    def run(self):
        try:
            process = self.service.start_deeplive(self.deeplive_dir, self.full_image_path, self.settings)
            self.finished.emit(process, "")
        except Exception as e:
            self.finished.emit(None, str(e))