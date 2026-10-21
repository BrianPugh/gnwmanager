import hashlib
from pathlib import Path

import pytest

from gnwmanager.cli import _patch
from gnwmanager.cli._patch import PatchError, detect_device, patch_argv
from gnwmanager.gnw_patch.patches import Device

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_stock(monkeypatch):
    """Make ``data`` pass as ``model``'s stock internal backup."""

    def fake(model, data):
        monkeypatch.setattr(Device.registry[model].Int, "STOCK_ROM_SHA1_HASH", hashlib.sha1(data).hexdigest())

    return fake


def test_detect_device(tmp_path, fake_stock):
    fake_stock("zelda", b"zelda")
    (tmp_path / "internal_flash_backup_zelda.bin").write_bytes(b"zelda")
    assert detect_device(tmp_path) == "zelda"


def test_detect_device_both(tmp_path, fake_stock):
    for model in ("mario", "zelda"):
        fake_stock(model, model.encode())
        (tmp_path / f"internal_flash_backup_{model}.bin").write_bytes(model.encode())
    with pytest.raises(PatchError, match="both models"):
        detect_device(tmp_path)


def test_detect_device_not_stock(tmp_path):
    (tmp_path / "internal_flash_backup_mario.bin").write_bytes(b"patched")
    with pytest.raises(PatchError, match="not a stock backup"):
        detect_device(tmp_path)


def test_detect_device_missing(tmp_path):
    with pytest.raises(PatchError, match="No internal_flash_backup_mario.bin"):
        detect_device(tmp_path)


def test_patch_argv_defaults(tmp_path, fake_stock):
    fake_stock("mario", b"mario")
    (tmp_path / "internal_flash_backup_mario.bin").write_bytes(b"mario")
    work = tmp_path / "work"
    argv = patch_argv([f"--backup-dir={tmp_path}", "--sd-bootloader"], work)
    assert argv[0] == "--device=mario"
    assert "--sd-bootloader" in argv
    assert any(a.startswith("--prebuilt=") and a.endswith("patch_elfs") for a in argv)
    assert f"--int-output={work / 'internal_flash_patched.bin'}" in argv
    assert f"--ext-output={work / 'external_flash_patched.bin'}" in argv
    assert f"--dump-dir={work / 'debug'}" in argv


def test_patch_argv_keeps_given(tmp_path):
    given = ["--device=amalgam", "--elf=x.elf", "--patch=x.bin", "--int-output=a.bin", "--dump-dir=d"]
    assert patch_argv(given, tmp_path) == [*given, f"--ext-output={tmp_path / 'external_flash_patched.bin'}"]


def test_patch_argv_help(tmp_path):
    # No backups needed.
    assert patch_argv(["--device=zelda", _patch.PATCHER_HELP], tmp_path) == ["--device=zelda", "--help"]


@pytest.mark.skipif(not (REPO / "gnwmanager" / "patch_elfs" / "manifest.json").exists(), reason="needs make patch-elfs")
@pytest.mark.skipif(not (REPO / "internal_flash_backup_mario.bin").exists(), reason="needs the stock mario backups")
def test_patch_mario(tmp_path, capsys):
    from gnwmanager.gnw_patch.patches import cli

    cli.main(patch_argv([f"--backup-dir={REPO}", "--device=mario"], tmp_path))
    assert (tmp_path / "internal_flash_patched.bin").stat().st_size == 0x20000
    assert (tmp_path / "external_flash_patched.bin").stat().st_size
