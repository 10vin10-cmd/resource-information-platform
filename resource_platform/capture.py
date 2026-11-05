"""Content-addressed capture of source files.

Every file that enters the platform is stored under its SHA-256 digest and never
changed afterwards. A manifest line records where it came from, so any figure
the platform reports can be traced to the exact bytes it was read from.

    store/
      objects/ab/abcdef...       the file, named by its digest
      manifest.jsonl             one line per capture: digest, source, time
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Capture:
    digest: str            # sha256 of the file's bytes
    dataset: str           # dataset id from datasets/*.yaml
    source_url: str
    publisher: str
    captured_at: str       # ISO 8601, UTC
    size: int
    filename: str
    synthetic: bool = False

    @property
    def short(self) -> str:
        return self.digest[:12]


class Store:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.manifest = self.root / "manifest.jsonl"

    def path(self, digest: str) -> Path:
        return self.objects / digest[:2] / digest

    def capture(self, file: Path | str, dataset: str, source_url: str, publisher: str,
                synthetic: bool = False, now: datetime | None = None) -> Capture:
        file = Path(file)
        digest = sha256_file(file)
        target = self.path(digest)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            shutil.copyfile(file, tmp)
            os.chmod(tmp, 0o444)
            tmp.replace(target)
        existing = self.find(digest, dataset)
        if existing:
            return existing  # same bytes for the same dataset: nothing new
        cap = Capture(digest=digest, dataset=dataset, source_url=source_url, publisher=publisher,
                      captured_at=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
                      size=target.stat().st_size, filename=file.name, synthetic=synthetic)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.manifest.open("a") as fh:
            fh.write(json.dumps(asdict(cap), sort_keys=True) + "\n")
        return cap

    def captures(self) -> list[Capture]:
        if not self.manifest.exists():
            return []
        return [Capture(**json.loads(line)) for line in self.manifest.read_text().splitlines()
                if line.strip()]

    def find(self, digest: str, dataset: str | None = None) -> Capture | None:
        for cap in self.captures():
            if cap.digest.startswith(digest) and (dataset is None or cap.dataset == dataset):
                return cap
        return None

    def latest(self, dataset: str) -> Capture | None:
        caps = [c for c in self.captures() if c.dataset == dataset]
        return max(caps, key=lambda c: c.captured_at) if caps else None

    def open_verified(self, digest: str) -> bytes:
        """The captured bytes, after checking they still match their name."""
        data = self.path(digest).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest:
            raise IntegrityError(f"object {digest[:12]} has changed on disk (now {actual[:12]})")
        return data

    def verify(self) -> list[str]:
        """Digests whose stored bytes no longer match. Empty means intact."""
        bad = []
        for cap in self.captures():
            try:
                self.open_verified(cap.digest)
            except (IntegrityError, FileNotFoundError):
                bad.append(cap.digest)
        return bad


class IntegrityError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
