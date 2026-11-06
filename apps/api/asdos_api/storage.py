from __future__ import annotations

import hashlib
import os
import re
import tempfile
from typing import BinaryIO
from pathlib import Path
from uuid import uuid4

from .config import settings

KEY_RE = re.compile(r"^[a-f0-9]{2}/[a-f0-9-]{36}$")


class ArtifactStore:
    """Private, atomic filesystem store. Public URLs never expose storage paths."""

    def __init__(self, root: Path | None = None):
        self.root = (root or settings.artifact_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)

    @staticmethod
    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def put(self, data: bytes) -> tuple[str, str, int]:
        from io import BytesIO

        return self.put_stream(BytesIO(data), max_bytes=len(data))

    def put_stream(self, source: BinaryIO, *, max_bytes: int) -> tuple[str, str, int]:
        artifact_id = str(uuid4())
        key = f"{artifact_id[:2]}/{artifact_id}"
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=destination.parent)
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(fd, "wb") as stream:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("UPLOAD_TOO_LARGE")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return key, digest.hexdigest(), size

    def put_file(self, source: Path) -> tuple[str, str, int]:
        return self.put(source.read_bytes())

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def path(self, key: str) -> Path:
        return self._path(key)

    def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        if not KEY_RE.fullmatch(key):
            raise ValueError("invalid private artifact key")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("artifact path escapes private store")
        return path


artifact_store = ArtifactStore()
