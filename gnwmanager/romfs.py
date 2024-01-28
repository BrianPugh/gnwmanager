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

Note: in this python implementation, we have "FREE" dummy entries indicating free-space.
"FREE" entries are not included in the final serialized RomFS Table.

==========
Defragging
==========
Defragging should be relatively rare, but when it needs to be performed, it should be able to be done
completely on-device with minimal data transfer over the debug probe.
"""

import struct
from collections import deque
from typing import List, Optional, Tuple, Union

from attrs import define, evolve, field, frozen

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
        # Size of header in bytes
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
        # 1 for the NULL-terminator
        return 4 + 4 + 4 + _round_up_4(len(self.name) + 1)

    @classmethod
    def from_bytes(cls, data, offset=0):
        offset, size, hash = struct.unpack_from("<III", data, offset)
        offset += 12

        # Read the NULL-terminated string for name
        start_idx = offset
        while offset < len(data) and data[offset] != 0:
            offset += 1
        name = data[start_idx:offset].decode("utf-8")
        offset += 1  # Skip the NULL byte

        return cls(name=name, offset=offset, size=size, hash=hash)

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


class RomFS:
    def __init__(self, header: Header, entries: List[Entry]):
        self.header = header
        self.entries = entries
        self._populate_free_entries()

    def _populate_free_entries(self):
        # Insert "FREE" dummy entries
        self.entries.sort(key=lambda x: x.offset)
        all_entries = []
        offset = 0
        for entry in self.entries:
            if diff := entry.offset - offset:
                all_entries.append(Entry(FREE, offset, diff, EMPTY_HASH))
            all_entries.append(entry)
            offset = entry.offset + entry.size

        if remaining_free_size := self.header.size - offset:
            all_entries.append(Entry(FREE, offset, remaining_free_size, EMPTY_HASH))
            offset += remaining_free_size

        self.entries[:] = all_entries

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

    def to_bytes(self) -> bytes:
        """Serialize the RomFS Table.

        Returns
        -------
        bytes
            Descriptor data.
        """
        self.entries.sort(key=lambda x: x.name)
        return self.header.to_bytes() + b"".join(e.to_bytes() for e in self.entries if e.name != FREE)

    def _walk_free(self, min_size=0):
        for entry in self.entries:
            if entry.name == FREE and entry.size >= min_size:
                yield entry

    def _walk_alloc(self):
        for entry in self.entries:
            if entry.name != FREE:
                yield entry

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
            index = self.entries.index(obj)
        else:
            # Find the entry
            for index, entry in enumerate(self._walk_alloc()):  # noqa: B007
                if entry.name == obj:
                    obj = entry
                    break
            else:
                raise FileNotFoundError

        offset = obj.offset
        size = obj.size

        if index < (len(self.entries) - 1) and self.entries[index + 1].name == FREE:
            next_entry = self.entries[index + 1]
            size += next_entry.size
            del self.entries[index + 1]

        del self.entries[index]

        if index > 0 and self.entries[index - 1].name == FREE:
            prev_entry = self.entries[index - 1]
            size += prev_entry.size
            offset = prev_entry.offset
            del self.entries[index - 1]

        free_entry = Entry(FREE, offset, size, EMPTY_HASH)
        self.entries.append(free_entry)

        return free_entry

    def _best_fit(self, size) -> Tuple[int, Entry]:
        """Find the smallest FREE entry that is ``>=size``."""
        self.entries.sort(key=lambda x: x.offset)
        # Perform "best-fit" allocation.
        best_index, best_entry = -1, None
        for i, entry in enumerate(self._walk_free(size)):
            if best_entry is None or entry.size < best_entry.size:
                best_index, best_entry = i, entry
        if best_entry is None:
            raise InsufficientSpaceError
        return best_index, best_entry

    def add(self, name, size, hash) -> Entry:
        """Add an entry."""
        if size > self.free:
            raise InsufficientSpaceError

        try:
            index, free_entry = self._best_fit(size)
        except InsufficientSpaceError as e:
            raise FragmentationError from e

        del self.entries[index]

        self.entries.append(
            Entry(
                name,
                offset=free_entry.offset,
                size=size,
                hash=hash,
            )
        )

        if free_size := free_entry.size - size:
            self.entries.append(
                Entry(
                    FREE,
                    offset=free_entry.offset + size,
                    size=free_size,
                    hash=EMPTY_HASH,
                )
            )

        return free_entry

    def defragment(self) -> List[MoveCommand]:
        """Generate an easy-to-execute defragment command-list.

        A "Good Enough" algorithm:

            1. Iterate over entries sorted by offset.
            2. If a FREE segment is reached:
                a. Iterate over entries in reversed order.
                b. If a file of the exact same size is found, move it.
                c. Otherwise, simply shift down the next entry.

        This algorithm could easily be performed on-device.
        It's just much easier to implement/test here.

        Updates ``self.entries``.
        """
        if not any(x.name == FREE for x in self.entries):
            raise ValueError("Cannot defrag; there are no free entries.")

        self.entries.sort(key=lambda x: x.offset)

        move_cmds = []
        defragged_entries = []
        entries = deque(self.entries)
        offset = 0
        current_free = 0

        while entries:
            entry = entries.popleft()
            if entry.name == FREE:
                current_free += entry.size

                # Search for a potential perfect match to populate this FREE entry.
                # Could potentially result in significantly reduced move-set.
                # only perfect matches *could* result in less moves.
                for i, src_entry in enumerate(reversed(entries)):
                    if src_entry.name == FREE:
                        continue
                    if src_entry.size != current_free:
                        continue

                    cmd = MoveCommand(src_entry.offset, offset, src_entry.size)
                    move_cmds.append(cmd)

                    entries.append(src_entry)
                    del entries[i]

                    offset += entry.size
                    current_free -= src_entry.size

                    break
            else:
                new_entry = evolve(entry, offset=offset)
                defragged_entries.append(new_entry)

                if entry.offset != new_entry.offset:
                    cmd = MoveCommand(entry.offset, new_entry.offset, entry.size)
                    move_cmds.append(cmd)

                offset += entry.size

        if current_free:
            defragged_entries.append(Entry(FREE, offset, current_free, EMPTY_HASH))
            offset += current_free

        self.entries[:] = defragged_entries
        return move_cmds

    def __repr__(self):
        return "\n".join([repr(self.header), "[", *("    " + repr(x) for x in self.entries), "]"])
