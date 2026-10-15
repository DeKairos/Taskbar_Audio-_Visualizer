"""Run a bundled app's device-free release checks without opening the desktop UI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def verify(executable, expected_version):
    with tempfile.TemporaryDirectory(prefix="audio-visualizer-smoke-") as temp:
        report = Path(temp) / "result.json"
        subprocess.run(
            [str(Path(executable).resolve()), "--self-test", str(report)],
            check=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        result = json.loads(report.read_text(encoding="utf-8"))
        if not result["ok"] or result["version"] != expected_version:
            raise RuntimeError(f"Frozen build verification failed: {result}")
        print(f"Frozen build verified: {result}")


if __name__ == "__main__":
    verify(sys.argv[1], sys.argv[2])
