"""Safe Git update checks for an installed checkout of this application."""
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import tempfile


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    available: str
    needs_update: bool
    requirements_changed: bool


def _run(*args, repo, timeout=120):
    try:
        result = subprocess.run(
            args, cwd=repo, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(str(exc)) from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise UpdateError(detail or f"Command failed: {args[0]}")
    return result.stdout.strip()


def _git(repo, *args, timeout=120):
    return _run("git", *args, repo=repo, timeout=timeout)


def _check_local_checkout(repo):
    repo = Path(repo).resolve()
    if Path(_git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise UpdateError("The app must be installed from its Git repository.")
    if _git(repo, "branch", "--show-current") != "main":
        raise UpdateError("Updates require the main branch. Ask the maintainer to check this installation.")
    if _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}") != "origin/main":
        raise UpdateError("The main branch must track origin/main.")
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise UpdateError("Local code changes were found. Ask the maintainer to save them before updating.")
    return repo


def _require_fast_forward(repo, current, available):
    try:
        _git(repo, "merge-base", "--is-ancestor", current, available)
    except UpdateError as exc:
        raise UpdateError("Local and remote versions diverged. Ask the maintainer to resolve them.") from exc


def check_for_update(repo):
    """Fetch the remote branch without changing application files."""
    repo = _check_local_checkout(repo)
    _git(repo, "fetch", "--no-tags", "origin", "main", timeout=45)
    current = _git(repo, "rev-parse", "HEAD")
    available = _git(repo, "rev-parse", "origin/main")
    if current != available:
        _require_fast_forward(repo, current, available)
    requirements_changed = bool(
        _git(repo, "diff", "--name-only", current, available, "--", "requirements.txt")
    )
    return UpdateInfo(current, available, current != available, requirements_changed)


def install_update(repo, info, python=sys.executable):
    """Install dependencies first, then fast-forward to the checked commit."""
    repo = _check_local_checkout(repo)
    if _git(repo, "rev-parse", "HEAD") != info.current:
        raise UpdateError("The local version changed since the update check. Check again.")
    if _git(repo, "rev-parse", "origin/main") != info.available:
        raise UpdateError("The available version changed. Check again.")
    if not info.needs_update:
        return
    _require_fast_forward(repo, info.current, info.available)
    if info.requirements_changed:
        requirements = _git(repo, "show", f"{info.available}:requirements.txt")
        with tempfile.TemporaryDirectory(prefix="voltmeter_update_") as temp:
            requirement_file = Path(temp) / "requirements.txt"
            requirement_file.write_text(requirements + "\n", encoding="utf-8")
            _run(python, "-m", "pip", "install", "-r", str(requirement_file),
                 repo=repo, timeout=600)
    _git(repo, "merge", "--ff-only", info.available)
