"""Read a repository tree at a commit without checking it out."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from editslice.graph import skip_path


def files_at_commit(repo: Path, commit: str) -> dict[str, str]:
    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", commit],
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [
        path
        for path in listed.stdout.splitlines()
        if path.endswith(".py") and not skip_path(path)
    ]
    files: dict[str, str] = {}
    if not paths:
        return files

    proc = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None

    def _write() -> None:
        assert proc.stdin is not None
        for path in paths:
            proc.stdin.write(f"{commit}:{path}\n".encode())
        proc.stdin.close()

    writer = threading.Thread(target=_write)
    writer.start()
    try:
        for path in paths:
            header = proc.stdout.readline()
            if not header:
                break
            parts = header.decode("utf-8", "replace").split()
            if len(parts) < 3 or "missing" in parts:
                continue
            size = int(parts[2])
            blob = proc.stdout.read(size)
            proc.stdout.read(1)
            if size > 500_000:
                continue
            files[path] = blob.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
    finally:
        writer.join()
        proc.wait()
    return files
