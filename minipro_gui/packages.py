"""Packages: a saved device + image file + options for repeat programming jobs.

Each package is stored as a small JSON file in the user's data directory.
A package can also be exported as a self-contained ``.minipkg`` bundle (a zip
holding the JSON plus a copy of the image) to move it to another machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .minipro import Operation, ProgramOptions

PACKAGE_EXT = ".minipkg"
FORMAT_VERSION = 1


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.")
    return slug or "package"


@dataclass
class Package:
    name: str
    device: str
    image: str
    programmer: str = ""
    operation: str = Operation.WRITE.value
    options: ProgramOptions = field(default_factory=ProgramOptions)
    notes: str = ""
    image_sha256: str = ""
    created: str = field(default_factory=_now)
    modified: str = field(default_factory=_now)
    # Running totals across sessions, handy for small production runs.
    runs_ok: int = 0
    runs_failed: int = 0
    # File name inside the store directory (set by PackageStore).
    file_name: str = ""

    def to_dict(self) -> dict:
        return {
            "format": FORMAT_VERSION,
            "name": self.name,
            "device": self.device,
            "image": self.image,
            "programmer": self.programmer,
            "operation": self.operation,
            "options": self.options.to_dict(),
            "notes": self.notes,
            "image_sha256": self.image_sha256,
            "created": self.created,
            "modified": self.modified,
            "runs_ok": self.runs_ok,
            "runs_failed": self.runs_failed,
        }

    @classmethod
    def from_dict(cls, data: dict, file_name: str = "") -> Package:
        return cls(
            name=data.get("name") or "Untitled",
            device=data.get("device", ""),
            image=data.get("image", ""),
            programmer=data.get("programmer", ""),
            operation=data.get("operation", Operation.WRITE.value),
            options=ProgramOptions.from_dict(data.get("options")),
            notes=data.get("notes", ""),
            image_sha256=data.get("image_sha256", ""),
            created=data.get("created", _now()),
            modified=data.get("modified", _now()),
            runs_ok=int(data.get("runs_ok", 0)),
            runs_failed=int(data.get("runs_failed", 0)),
            file_name=file_name,
        )

    def record_checksum(self) -> None:
        self.image_sha256 = sha256_of(self.image) if os.path.isfile(self.image) else ""

    def image_status(self) -> str:
        """'ok', 'missing', 'changed' or 'unknown' (no checksum recorded)."""
        if not self.image or not os.path.isfile(self.image):
            return "missing"
        if not self.image_sha256:
            return "unknown"
        return "ok" if sha256_of(self.image) == self.image_sha256 else "changed"


class PackageStore:
    def __init__(self, root: str) -> None:
        self.root = root
        self.images_dir = os.path.join(root, "images")
        os.makedirs(self.root, exist_ok=True)

    # -- basic CRUD --------------------------------------------------------

    def load_all(self) -> list[Package]:
        packages = []
        for entry in sorted(os.listdir(self.root)):
            if not entry.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.root, entry), encoding="utf-8") as fh:
                    packages.append(Package.from_dict(json.load(fh), entry))
            except (OSError, ValueError):
                continue  # skip unreadable files rather than refusing to start
        return sorted(packages, key=lambda p: p.name.lower())

    def find_by_name(self, name: str) -> Package | None:
        return next((p for p in self.load_all() if p.name.lower() == name.lower()), None)

    def save(self, package: Package) -> Package:
        if not package.file_name:
            package.file_name = self._unique_file_name(slugify(package.name))
        package.modified = _now()
        path = os.path.join(self.root, package.file_name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(package.to_dict(), fh, indent=2)
        os.replace(tmp, path)
        return package

    def delete(self, package: Package) -> None:
        if package.file_name:
            path = os.path.join(self.root, package.file_name)
            if os.path.exists(path):
                os.remove(path)
        # Images that came from an imported bundle live in our store; remove
        # them too unless another package still uses the same file.
        if package.image.startswith(self.images_dir + os.sep):
            still_used = any(p.image == package.image for p in self.load_all())
            if not still_used and os.path.exists(package.image):
                os.remove(package.image)

    def _unique_file_name(self, slug: str) -> str:
        candidate, n = f"{slug}.json", 2
        while os.path.exists(os.path.join(self.root, candidate)):
            candidate, n = f"{slug}-{n}.json", n + 1
        return candidate

    # -- bundles -----------------------------------------------------------

    @staticmethod
    def export_bundle(package: Package, dest: str) -> None:
        """Write a zip containing package.json and the image file."""
        if not os.path.isfile(package.image):
            raise FileNotFoundError(f"Image file not found: {package.image}")
        image_name = os.path.basename(package.image)
        data = package.to_dict()
        data["image"] = image_name
        data["runs_ok"] = data["runs_failed"] = 0
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("package.json", json.dumps(data, indent=2))
            zf.write(package.image, f"image/{image_name}")

    def import_bundle(self, src: str) -> Package:
        with zipfile.ZipFile(src) as zf:
            data = json.loads(zf.read("package.json"))
            image_members = [n for n in zf.namelist() if n.startswith("image/") and not n.endswith("/")]
            if not image_members:
                raise ValueError("The package bundle does not contain an image file.")
            member = image_members[0]
            os.makedirs(self.images_dir, exist_ok=True)
            base = os.path.basename(member)
            stem, ext = os.path.splitext(base)
            target, n = os.path.join(self.images_dir, base), 2
            while os.path.exists(target):
                target, n = os.path.join(self.images_dir, f"{stem}-{n}{ext}"), n + 1
            with zf.open(member) as src_fh, open(target, "wb") as dst_fh:
                shutil.copyfileobj(src_fh, dst_fh)

        package = Package.from_dict(data)
        package.image = target
        if package.image_sha256 and sha256_of(target) != package.image_sha256:
            os.remove(target)
            raise ValueError("The image inside the bundle is corrupt (checksum mismatch).")
        package.record_checksum()
        if self.find_by_name(package.name):
            package.name = self._unique_name(package.name)
        return self.save(package)

    def _unique_name(self, name: str) -> str:
        existing = {p.name.lower() for p in self.load_all()}
        n = 2
        while f"{name} ({n})".lower() in existing:
            n += 1
        return f"{name} ({n})"
