import errno
import os
import stat
from pathlib import Path
from typing import Optional

import fuse
from littlefs.errors import LittleFSError

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app

fuse.fuse_python_api = (0, 2)


class LittleFSFuse(fuse.Fuse):
    def __init__(self, lfs, *args, **kwargs):
        """LFS filesystem should be mounted prior."""
        super().__init__(*args, **kwargs)
        self.lfs = lfs

    def getattr(self, path):
        st_mode = 0o755
        try:
            st = self.lfs.stat(path)
        except LittleFSError as e:
            if e.code == LittleFSError.Error.LFS_ERR_NOENT:
                return -errno.ENOENT
            else:
                raise

        if st.type == 1:  # file
            st_mode = 0o666 | stat.S_IFREG
            st_size = st.size
        elif st.type == 2:  # dir
            st_mode |= 0o755 | stat.S_IFDIR
            st_size = 4096
        else:
            raise NotImplementedError

        return fuse.Stat(st_mode=st_mode, st_size=st_size, st_nlink=2)

    def readdir(self, path, offset):
        for entry in [".", ".."] + self.lfs.listdir(path):
            yield fuse.Direntry(entry)

    def open(self, path, flags):
        # Map the POSIX flags to mode strings.
        modes = {os.O_RDONLY: "r", os.O_WRONLY: "w", os.O_RDWR: "r+"}
        mode = modes.get(flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR))

        # Handle append mode
        if flags & os.O_APPEND:
            mode = "a" if mode == "w" else "a+"

        try:
            self.lfs.open(path, mode)
        except LittleFSError as e:
            if e.code == LittleFSError.Error.LFS_ERR_NOENT:
                return -errno.ENOENT
            else:
                raise

    def read(self, path, size, offset):
        with self.lfs.open(path, "rb") as f:
            f.seek(offset)
            return f.read(size)

    def write(self, path, buf, offset):
        with self.lfs.open(path, "r+b") as f:
            f.seek(offset)
            return f.write(buf)

    def mkdir(self, path, mode):
        try:
            self.lfs.mkdir(path, mode)
        except LittleFSError as e:
            if e.code == LittleFSError.Error.LFS_ERR_NOENT:
                return -errno.ENOENT
            else:
                raise

    def unlink(self, path):
        try:
            self.lfs.remove(path)
        except LittleFSError as e:
            if e.code == LittleFSError.Error.LFS_ERR_NOENT:
                return -errno.ENOENT
            else:
                raise

    def rmdir(self, path):
        try:
            self.lfs.rmdir(path)
        except LittleFSError as e:
            if e.code == LittleFSError.Error.LFS_ERR_NOENT:
                return -errno.ENOENT
            else:
                raise


@app.command
def mount(
    mountpoint: Optional[Path] = None,
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """TODO."""
    if mountpoint is None:
        mountpoint = Path.home() / "gnw"
    gnw.start_gnwmanager()
    fs = gnw.filesystem(offset=offset)
    server = LittleFSFuse(fs, version="%prog " + fuse.__version__, dash_s_do="setsingle")
    server.fuse_args.mountpoint = str(mountpoint)  # pyright: ignore [reportGeneralTypeIssues]
    server.fuse_args.setmod("foreground")
    # server.fuse_args.add("debug")

    # Start the FUSE main loop
    print(f"Mounting filesystem to {str(mountpoint)}")
    server.main()
