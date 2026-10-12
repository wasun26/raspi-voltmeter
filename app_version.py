"""Application version stored alongside the source release."""
from pathlib import Path


APP_VERSION = (Path(__file__).resolve().parent / "VERSION").read_text(
    encoding="utf-8"
).strip()
