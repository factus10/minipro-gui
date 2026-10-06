import os

import pytest

from minipro_gui.minipro import ProgramOptions
from minipro_gui.packages import Package, PackageStore


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "rom.bin"
    path.write_bytes(bytes(range(256)) * 128)
    return str(path)


def test_save_load_roundtrip(tmp_path, image):
    store = PackageStore(str(tmp_path / "store"))
    pkg = Package(name="Board ROM", device="AT28C256", image=image,
                  options=ProgramOptions(allow_size_mismatch=True))
    pkg.record_checksum()
    store.save(pkg)
    [loaded] = store.load_all()
    assert loaded.name == "Board ROM"
    assert loaded.options.allow_size_mismatch
    assert loaded.image_status() == "ok"


def test_image_status_detects_change_and_missing(tmp_path, image):
    pkg = Package(name="x", device="d", image=image)
    pkg.record_checksum()
    with open(image, "ab") as fh:
        fh.write(b"\x00")
    assert pkg.image_status() == "changed"
    os.remove(image)
    assert pkg.image_status() == "missing"


def test_unique_file_names(tmp_path, image):
    store = PackageStore(str(tmp_path / "store"))
    a = store.save(Package(name="Same/Name", device="d", image=image))
    b = store.save(Package(name="Same/Name", device="d", image=image))
    assert a.file_name != b.file_name
    assert len(store.load_all()) == 2


def test_export_import_bundle(tmp_path, image):
    src = PackageStore(str(tmp_path / "a"))
    pkg = Package(name="Bundle me", device="W25Q32BV", image=image, notes="hello")
    pkg.record_checksum()
    pkg.runs_ok = 7
    src.save(pkg)
    bundle = str(tmp_path / "out.minipkg")
    src.export_bundle(pkg, bundle)

    dst = PackageStore(str(tmp_path / "b"))
    imported = dst.import_bundle(bundle)
    assert imported.name == "Bundle me"
    assert imported.notes == "hello"
    assert imported.runs_ok == 0
    assert imported.image.startswith(dst.images_dir)
    assert imported.image_status() == "ok"

    again = dst.import_bundle(bundle)  # same name gets a suffix, image gets a new file
    assert again.name == "Bundle me (2)"
    assert again.image != imported.image

    dst.delete(again)
    assert not os.path.exists(again.image)
    assert os.path.exists(imported.image)
