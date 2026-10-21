import hashlib
from pathlib import Path

import pytest

from gnwmanager.cli import _patch
from gnwmanager.cli._patch import PatchError, detect_device, patch_command
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
    argv = patch_command([f"--backup-dir={tmp_path}", "--sd-bootloader"], work).argv
    assert argv[0] == "--device=mario"
    assert "--sd-bootloader" in argv
    assert f"--prebuilt={work / 'patch_elfs'}" in argv
    assert f"--int-output={work / 'internal_flash_patched.bin'}" in argv
    assert f"--ext-output={work / 'external_flash_patched.bin'}" in argv
    assert f"--dump-dir={work / 'debug'}" in argv


def test_patch_argv_keeps_given(tmp_path):
    given = ["--device=amalgam", "--elf=x.elf", "--patch=x.bin", "--int-output=a.bin", "--dump-dir=d"]
    assert patch_command(given, tmp_path).argv == [*given, f"--ext-output={tmp_path / 'external_flash_patched.bin'}"]


def test_patch_argv_help(tmp_path):
    # No backups needed.
    assert patch_command(["--device=zelda", _patch.PATCHER_HELP], tmp_path).argv == ["--device=zelda", "--help"]
    assert patch_command(["zelda", _patch.PATCHER_HELP], tmp_path).argv == ["--device=zelda", "--help"]


def _backups(tmp_path, model):
    internal, external = tmp_path / "int.bin", tmp_path / "ext.bin"
    internal.write_bytes(model.encode())
    external.write_bytes(b"external")
    return internal, external


def test_legacy_form(tmp_path, fake_stock):
    """``flash-patch MODEL INTERNAL EXTERNAL [OPTIONS]``, as gnwmanager had it."""
    fake_stock("mario", b"mario")
    internal, external = _backups(tmp_path, "mario")
    work = tmp_path / "work"
    argv = [
        "mario",
        str(internal),
        str(external),
        "--bootloader",
        "--sleep-time",
        "60",
        "--bootloader-tag",
        "v1.0.3",
    ]
    cmd = patch_command(argv, work)
    assert cmd.argv[:4] == ["--device=mario", "--sd-bootloader", "--sleep-time", "60"]
    assert f"--backup-dir={work / 'backups'}" in cmd.argv
    assert (work / "backups" / "internal_flash_backup_mario.bin").read_bytes() == b"mario"
    assert (work / "backups" / "flash_backup_mario.bin").read_bytes() == b"external"
    assert (cmd.bootloader_repo, cmd.bootloader_tag) == (_patch.BOOTLOADER_REPO, "v1.0.3")


def test_legacy_paths_detect_model(tmp_path, fake_stock):
    fake_stock("zelda", b"zelda")
    internal, external = _backups(tmp_path, "zelda")
    argv = patch_command([str(internal), str(external)], tmp_path / "work").argv
    assert argv[0] == "--device=zelda"


def test_legacy_no_second_beep(tmp_path, caplog):
    argv = patch_command(["zelda", "--no-second-beep", "--elf=x.elf", "--patch=x.bin"], tmp_path).argv
    assert "--no-second-beep" not in argv
    assert "clock menu" in caplog.text


def test_bootloader_options(tmp_path):
    cmd = patch_command(["mario", "--bootloader-repo=me/bl", "--elf=x.elf", "--patch=x.bin"], tmp_path)
    assert (cmd.bootloader_repo, cmd.bootloader_tag) == ("me/bl", "latest")
    assert not any(a.startswith("--bootloader") for a in cmd.argv)


@pytest.mark.parametrize(
    ("argv", "match"),
    [
        (["mario", "--device=zelda"], "Give the model once"),
        (["mario", "a.bin"], "Expected the 2 stock backups"),
        (["mario", "a.bin", "b.bin", "--backup-dir=."], "not both"),
        (["mario", "missing.bin", "missing2.bin"], "no such file"),
    ],
)
def test_legacy_errors(tmp_path, argv, match):
    with pytest.raises(PatchError, match=match):
        patch_command(argv, tmp_path)


def test_legacy_amalgam_paths(tmp_path):
    internal, external = _backups(tmp_path, "mario")
    with pytest.raises(PatchError, match="reads its backups from --backup-dir"):
        patch_command(["amalgam", str(internal), str(external)], tmp_path / "work")


@pytest.mark.skipif(not (REPO / "gnwmanager" / _patch.PATCH_ELFS).exists(), reason="needs make patch-elfs")
@pytest.mark.skipif(not (REPO / "internal_flash_backup_mario.bin").exists(), reason="needs the stock mario backups")
def test_patch_mario(tmp_path, capsys):
    from gnwmanager.gnw_patch.patches import cli

    _patch.unpack_elfs(tmp_path / "patch_elfs")
    cli.main(patch_command([f"--backup-dir={REPO}", "--device=mario"], tmp_path).argv)
    assert (tmp_path / "internal_flash_patched.bin").stat().st_size == 0x20000
    assert (tmp_path / "external_flash_patched.bin").stat().st_size
