import fcntl
import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "recall.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def launcher_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    home = tmp_path / "home"
    state = tmp_path / "state"
    runtime = tmp_path / "runtime"
    for directory in (bin_dir, home, state, runtime):
        directory.mkdir()
    authority = runtime / "Xauthority"
    authority.write_text("auth", encoding="utf-8")
    capture = tmp_path / "gnome-args"

    write_executable(
        bin_dir / "systemctl",
        "#!/bin/bash\nprintf 'DISPLAY=:0\\nWAYLAND_DISPLAY=wayland-0\\nXAUTHORITY=%s\\n' \"$TEST_XAUTHORITY\"\n",
    )
    write_executable(
        bin_dir / "gnome-terminal",
        '#!/bin/bash\nprintf \'%s\\n\' "$@" > "$TEST_CAPTURE"\nexit "${GNOME_STATUS:-0}"\n',
    )
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_STATE_HOME": str(state),
        "XDG_RUNTIME_DIR": str(runtime),
        "EXTRA_PATH": str(bin_dir),
        "TEST_XAUTHORITY": str(authority),
        "TEST_CAPTURE": str(capture),
    }
    for variable in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"):
        env.pop(variable, None)
    return env, capture


def test_launcher_preserves_terminal_exit_status(
    launcher_environment: tuple[dict[str, str], Path],
) -> None:
    env, _ = launcher_environment
    env["GNOME_STATUS"] = "7"

    result = subprocess.run([SCRIPT], env=env, check=False)

    assert result.returncode == 7


def test_launcher_passes_application_command(
    launcher_environment: tuple[dict[str, str], Path],
) -> None:
    env, capture = launcher_environment

    result = subprocess.run([SCRIPT], env=env, check=False)

    assert result.returncode == 0
    assert capture.read_text(encoding="utf-8").splitlines()[-3:] == ["uv", "run", "main.py"]


def test_launcher_skips_overlapping_session(
    launcher_environment: tuple[dict[str, str], Path],
) -> None:
    env, _ = launcher_environment
    lock_path = Path(env["XDG_STATE_HOME"]) / "code-recall/recall.lock"
    lock_path.parent.mkdir(mode=0o700)

    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run([SCRIPT], env=env, check=False)

    assert result.returncode == 0
    log = Path(env["XDG_STATE_HOME"]) / "code-recall/recall-error.log"
    assert "already running" in log.read_text(encoding="utf-8")


def test_launcher_reports_lock_failure(
    launcher_environment: tuple[dict[str, str], Path],
) -> None:
    env, _ = launcher_environment
    flock = Path(env["EXTRA_PATH"]) / "flock"
    write_executable(flock, "#!/bin/bash\nexit 2\n")

    result = subprocess.run([SCRIPT], env=env, check=False)

    assert result.returncode == 2
    log = Path(env["XDG_STATE_HOME"]) / "code-recall/recall-error.log"
    assert "Could not acquire" in log.read_text(encoding="utf-8")
