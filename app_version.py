"""Application name and source release version."""
from pathlib import Path


APP_NAME = "Piezoelectric Monitor"
APP_VERSION = (Path(__file__).resolve().parent / "VERSION").read_text(
    encoding="utf-8"
).strip()
