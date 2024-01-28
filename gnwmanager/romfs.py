"""RomFS.

=====
Goals
=====
1. File contents must be contiguous and be able to be mmap'd.
2. Files can be added/removed incrementally (rare event).
3. Must be able to defrag on-device.
4. Generally not concerned for wear-leveling, but defragging should be respectfully efficient.

=============
Specification
=============
* RomFS consists of a partition, and a table pointing to locations in the partition.
    * This table may be stored in another filesystem; e.g. LittleFS.
    * This table may also be compressed; e.g. Tamp
* Entries can be sorted in any order. Here they will be sorted in alphabetical order for on-device performance.
* Like SPIFFS, folders don't really exist, they're just part of a name.
* All data is stored little-endian.

------
Header
------
The following header is at the very beginning of the file.

+------+--------+----------------------------------------------------------------------------------+
| Size | Dtype  | Description                                                                      |
+======+========+==================================================================================+
|    1 |  uint8 | RomFS Version; if versions differ, then data content is incompatible.            |
+------+--------+----------------------------------------------------------------------------------+
|    3 | uint24 | Number of entries.                                                               |
+------+--------+----------------------------------------------------------------------------------+
|    4 | uint32 | Offset into external flash of RomFS partiion.                                    |
+------+--------+----------------------------------------------------------------------------------+
|    4 | uint32 | Size of RomFS partition.                                                         |
+------+--------+----------------------------------------------------------------------------------+


-----
Entry
-----
After the header, the rest of the file is a giant array of alphabetically-sorted pointers to files.
This is so displaying the retro-go menu is efficient (at the cost of defragging being more
expensive, this is done computer-side, so it doesn't really matter).

+------+--------+----------------------------------------------------------------------------------+
| Size | Dtype  | Description                                                                      |
+======+========+==================================================================================+
|    4 | uint32 | Offset into RomFS partition to start of file. Must be 4-byte aligned.            |
+------+--------+----------------------------------------------------------------------------------+
|    4 | uint32 | Size of file. The on-disk size is size rounded-up to nearest 4-bytes.            |
+------+--------+----------------------------------------------------------------------------------+
|    4 | uint32 | First 4 bytes (32-bits) of data's sha256 hash packed as a uint32.                |
+------+--------+----------------------------------------------------------------------------------+
|    * |   char | NULL-terminated string representing filepath. This is string is right-padded     |
|      |        | zeros to the nearest 4-byte boundary.                                            |
+------+--------+----------------------------------------------------------------------------------+

The file's abbreviated hash can be used to determine if data contents need to be updated.
The chance of a hash collision (falsely assuming a file's data hasn't changed) is
``1 / 4,294,967,296``, which is deemed an acceptable risk.

Under this schema, the smallest possible entry is 16 bytes.

==========
Defragging
==========
Defragging should be relatively rare, but when it needs to be performed, it should be able to be done
completely on-device with minimal data transfer over the debug probe.
"""

import struct
from collections import deque
from contextlib import suppress
from typing import List, Tuple, Union

from attrs import evolve, field, frozen

from gnwmanager.utils import sha256

FREE = ""
EMPTY_HASH = b"\x00" * 4


class InsufficientSpaceError(Exception):
    """Not enough space on disk."""


class FragmentationError(Exception):
    """A defragmentation needs to be performed to get enough free space."""


def _round_up_4(value: int) -> int:
    return (int(value) + 3) // 4**4


def _pad_4(data: bytes) -> bytes:
    padded_length = _round_up_4(len(data))
    if len(data) == padded_length:
        return data
    return data + b"\x00" * (padded_length - len(data))


class Header:
    VERSION = 0x01

    def __init__(self, n_entries, offset, size):
        self.n_entries = n_entries
        self.offset = offset
        self.size = size

    def __len__(self):
        # Size of serialized entry.
        return 12

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0):
        header_n_entries, offset, size = struct.unpack_from("<III", data, offset)

        header = header_n_entries & 0xFF
        assert header == Header.VERSION
        n_entries = header_n_entries >> 8

        return cls(n_entries=n_entries, offset=offset, size=size)

    def to_bytes(self):
        version_n_entries = (self.n_entries << 8) | Header.VERSION
        return struct.pack("<III", version_n_entries, self.offset, self.size)

    def __repr__(self):
        return f"{type(self).__name__}(n_entires={self.n_entries}, offset=0x{self.offset:08X}, size=0x{self.size:08X})"


@frozen
class Entry:
    name: str
    offset: int
    size: int
    hash: bytes = field()

    @hash.validator  # pyright: ignore[reportGeneralTypeIssues]
    def _check_hash_length(self, attribute, value):
        assert len(value) == 4

    def __len__(self):
        # Size of serialized entry.
        # 1 for the NULL-terminator
        return 4 + 4 + 4 + _round_up_4(len(self.name) + 1)

    @classmethod
    def from_bytes(cls, data, offset=0):
        section_offset, size, hash = struct.unpack_from("<III", data, offset)
        offset += 12

        # Read the NULL-terminated string for name
        start_idx = offset
        while offset < len(data) and data[offset] != 0:
            offset += 1
        name = data[start_idx:offset].decode("utf-8")
        offset += 1  # Skip the NULL byte

        return cls(name=name, offset=section_offset, size=size, hash=hash)

    def to_bytes(self):
        # Encode the name with a NULL terminator & pad it to multiple of 4
        name_encoded = _pad_4(self.name.encode("utf-8") + b"\x00")
        return struct.pack("<III", self.offset, self.size, self.hash) + name_encoded

    def __repr__(self):
        return f"{type(self).__name__}(name={self.name}, offset=0x{self.offset:08X}), size=0x{self.size:08x}, hash={self.hash.hex()}"


@frozen
class MoveCommand:
    src: int
    dst: int
    size: int

    def to_bytes(self):
        return struct.pack("<III", self.src, self.dst, self.size)


class SubsetSumOptimizationError(Exception):
    """SubsetSum was unable to discover a solution."""


def subset_sum(
    numbers: Tuple[int, ...],
    target: int,
    limit: int,
    partial: Tuple[int, ...] = (),
    partial_indices: Tuple[int, ...] = (),
) -> List[int]:
    """Find the subset-sum using dynamic programming with lru_cache."""
    diff = target - sum(partial)
    for i in range(len(numbers) - 1, -1, -1):
        n = numbers[i]
        if n < diff and len(partial) < limit:
            try:
                return subset_sum(numbers[:i], target, limit, partial + (n,), partial_indices + (i,))
            except SubsetSumOptimizationError:
                pass
        elif n == diff:
            return list(partial_indices + (i,))

    raise SubsetSumOptimizationError("No combination found that sums to the target value.")


class RomFS:
    def __init__(self, header: Header, entries: List[Entry]):
        self.header = header
        self.entries = entries

    @classmethod
    def from_descriptor(cls, data: bytes):
        offset = 0
        entries = []

        header = Header.from_bytes(data)
        offset += len(header)

        while offset < len(data):
            entry = Entry.from_bytes(data, offset)
            offset += len(entry)
            entries.append(entry)

        return cls(header, entries)

    def to_bytes(self, key=lambda x: x.name) -> bytes:
        """Serialize the RomFS Table.

        Returns
        -------
        bytes
            Descriptor data.
        """
        self.entries.sort(key=key)
        return self.header.to_bytes() + b"".join(e.to_bytes() for e in self.entries)

    def _walk_free(self, min_size=0):
        self.entries.sort(key=lambda x: x.offset)

        offset = 0
        for entry in self.entries:
            diff = entry.offset - offset
            if diff > min_size:
                yield Entry(FREE, offset=offset, size=diff, hash=EMPTY_HASH)
            offset = entry.offset + entry.size

        diff = self.header.size - offset
        if diff > min_size:
            yield Entry(FREE, offset=offset, size=diff, hash=EMPTY_HASH)

    @property
    def free(self) -> int:
        """Total number of free bytes."""
        return sum(x.size for x in self._walk_free())

    def remove(self, obj: Union[str, Entry]) -> Entry:
        """Remove an entry by name or Entry object.

        Raises
        ------
        FileNotFoundError
            If entry cannot be found.

        Returns
        -------
        Entry
            Removed entry object.
        """
        self.entries.sort(key=lambda x: x.offset)
        if isinstance(obj, Entry):
            try:
                index = self.entries.index(obj)
            except ValueError:
                raise FileNotFoundError from None
        else:
            # Find the entry
            for index, entry in enumerate(self.entries):  # noqa: B007
                if entry.name == obj:
                    obj = entry
                    break
            else:
                raise FileNotFoundError
        del self.entries[index]
        return obj

    def _best_fit(self, size) -> Entry:
        """Find the smallest FREE entry that is ``>=size``."""
        self.entries.sort(key=lambda x: x.offset)
        # Perform "best-fit" allocation.
        best_entry = None
        for entry in self._walk_free(size):
            if best_entry is None or entry.size < best_entry.size:
                best_entry = entry
                if entry.size == size:
                    break
        if best_entry is None:
            raise InsufficientSpaceError
        return best_entry

    def add_entry(self, name, size, hash) -> Entry:
        """Add an entry."""
        if size > self.free:
            raise InsufficientSpaceError
        try:
            free_entry = self._best_fit(size)
        except InsufficientSpaceError as e:
            raise FragmentationError from e
        self.entries.append(Entry(name, offset=free_entry.offset, size=size, hash=hash))
        return free_entry

    def add_data(self, name, data) -> Entry:
        return self.add_entry(name, len(data), sha256(data)[:4])

    def defrag(self, limit=8) -> List[MoveCommand]:
        """Generate an minimal defragment command-list.

        Parameters
        ----------
        limit: int
            Maximize number of entries to consider when attempting
            to solve subset-sum problem.

        Updates ``self.entries``.
        """
        self.entries.sort(key=lambda x: x.offset)

        move_cmds = []
        defragged_entries = []
        entries = deque(self.entries)
        offset = 0

        while entries:
            entry = entries.popleft()

            if free_size := entry.offset - offset:
                # Try and fill up the freespace with entries near-the-end.
                # This is to minimize the number of blocks moved when defragging.
                with suppress(SubsetSumOptimizationError):
                    indices = subset_sum(tuple(x.size for x in entries), free_size, limit)
                    indices.sort(reverse=True)
                    for index in indices:
                        move_cmds.append(MoveCommand(entries[index].offset, offset, entries[index].size))
                        offset += entries[index].size
                        del entries[index]

            defragged_entry = evolve(entry, offset=offset)
            if entry.offset != defragged_entry.offset:
                move_cmds.append(MoveCommand(entry.offset, defragged_entry.offset, entry.size))
            defragged_entries.append(defragged_entry)
            offset += defragged_entry.size
        self.entries[:] = defragged_entries
        return move_cmds

    def __repr__(self):
        return "\n".join([repr(self.header), "[", *("    " + repr(x) for x in self.entries), "]"])
