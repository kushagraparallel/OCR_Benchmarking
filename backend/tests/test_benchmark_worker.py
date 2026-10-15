"""Regression test for a real, Windows-only native DLL load-order conflict.

Unlike the rest of the OCR adapter test suite, this test deliberately uses
the real `torch` and `paddlepaddle` packages instead of mocks: the bug it
guards against is a native-library interaction that only reproduces with the
actual installed binaries, discovered by running all four OCR engines
together through the real worker (see app/workers/benchmark_worker.py's
``_import_torch_before_paddle_on_windows`` for the full explanation).
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent

_REAL_DEPENDENCIES_INSTALLED = (
    importlib.util.find_spec("torch") is not None and importlib.util.find_spec("paddle") is not None
)

requires_torch_and_paddle = pytest.mark.skipif(
    not _REAL_DEPENDENCIES_INSTALLED,
    reason="requires the real torch and paddlepaddle packages installed (optional OCR engines)",
)


def _run(script: str) -> subprocess.CompletedProcess[str]:
    """Run a short script in a fresh subprocess with the backend on the path."""
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )


@requires_torch_and_paddle
@pytest.mark.skipif(sys.platform != "win32", reason="the conflict this guards against is Windows-only")
def test_paddle_imported_before_torch_breaks_torch_without_the_fix() -> None:
    """Confirm the underlying OS/library bug actually reproduces (a true negative control).

    If this assertion ever starts failing on its own, a future torch/paddle
    release has likely fixed the conflict upstream and the workaround in
    ``benchmark_worker.py`` may no longer be needed.
    """
    result = _run("import paddle\nimport torch\n")
    assert result.returncode != 0
    assert "shm.dll" in result.stderr or "WinError 127" in result.stderr


@requires_torch_and_paddle
def test_importing_benchmark_worker_before_paddle_keeps_torch_usable() -> None:
    """The worker module's import-order guard must prevent the conflict above."""
    result = _run("import app.workers.benchmark_worker\nimport paddle\nimport torch\nprint('OK')\n")
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
