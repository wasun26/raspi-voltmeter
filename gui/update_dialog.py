"""A small non-blocking update dialog for the desktop application."""
from pathlib import Path
import sys

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app_update import check_for_update, install_update


class UpdateWorker(QThread):
    result_ready = pyqtSignal(object, object)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.result_ready.emit(self.operation(), None)
        except Exception as exc:
            self.result_ready.emit(None, exc)


class UpdateDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.repo = Path(__file__).resolve().parent.parent
        self.info = None
        self.worker = None
        self.busy = False
        self.setWindowTitle("Update Voltmeter")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        self.status = QLabel("Checking for updates...")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        self.update_button = QPushButton("Update and restart")
        self.update_button.setEnabled(False)
        self.update_button.clicked.connect(self._install)
        actions.addWidget(self.update_button)
        self.close_button = QPushButton("Close")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.reject)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)
        self._start(lambda: check_for_update(self.repo), self._checked)

    def _start(self, operation, callback):
        self.busy = True
        self.close_button.setEnabled(False)
        self.update_button.setEnabled(False)
        self.worker = UpdateWorker(operation, self)
        self.worker.result_ready.connect(callback)
        self.worker.start()

    def _checked(self, info, error):
        self.worker.wait(1000)
        self.busy = False
        self.close_button.setEnabled(True)
        if error is not None:
            self.status.setText(f"Could not check for updates:\n{error}")
        elif not info.needs_update:
            self.status.setText("Voltmeter is up to date.")
        else:
            self.info = info
            self.status.setText(
                f"An update is available ({info.available[:8]}). "
                "Updating will pause measurement, close the current CSV file, "
                "and restart the app. Saved files will be kept."
            )
            self.update_button.setEnabled(True)

    def _install(self):
        if not self.main_window.prepare_for_update():
            self.status.setText(self.main_window.update_error_detail)
            self.update_button.setEnabled(False)
            return
        self.status.setText("Installing update... This may take a few minutes.")
        self._start(lambda: install_update(self.repo, self.info, sys.executable), self._installed)

    def _installed(self, _, error):
        self.worker.wait(1000)
        self.busy = False
        if error is not None:
            self.status.setText(f"Update failed:\n{error}\nPrevious code is still available.")
            try:
                self.main_window.resume_after_failed_update()
            except Exception as resume_error:
                self.status.setText(self.status.text() + f"\nCould not resume measurement: {resume_error}")
            self.close_button.setEnabled(True)
            return
        self.status.setText("Updated. Restarting Voltmeter...")
        self.main_window.restart_after_update(self)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)
