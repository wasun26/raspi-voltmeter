"""Recording preferences; applying them starts a new session while paused."""
import re

from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSpinBox, QVBoxLayout,
    QPushButton,
)


class RecordingSettingsDialog(QDialog):
    def __init__(self, recorder, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recording settings")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        note = QLabel("Apply while paused. New settings start a new CSV session; existing files are kept.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.directory = QLineEdit(str(recorder.directory))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.directory)
        folder_row.addWidget(browse)
        form.addRow("Save folder", folder_row)
        self.prefix = QLineEdit(recorder.file_prefix)
        self.prefix.setMaxLength(64)
        self.prefix.setToolTip("Letters, numbers, underscores and hyphens. Date/session/part are added automatically.")
        form.addRow("File name prefix", self.prefix)
        self.max_lines = QSpinBox()
        self.max_lines.setRange(0, 2147483647)
        self.max_lines.setSpecialValueText("No line limit")
        self.max_lines.setValue(recorder.max_data_lines)
        self.max_lines.setToolTip("Data rows per file, excluding header. On reaching this limit, continue in a new file.")
        form.addRow("Max data lines / file", self.max_lines)
        self.daily = QCheckBox("Start a new file each calendar day")
        self.daily.setChecked(recorder.rotate_daily)
        form.addRow("Daily rotation", self.daily)
        self.min_free = QSpinBox()
        self.min_free.setRange(0, 1000000)
        self.min_free.setSuffix(" MiB")
        self.min_free.setSpecialValueText("No reserved space")
        self.min_free.setValue(recorder.min_free_mb)
        self.min_free.setToolTip("Stop acquisition below this free-space threshold. Checked every 5 seconds; never delete old files.")
        form.addRow("Minimum free drive space", self.min_free)
        layout.addLayout(form)
        safety = QLabel("CSV • mV • Sync every reading\nNo automatic deletion or overwriting. A full drive or write error stops acquisition.")
        safety.setWordWrap(True)
        layout.addWidget(safety)
        self.remember = QCheckBox("Remember these settings for next launch")
        self.remember.setChecked(True)
        layout.addWidget(self.remember)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply / new session")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose save folder", self.directory.text())
        if directory:
            self.directory.setText(directory)

    def recording_options(self):
        return dict(directory=self.directory.text().strip(), file_prefix=self.prefix.text().strip(),
                    max_data_lines=self.max_lines.value(), rotate_daily=self.daily.isChecked(),
                    min_free_mb=self.min_free.value())

    def accept(self):
        options = self.recording_options()
        if not options["directory"]:
            QMessageBox.warning(self, "Recording settings", "Choose a save folder.")
            return
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", options["file_prefix"]):
            QMessageBox.warning(self, "Recording settings", "Prefix must start with a letter or number and contain only letters, numbers, underscores or hyphens.")
            return
        super().accept()
