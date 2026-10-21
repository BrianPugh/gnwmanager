from pathlib import Path

import pytest
from cyclopts import UnknownOptionError

from gnwmanager.cli import _patch
from gnwmanager.cli._patch import PatchError, patch_command
from gnwmanager.cli.main import app

REPO = Path(__file__).resolve().parents[1]


def test_patch_argv_defaults(tmp_path):
    work = tmp_path / "work"
    argv = patch_command(["mario", f"--backup-dir={tmp_path}", "--sd-bootloader"], work).argv
    assert argv[0] == "--device=mario"
    assert "--sd-bootloader" in argv
    assert f"--prebuilt={work / 'patch_elfs'}" in argv
    assert f"--int-output={work / 'internal_flash_patched.bin'}" in argv
    assert f"--ext-output={work / 'external_flash_patched.bin'}" in argv
    assert f"--dump-dir={work / 'debug'}" in argv


def test_patch_argv_no_model(tmp_path):
    with pytest.raises(PatchError, match="No model given"):
        patch_command(["--sd-bootloader"], tmp_path)


def test_patch_argv_keeps_given(tmp_path):
    given = ["--device=amalgam", "--elf=x.elf", "--patch=x.bin", "--int-output=a.bin", "--dump-dir=d"]
    assert patch_command(given, tmp_path).argv == [*given, f"--ext-output={tmp_path / 'external_flash_patched.bin'}"]


def _parse(argv):
    """The command line ``flash-patch argv`` hands ``patch_command()``."""
    command, bound, ignored = app.parse_args(["flash-patch", *argv])
    assert "backend_factory" in ignored
    device = next(d for d, c in _patch.COMMANDS.items() if c is command)
    return _patch._patcher_argv(device, bound.args, bound.kwargs)


def test_cli_argv():
    argv = _parse(["zelda", "--no-la", "--loz2", "a.nes", "--relocate-stock", "0x08120000"])
    assert argv == ["zelda", "--relocate-stock=0x08120000", "--no-la", "--loz2=a.nes"]


def test_cli_argv_list_option():
    argv = _parse(["mario", "--smb1-graphics", "a.ips", "b.ips", "--no-smb2"])
    assert argv == ["mario", "--smb1-graphics", "a.ips", "b.ips", "--no-smb2"]


def test_cli_argv_legacy(tmp_path):
    internal, external = _backups(tmp_path, "mario")
    argv = _parse(["mario", str(internal), str(external), "--bootloader", "--bootloader-tag", "v1.0.3"])
    cmd = patch_command(argv, tmp_path / "work")
    assert cmd.argv[:2] == ["--device=mario", "--sd-bootloader"]
    assert cmd.bootloader_tag == "v1.0.3"


def test_cli_model_command():
    assert _parse(["zelda", "--no-la"]) == ["zelda", "--no-la"]
    assert _parse(["amalgam", "--sd-bootloader"]) == ["amalgam", "--sd-bootloader"]


@pytest.mark.parametrize(
    "argv", [["mario", "--no-such-option"], ["zelda", "--no-smb2"], ["mario", "--no-la"], ["mario", "--device=zelda"]]
)
def test_cli_unknown_option(argv):
    with pytest.raises(UnknownOptionError):
        app.parse_args(["flash-patch", *argv], exit_on_error=False)


def test_cli_help_lists_commands(capsys):
    app(["flash-patch", "--help"], exit_on_error=False)
    out = capsys.readouterr().out
    for model in _patch.DEVICES:
        assert f"{model} " in out
    assert "─ Patch ─" not in out


def test_cli_help_amalgam(capsys):
    app(["flash-patch", "amalgam", "--help"], exit_on_error=False)
    out = capsys.readouterr().out
    for name in ("--sd-bootloader", "--bootloader-tag", "--no-smb2", "--no-la", "--int-output", "Zelda only"):
        assert name in out
    for name in (*_patch.HIDDEN_OPTIONS, "--device", "INTERNAL"):
        assert f"{name} " not in out


def test_cli_help_model(capsys):
    app(["flash-patch", "zelda", "--help"], exit_on_error=False)
    out = capsys.readouterr().out
    assert "--no-la" in out and "96x32" in out
    for name in ("--no-smb2", "--device", "Zelda only", "96x48"):
        assert name not in out


def _backups(tmp_path, model):
    internal, external = tmp_path / "int.bin", tmp_path / "ext.bin"
    internal.write_bytes(model.encode())
    external.write_bytes(b"external")
    return internal, external


def test_legacy_form(tmp_path):
    """``flash-patch MODEL INTERNAL EXTERNAL [OPTIONS]``, as gnwmanager had it."""
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
