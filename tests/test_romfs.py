from gnwmanager.romfs import RomFS, Header, Entry


def test_empty_fs():
    romfs = RomFS(Header(0, 0, 1 << 20), [])
    # TODO


def test_fs_add():
    pass
