import importlib.resources
import logging
from collections import namedtuple
from copy import deepcopy
from itertools import count
from math import ceil
from pathlib import PurePosixPath
from time import sleep, time
from typing import Dict, List, Literal, NamedTuple, Optional, Union

from tqdm import tqdm

from gnwmanager.exceptions import DataError
from gnwmanager.ocdbackend import OCDBackend
from gnwmanager.status import flashapp_status_enum_to_str
from gnwmanager.time import timestamp_now
from gnwmanager.utils import EMPTY_HASH_DIGEST, chunk_bytes, compress_lzma, pad_bytes, sha256
from gnwmanager.validation import validate_extflash_offset, validate_intflash_offset

log = logging.getLogger(__name__)


class Variable(NamedTuple):
    address: int
    size: int


ERROR_MASK = 0xFFFF_0000

# Status strings that indicate the bytes the host wrote to device RAM didn't
# survive the debug-probe transfer intact. The data on device flash/SD is fine;
# the corruption is in the in-flight buffer.
#
# BAD_HASH_RAM_COMPRESSED is handled in-protocol via chunk-level retry (the
# device parks in HASH_RETRY_WAIT and the host re-transmits to the same context
# buffer). BAD_HASH_RAM (decompressed-data check failure) falls through to the
# operation-level retry wrapper, which reloads firmware and starts over.
_TRANSFER_CORRUPTION_PREFIXES = ("BAD_HASH_RAM_COMPRESSED", "BAD_HASH_RAM")

# Operation-level: full reload + restart on persistent transfer corruption.
_MAX_TRANSFER_RETRIES = 2

# Chunk-level: re-transmit a single context buffer without reloading firmware.
_MAX_CHUNK_RETRIES = 3


def _is_transfer_corruption_error(exc: "DataError") -> bool:
    if not exc.args or not isinstance(exc.args[0], str):
        return False
    return exc.args[0].startswith(_TRANSFER_CORRUPTION_PREFIXES)


actions: dict[str, int] = {
    "ERASE_AND_FLASH": 0,
    "HASH": 1,
    "WRITE_FILE_TO_SD": 2,
    "LIST_SD_DIR": 3,
    "DELETE_FILE_FROM_SD": 4,
    "READ_FILE_FROM_SD": 5,
}

_comm: dict[str, Variable] = {
    "framebuffer": Variable(0x2400_0000, 320 * 240 * 2),
    "flashapp_comm": Variable(0x2402_5800, 0xC4000),
}
_contexts: list[dict[str, Variable]] = [{} for _ in range(2)]


def _populate_comm():
    # Communication Variables; put in a function to prevent variable leakage.
    _comm["status"] = last_variable = Variable(_comm["flashapp_comm"].address, 4)
    _comm["status_override"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["utc_timestamp"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["progress"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["flash_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["min_erase_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["upload_in_progress"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["download_in_progress"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["expected_hash"] = last_variable = Variable(last_variable.address + last_variable.size, 32)
    _comm["actual_hash"] = last_variable = Variable(last_variable.address + last_variable.size, 32)

    # Per-chunk retry handshake. When the device detects BAD_HASH_RAM_COMPRESSED
    # it parks in HASH_RETRY_WAIT, publishes the index of the corrupted context
    # buffer, and waits for the host to re-transmit the data and bump
    # retry_request. The device echoes retry_request into retry_ack once it
    # has re-loaded working_context from the (rewritten) source context.
    _comm["failed_context_idx"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["retry_request"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["retry_ack"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    for i in range(2):
        struct_start = _comm["flashapp_comm"].address + ((i + 1) * 1024)

        _contexts[i]["return_buffer_ptr"] = last_variable = Variable(struct_start, 4)

        _contexts[i]["size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["offset"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["erase"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["erase_bytes"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["compressed_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["expected_sha256"] = last_variable = Variable(last_variable.address + last_variable.size, 32)
        _contexts[i]["bank"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["action"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["response_ready"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["dest_path"] = last_variable = Variable(last_variable.address + last_variable.size, 256)
        _contexts[i]["block"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["total_blocks"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        _contexts[i]["compressed_sha256"] = last_variable = Variable(last_variable.address + last_variable.size, 32)

        _contexts[i]["ready"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    struct_start = _comm["flashapp_comm"].address + (3 * 1024)
    _comm["active_context"] = last_variable = Variable(struct_start, 1024)

    for i in range(2):
        _contexts[i]["buffer"] = last_variable = Variable(last_variable.address + last_variable.size, 256 << 10)


_populate_comm()


def _round_up(value, mod) -> int:
    return int(ceil(value / mod) * mod)


def _chunk_bytes(data: bytes, chunk_size: int) -> list[bytes]:
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


def _key_to_address(key: Union[int, str, Variable]) -> int:
    if isinstance(key, str):
        addr = _comm[key].address
    elif isinstance(key, int):
        addr = key
    elif isinstance(key, Variable):
        addr = key.address
    else:
        raise TypeError
    return addr


class GnW:
    """Abstraction pertaining to specific GnW hardware and the on-devicegnwmanager app."""

    def __init__(self, backend: OCDBackend):
        self.backend = backend
        self.contexts = deepcopy(_contexts)
        self.context_counter = 1
        self._external_flash_size = 0
        self._external_flash_block_size = 0
        self._gnwmanager_started = False
        self.default_filesystem_offset = 0
        # Per-context retry state for the BAD_HASH_RAM_COMPRESSED chunk-retry
        # handshake. Each slot holds either None (nothing recoverable in flight)
        # or a dict with the buffer bytes + hashes the host wrote, plus an
        # `attempts` counter. Populated by program()/sd_write_file_chunk()
        # whenever they push compressed data to a context.
        self._in_flight_retry: list[Optional[dict]] = [None, None]

    @property
    def external_flash_size(self) -> int:
        log.debug("Querying external flash size.")
        if self._external_flash_size == 0:
            self._external_flash_size = self.read_uint32("flash_size")
        return self._external_flash_size

    @property
    def external_flash_block_size(self) -> int:
        log.debug("Querying external flash min erase size.")
        if self._external_flash_block_size == 0:
            self._external_flash_block_size = self.read_uint32("min_erase_size")
        return self._external_flash_block_size

    def read_uint32(self, key: Union[int, str, Variable]) -> int:
        return self.backend.read_uint32(_key_to_address(key))

    def write_uint32(self, key: Union[int, str, Variable], val: int):
        return self.backend.write_uint32(_key_to_address(key), val)

    def read_memory(self, key: Union[int, str, Variable], size: Optional[int] = None):
        if isinstance(key, str):
            if size is not None:
                raise ValueError
            addr, size = _comm[key].address, _comm[key].size
        elif isinstance(key, int):
            if size is None:
                raise ValueError
            addr = key
        elif isinstance(key, Variable):
            if size is None:
                size = key.size
            addr = key.address
        else:
            raise TypeError

        self.write_uint32("download_in_progress", 1)
        data = self.backend.read_memory(addr, size)
        self.write_uint32("download_in_progress", 0)

        return data

    def write_memory(self, key: Union[int, str, Variable], val: bytes):
        addr = _key_to_address(key)
        self.backend.write_memory(addr, val)

    def write_str(self, key: Union[int, str, Variable], val: str):
        byte_val = val.encode("utf-8") + b"\x00"
        self.write_memory(key, byte_val)

    def _drain_pending_writes(self, context):
        # ADIv5 posted-write drain: any AP read flushes pending writes through the
        # debug adapter. Without this, the running CPU can see `ready` flip before
        # earlier bursts (large buffers, long paths) have landed (manifests as
        # BAD_HASH_RAM_COMPRESSED for sdpush/flash). Cheap: one extra word read.
        self.read_uint32(context["buffer"].address)

    def _record_in_flight_compressed(
        self, context, *, buffer_data: bytes, compressed_sha256: bytes, expected_sha256: bytes
    ):
        """Stash what was written to this context so the chunk-retry handshake can resend it.

        Driven from `_get_status` on BAD_HASH_RAM_COMPRESSED.
        """
        idx = _contexts.index(context)
        self._in_flight_retry[idx] = {
            "buffer_data": buffer_data,
            "compressed_sha256": compressed_sha256,
            "expected_sha256": expected_sha256,
            "attempts": 0,
        }

    def _try_chunk_retry(self) -> bool:
        """Re-transmit a corrupted context buffer via the HASH_RETRY_WAIT handshake.

        Returns True if a retry was issued (caller should re-poll status),
        False if no retry is possible (caller surfaces the error). Exhausted
        attempts and a missing in-flight record (e.g. an uncompressed transfer
        — but those don't trip BAD_HASH_RAM_COMPRESSED) both fall back to
        operation-level retry.
        """
        failed_idx = self.read_uint32("failed_context_idx")
        if failed_idx not in (0, 1):
            return False
        saved = self._in_flight_retry[failed_idx]
        if saved is None or saved["attempts"] >= _MAX_CHUNK_RETRIES:
            return False

        context = _contexts[failed_idx]
        saved["attempts"] += 1
        log.warning(
            f"BAD_HASH_RAM_COMPRESSED on context {failed_idx}; "
            f"re-transmitting buffer (attempt {saved['attempts']}/{_MAX_CHUNK_RETRIES})."
        )

        self.write_uint32("upload_in_progress", 1)
        self.write_memory(context["buffer"], saved["buffer_data"])
        self.write_memory(context["compressed_sha256"], saved["compressed_sha256"])
        self.write_memory(context["expected_sha256"], saved["expected_sha256"])
        self._drain_pending_writes(context)

        new_request = self.read_uint32("retry_request") + 1
        self.write_uint32("retry_request", new_request)
        self.write_uint32("upload_in_progress", 0)

        # Wait for the device to consume retry_request — at that point it has
        # already re-loaded working_context and transitioned back to DECOMPRESSING.
        deadline = time() + 10
        while self.read_uint32("retry_ack") != new_request:
            if time() > deadline:
                log.warning(f"Retry ack timeout on context {failed_idx}.")
                return False
            sleep(0.01)
        return True

    def _with_transfer_retry(self, op_name: str, fn, *args, **kwargs):
        """Run ``fn`` and retry on transfer-corruption errors (BAD_HASH_RAM*).

        The failure surfaces in a later status poll rather than at the call
        that queued the bad chunk, so we can't isolate the failing chunk —
        retry reloads firmware (resetting the context state machine) and
        re-runs the whole operation. Re-flashing is idempotent: the firmware
        short-circuits chunks whose hash already matches.
        """
        for attempt in range(_MAX_TRANSFER_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except DataError as e:
                if attempt == _MAX_TRANSFER_RETRIES or not _is_transfer_corruption_error(e):
                    raise
                first_line = e.args[0].splitlines()[0]
                log.warning(
                    f"{op_name}: {first_line} on attempt {attempt + 1}/{_MAX_TRANSFER_RETRIES + 1}; "
                    "reloading firmware and retrying."
                )
                self.start_gnwmanager(force=True)

    def wait_for_idle(self, timeout: float = 120):
        """Block until the on-device status is IDLE.

        `timeout` is a *no-progress* budget, not a total wall-clock budget:
        the deadline resets every time the device's status string changes.
        A slow operation that keeps making forward progress is tolerated
        indefinitely; only a stall with no status change for `timeout`
        seconds raises.

        Parameters
        ----------
        timeout: float
            Maximum seconds to wait without observing any status change.

        Raises
        ------
        TimeoutError
            If the on-device status does not change for `timeout` seconds.
        """
        log.debug("Waiting for device to idle.")
        t_start = time()
        t_progress = t_start
        last_status = None

        for i in count():
            status_str = self._get_status()
            if status_str == "IDLE":
                break
            if status_str != last_status:
                t_progress = time()
                last_status = status_str
            if i % 10 == 0:
                log.debug(f"waiting for device to IDLE; current status: {status_str}")
            if time() - t_progress > timeout:
                raise TimeoutError(f"wait_for_idle: no status progress for {timeout:.1f}s (status={status_str})")
            sleep(0.1)
        log.debug(f"Waited {time() - t_start:.3f}s for device idle.")

    def wait_for_all_contexts_complete(self, timeout=120):
        """Wait for every in-flight context slot to be acked by the device.

        `timeout` is a *no-progress* budget per context, not a total
        wall-clock budget: while waiting on a given context the deadline
        resets every time its `ready` field or the device `status` changes.
        Slow but advancing operations (e.g. a long FAT sync on a slow SD
        card) are tolerated indefinitely; only a stall with no observable
        state change for `timeout` seconds raises.

        Parameters
        ----------
        timeout: float
            Maximum seconds to wait without observing any change in the
            current context's `ready` field or the device status. The same
            budget is also passed to the trailing `wait_for_idle` call.

        Raises
        ------
        TimeoutError
            If no progress is observed on a context for `timeout` seconds.
        """
        log.debug("Waiting for all contexts to complete.")
        t_start = time()
        for i, context in enumerate(_contexts):
            t_progress = time()
            last_ready = None
            last_status = None
            while True:
                cur_ready = self.read_uint32(context["ready"])
                if not cur_ready:
                    break
                cur_status = self._get_status()
                if cur_ready != last_ready or cur_status != last_status:
                    t_progress = time()
                    last_ready = cur_ready
                    last_status = cur_status
                if time() - t_progress > timeout:
                    raise TimeoutError(
                        f"wait_for_all_contexts_complete: no progress for {timeout:.1f}s "
                        f"on context {i} (ready=0x{cur_ready:x}, status={cur_status})"
                    )
                sleep(0.1)
            log.debug(f"Context {i} complete.")
        log.debug(f"Waited {time() - t_start:.3f}s for all contexts to complete.")
        self._get_status()
        self.wait_for_idle(timeout=timeout)

    def wait_for_context_response(self, context, timeout=120):
        """Wait for the device to write a response into `context`.

        `timeout` is a *no-progress* budget, not a total wall-clock budget:
        the deadline resets every time the device status string changes
        (the status is polled each iteration, which also surfaces device
        errors via `_get_status`). A slow but advancing query is tolerated
        indefinitely; only a stall with no status change for `timeout`
        seconds raises.

        Parameters
        ----------
        context: dict
            The context slot previously handed work; its `response_ready`
            flag is polled.
        timeout: float
            Maximum seconds to wait without observing any status change.

        Raises
        ------
        TimeoutError
            If the device status does not change for `timeout` seconds
            before `response_ready` becomes non-zero.
        """
        context_index = _contexts.index(context)
        log.debug(f"Waiting on context {context_index} for response.")
        t_start = time()
        t_progress = t_start
        last_status = None
        while not self.read_uint32(context["response_ready"]):
            cur_status = self._get_status()
            if cur_status != last_status:
                t_progress = time()
                last_status = cur_status
            if time() - t_progress > timeout:
                raise TimeoutError(
                    f"wait_for_context_response: no progress for {timeout:.1f}s "
                    f"on context {context_index} (status={cur_status})"
                )
            sleep(0.1)
        log.debug(f"Waited {time() - t_start:.3f}s for context {context_index} response.")

    def reset_context_counter(self):
        self.context_counter = 1
        # Any prior in-flight buffers are gone with the device's RAM; the
        # next program/sd_write_file_chunk will repopulate as needed.
        self._in_flight_retry = [None, None]
        log.debug(f"context_counter reset to {self.context_counter}.")

    def reset(self):
        log.debug("Performing device reset.")
        self.backend.reset()
        self.reset_context_counter()
        self._gnwmanager_started = False

    def reset_and_halt(self):
        log.debug("Performing device reset and halt.")
        self.backend.reset_and_halt()
        self.reset_context_counter()
        self._gnwmanager_started = False

    def _get_status(self, raise_on_error=True) -> str:
        while True:
            status_enum = self.read_uint32("status")
            status_str = flashapp_status_enum_to_str.get(status_enum, "UNKNOWN")
            if raise_on_error and (status_enum & ERROR_MASK) == 0xBAD0_0000:
                # In-protocol chunk retry: device parks in HASH_RETRY_WAIT and
                # we resend the corrupted buffer without reloading firmware.
                # Falls through to the DataError raise once retries are spent.
                if status_str == "BAD_HASH_RAM_COMPRESSED" and self._try_chunk_retry():
                    continue
                if status_str in ("BAD_HASH_RAM", "BAD_HASH_RAM_COMPRESSED", "BAD_HASH_FLASH"):
                    expected_hash = self.read_memory("expected_hash")
                    actual_hash = self.read_memory("actual_hash")
                    raise DataError(f"{status_str}:\nExpected: {expected_hash.hex()}\nActual: {actual_hash.hex()}")
                raise DataError(status_str)
            return status_str

    def get_context(self, timeout=120):
        """Return the next available context slot (first with `ready == 0`).

        `timeout` is a *no-progress* budget, not a total wall-clock budget:
        the deadline resets every time any slot's `ready` value or the
        device status changes. While the device keeps draining queued work
        the wait can extend indefinitely; only a stall with no observable
        state change for `timeout` seconds raises.

        Parameters
        ----------
        timeout: float
            Maximum seconds to wait without observing any change in either
            slot's `ready` field or the device status.

        Raises
        ------
        TimeoutError
            If no slot becomes available and no progress is observed for
            `timeout` seconds.
        """
        t_start = time()
        t_progress = t_start
        last_ready = None
        last_status = None
        while True:
            ready_states = []
            for i, context in enumerate(_contexts):
                ready = self.read_uint32(context["ready"])
                if not ready:
                    # Slot is free → its prior work succeeded; drop stale
                    # retry tracking so a future BAD_HASH_RAM_COMPRESSED on
                    # this slot can't pull data from a finished chunk.
                    self._in_flight_retry[i] = None
                    log.debug(f"Got context {i} in {time() - t_start:.3f}s.")
                    return context
                ready_states.append(ready)
            cur_ready = tuple(ready_states)
            cur_status = self._get_status()
            if cur_ready != last_ready or cur_status != last_status:
                t_progress = time()
                last_ready = cur_ready
                last_status = cur_status
            if time() - t_progress > timeout:
                log.debug(f"Timeout ({timeout}s no-progress) waiting for an available context.")
                raise TimeoutError(
                    f"get_context: no progress for {timeout:.1f}s "
                    f"(ready={[f'0x{r:x}' for r in ready_states]}, status={cur_status})"
                )
            sleep(0.1)

    def filesystem(self, offset: Optional[int] = None, **kwargs):
        from gnwmanager.filesystem import get_filesystem

        if offset is None:
            offset = self.default_filesystem_offset
            log.debug(f"Using GnW default offset {offset} for filesystem.")

        return get_filesystem(self, offset=offset, **kwargs)

    def read_hashes(self, offset, size) -> list[bytes]:
        """Blocking call to get the hashes of external flash chunks.

        All chunks are 256KB; the last chunk may be less.

        Parameters
        ----------
        offset: int
            Offset into external flash.
        size: int
            Number of bytes to hash.

        Returns
        -------
        List[bytes]
            List of 32-byte sha256 hashes.
        """
        validate_extflash_offset(offset)
        n_chunks = int(ceil(size / (256 << 10)))
        log.debug(f"Hashing {size} bytes starting at {offset} in {n_chunks}x 256KB chunks.")

        context = self.get_context()

        self.write_uint32(context["response_ready"], 0)
        self.write_uint32(context["action"], actions["HASH"])
        self.write_uint32(context["offset"], offset)
        self.write_uint32(context["size"], size)
        self.write_uint32(context["ready"], self.context_counter)
        self.context_counter += 1
        log.debug(f"context_counter incremented to {self.context_counter}.")

        self.wait_for_context_response(context)

        hashes = self.read_memory(context["buffer"], n_chunks * 32)

        # Free the context
        self.write_uint32(context["ready"], 0)

        return _chunk_bytes(hashes, 32)

    def program(
        self,
        bank: Literal[0, 1, 2],
        offset: int,
        data: bytes,
        erase: bool = True,
        blocking: bool = True,
        compress: bool = True,
    ) -> None:
        """Low-level write data to flash.

        Limited to RAM constraints (i.e. <256KB writes).

        ``program_chunk_idx`` must externally be set.

        Does NOT check destination for a hash match prior to flashing.

        Parameters
        ----------
        bank: int
            0 - External Flash
            1 - Internal Bank 1
            2 - Internal Bank 2
        offset: int
            Offset into extflash to write.
        size: int
            Number of bytes to write.
        erase: bool
            Erases flash prior to write.
            Defaults to ``True``.
        blocking: bool
            Wait for action to be complete.
        """
        log.debug(f"gnw.program: {bank=} {offset=} {len(data)=} {erase=} {blocking=} {compress=}")
        if bank not in (0, 1, 2):
            raise ValueError("Bank must be one of {0, 1, 2}.")

        if bank == 0:
            validate_extflash_offset(offset)
        else:
            validate_intflash_offset(offset)

        if not data:
            return
        if len(data) > (256 << 10):
            raise ValueError("Too large of data for a single write.")

        if compress:
            compressed_data = compress_lzma(data)
            # If we are unable to compress meaningfully, don't bother.
            if len(compressed_data) > (0.9 * len(data)):
                compress = False
        else:
            compressed_data = b""

        context = self.get_context()

        log.debug("setting upload_in_progress.")
        self.write_uint32("upload_in_progress", 1)

        self.write_uint32(context["action"], actions["ERASE_AND_FLASH"])
        self.write_uint32(context["offset"], offset)
        self.write_uint32(context["size"], len(data))
        self.write_uint32(context["bank"], bank)

        if erase:
            self.write_uint32(context["erase"], 1)  # Perform an erase at `offset`
            self.write_uint32(context["erase_bytes"], len(data))
        else:
            self.write_uint32(context["erase"], 0)

        data_hash = sha256(data)
        self.write_memory(context["expected_sha256"], data_hash)

        if compress:
            compressed_hash = sha256(compressed_data)
            self.write_uint32(context["compressed_size"], len(compressed_data))
            self.write_memory(context["buffer"], compressed_data)
            self.write_memory(context["compressed_sha256"], compressed_hash)
            self._record_in_flight_compressed(
                context,
                buffer_data=compressed_data,
                compressed_sha256=compressed_hash,
                expected_sha256=data_hash,
            )
        else:
            self.write_uint32(context["compressed_size"], 0)
            self.write_memory(context["buffer"], data)

        self._drain_pending_writes(context)

        log.debug(f"Activating PROGRAM: {data_hash.hex()}")
        self.write_uint32(context["ready"], self.context_counter)
        self.context_counter += 1
        log.debug(f"context_counter incremented to {self.context_counter}.")

        log.debug("clearing upload_in_progress.")
        self.write_uint32("upload_in_progress", 0)

        if blocking:
            self.wait_for_all_contexts_complete()

    def flash(
        self,
        bank: Literal[0, 1, 2],
        offset: int,
        data: bytes,
        progress: bool = False,
        desc: Optional[str] = None,
    ):
        """High level convenience function for flashing any-length data to any flash location."""
        op_name = f"flash bank={bank} offset=0x{offset:x}"
        if bank == 0:
            data = pad_bytes(data, self.external_flash_block_size)
            if len(data) > self.external_flash_size:
                raise ValueError("Data cannot fit into external flash.")

            self._with_transfer_retry(op_name, self._flash_ext, offset, data, progress=progress, desc=desc)
        elif bank in (1, 2):
            data = pad_bytes(data, 8192)
            if len(data) > (256 << 10):
                raise ValueError("Data cannot fit into internal flash.")

            self._with_transfer_retry(op_name, self.program, bank, offset, data)
        else:
            raise ValueError

    def erase(
        self,
        bank: Literal[0, 1, 2],
        offset: int,
        size: int,
        blocking: bool = True,
        whole_chip: bool = False,
        **kwargs,
    ) -> None:
        """Perform a flash erase.

        Parameters
        ----------
        bank: int
            0 - External Flash
            1 - Internal Bank 1
            2 - Internal Bank 2
        offset: int
            Offset into location to erase.
        size: int
            Number of bytes to erase.
            Will be rounded up to the nearest sector size, if necessary.
            Ignored if ``whole_chip=True``.
        blocking: bool
            Wait for action to be complete.
        whole_chip: bool
            If ``true``, perform a faster bulk erase and erase entire location.
            Set ``offset=0`` and ``size=0`` when using this option.
        """
        log.debug(f"gnw.erase: {bank=} {offset=} {size=} {blocking=} {whole_chip=}")
        # Input validation
        if size < 0:
            raise ValueError

        if whole_chip:
            if offset != 0:
                raise ValueError("Offset must be 0 if whole_chip=True.")
            if size != 0:
                raise ValueError("Size must be 0 if whole_chip=True.")
        else:
            if size == 0:
                raise ValueError("Size must be >0.")

        if bank not in (0, 1, 2):
            raise ValueError("Bank must be one of {0, 1, 2}.")

        if bank == 0:
            validate_extflash_offset(offset)
        elif bank in (1, 2):
            validate_intflash_offset(offset)
        else:
            raise NotImplementedError

        # Perform action
        context = self.get_context()

        self.write_uint32(context["action"], actions["ERASE_AND_FLASH"])
        self.write_uint32(context["offset"], offset)
        self.write_uint32(context["size"], 0)  # We are not programming any bytes
        self.write_uint32(context["erase"], 1)  # Perform an erase at `offset`
        self.write_uint32(context["erase_bytes"].address, size)  # 0 signals a whole-chip erase.
        self.write_uint32(context["bank"], bank)
        self.write_memory(context["expected_sha256"], EMPTY_HASH_DIGEST)

        self.write_uint32(context["ready"], self.context_counter)
        self.context_counter += 1
        log.debug(f"context_counter incremented to {self.context_counter}.")

        if blocking:
            self.wait_for_all_contexts_complete(**kwargs)

    def _flash_ext(
        self,
        offset: int,
        data: bytes,
        progress: bool = False,
        desc: Optional[str] = None,
    ):
        validate_extflash_offset(offset)

        device_hashes = self.read_hashes(offset, len(data))

        chunk_size = self.contexts[0]["buffer"].size  # Assumes all contexts have same size buffer
        chunks = chunk_bytes(data, chunk_size)

        Packet = namedtuple("Packet", ["addr", "data"])
        all_packets = [Packet(offset + i * chunk_size, chunk) for i, chunk in enumerate(chunks)]
        log.info(f"Data chunked into {len(all_packets)} packets.")

        # Remove packets where the hash already matches
        packets = [
            packet for packet, device_hash in zip(all_packets, device_hashes) if sha256(packet.data) != device_hash
        ]

        log.info(f"{len(packets)} packets need to be programmed.")
        for i, packet in enumerate(tqdm(packets, desc=desc) if progress else packets):
            log.info(f"Programming packet {i + 1}/{len(packets)}.")
            self.program(0, packet.addr, packet.data, blocking=False)
            self.write_uint32("progress", int(26 * (i + 1) / len(packets)))

        self.wait_for_all_contexts_complete()

    def _sd_write_file_chunk(
        self,
        path: str,
        block: int,
        total_blocks: int,
        data: bytes = b"",
        blocking: bool = True,
        compress: bool = True,
    ) -> None:
        """Low-level write data to fat filesystem.

        Limited to RAM constraints (i.e. <256KB writes).

        Parameters
        ----------
        path: str
            Path of file to write
        size: int
            Number of bytes to write.
        blocking: bool
            Wait for action to be complete.
        """
        log.debug(f"gnw._sd_write_file_chunk: {path=} {len(data)=} {blocking=} {compress=}")

        if not path:
            raise ValueError("Destination SD path cannot be empty.")

        if len(data) > (256 << 10):
            raise ValueError("Too large of data for a single write.")

        if compress:
            compressed_data = compress_lzma(data)
            # If we are unable to compress meaningfully, don't bother.
            if len(compressed_data) > (0.9 * len(data)):
                compress = False
        else:
            compressed_data = b""

        context = self.get_context()

        log.debug("setting upload_in_progress.")
        self.write_uint32("upload_in_progress", 1)

        self.write_uint32(context["action"], actions["WRITE_FILE_TO_SD"])
        self.write_str(context["dest_path"], path)
        self.write_uint32(context["size"], len(data))
        self.write_uint32(context["block"], block)
        self.write_uint32(context["total_blocks"], total_blocks)

        data_hash = sha256(data)
        self.write_memory(context["expected_sha256"], data_hash)

        if compress:
            compressed_hash = sha256(compressed_data)
            self.write_uint32(context["compressed_size"], len(compressed_data))
            self.write_memory(context["buffer"], compressed_data)
            self.write_memory(context["compressed_sha256"], compressed_hash)
            self._record_in_flight_compressed(
                context,
                buffer_data=compressed_data,
                compressed_sha256=compressed_hash,
                expected_sha256=data_hash,
            )
        else:
            self.write_uint32(context["compressed_size"], 0)
            self.write_memory(context["buffer"], data)

        self._drain_pending_writes(context)

        log.debug(f"Activating PROGRAM: {data_hash.hex()}")
        self.write_uint32(context["ready"], self.context_counter)
        self.context_counter += 1
        log.debug(f"context_counter incremented to {self.context_counter}.")

        log.debug("clearing upload_in_progress.")
        self.write_uint32("upload_in_progress", 0)

        if blocking:
            self.wait_for_all_contexts_complete()

    def sd_write_file(
        self,
        path: str,
        data: bytes,
        progress: bool = False,
    ):
        if path.endswith("/"):
            raise ValueError(f"path shall not be a folder {path}")
        if not path.startswith("/"):
            raise ValueError(f"path shall start with '/' {path}")
        self._with_transfer_retry(f"sdpush {path}", self._sd_write_file_impl, path, data, progress)

    def _sd_write_file_impl(self, path: str, data: bytes, progress: bool):
        chunk_size = self.contexts[0]["buffer"].size  # Assumes all contexts have same size buffer
        chunks = chunk_bytes(data, chunk_size)

        log.info(f"Data chunked into {len(chunks)} packets.")

        if len(chunks) == 0:
            log.info("Programming empty file.")
            self._sd_write_file_chunk(path, 0, 1, blocking=False)

        for i, packet in enumerate(tqdm(chunks, desc=PurePosixPath(path).name) if progress else chunks):
            log.info(f"Programming packet {i + 1}/{len(chunks)}.")
            self._sd_write_file_chunk(path, i, len(chunks), packet, blocking=False)
            self.write_uint32("progress", int(26 * (i + 1) / len(chunks)))

        self.wait_for_all_contexts_complete()

    def _sd_read_file_chunk(
        self,
        path: str,
        offset: int,
        max_bytes: int,
        *,
        blocking: bool = True,
    ) -> bytes:
        """Read up to ``max_bytes`` from ``path`` on the SD card starting at ``offset``."""
        if not path:
            raise ValueError("SD path cannot be empty.")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        if max_bytes < 0 or max_bytes > (256 << 10):
            raise ValueError("max_bytes must be in [0, 256 KiB].")
        if max_bytes == 0 and offset != 0:
            raise ValueError("max_bytes==0 (stat) requires offset==0.")

        context = self.get_context()
        self.write_uint32(context["response_ready"], 0)
        self.write_uint32(context["action"], actions["READ_FILE_FROM_SD"])
        self.write_str(context["dest_path"], path)
        self.write_uint32(context["offset"], offset)
        self.write_uint32(context["size"], max_bytes)
        self._drain_pending_writes(context)
        self.write_uint32(context["ready"], self.context_counter)
        self.context_counter += 1
        log.debug(f"context_counter incremented to {self.context_counter}.")

        self.wait_for_context_response(context)
        self._get_status()
        nbytes = self.read_uint32(context["size"])
        data = self.read_memory(context["buffer"], nbytes) if nbytes else b""
        self.write_uint32(context["ready"], 0)
        if blocking:
            self.wait_for_idle()
        return data

    def _sd_file_size(self, path: str) -> int:
        """Return the size in bytes of ``path`` on the SD card (FatFs ``f_size``)."""
        if not path.startswith("/"):
            raise ValueError(f"path shall start with '/' {path}")
        if path.endswith("/"):
            raise ValueError(f"path shall not be a directory: {path}")

        context = self.get_context()
        self.write_uint32(context["response_ready"], 0)
        self.write_uint32(context["action"], actions["READ_FILE_FROM_SD"])
        self.write_str(context["dest_path"], path)
        self.write_uint32(context["offset"], 0)
        self.write_uint32(context["size"], 0)
        self._drain_pending_writes(context)
        self.write_uint32(context["ready"], self.context_counter)
        self.context_counter += 1
        log.debug(f"context_counter incremented to {self.context_counter}.")

        self.wait_for_context_response(context)
        self._get_status()
        nbytes = self.read_uint32(context["size"])
        self.write_uint32(context["ready"], 0)
        self.wait_for_idle()
        return nbytes

    def sd_read_file(self, path: str, progress: bool = False) -> bytes:
        """Read an entire file from the SD card (chunks of up to 256 KiB)."""
        if path.endswith("/"):
            raise ValueError(f"path shall not be a directory: {path}")
        if not path.startswith("/"):
            raise ValueError(f"path shall start with '/' {path}")

        chunk_size = self.contexts[0]["buffer"].size
        file_size = self._sd_file_size(path)

        ranges: List[tuple[int, int]] = []
        o = 0
        while o < file_size:
            nb = min(chunk_size, file_size - o)
            ranges.append((o, nb))
            o += nb
        if file_size == 0:
            ranges = [(0, chunk_size)]

        log.info(f"Data fetched in {len(ranges)} packets.")
        out = bytearray()
        for i, (off, nb) in enumerate(tqdm(ranges, desc=PurePosixPath(path).name, disable=not progress)):
            log.info(f"Reading packet {i + 1}/{len(ranges)}.")
            chunk = self._sd_read_file_chunk(path, off, nb, blocking=False)
            out.extend(chunk)
            self.write_uint32("progress", int(26 * (i + 1) / len(ranges)))

        self.wait_for_all_contexts_complete()
        return bytes(out)

    def sd_unlink(self, path: str) -> None:
        """Remove a file from the SD card (FatFs ``f_unlink``)."""
        if not path.startswith("/"):
            raise ValueError(f"path shall start with '/' {path}")
        if path.endswith("/"):
            raise ValueError(f"path shall be a file, not a directory: {path}")

        context = self.get_context()
        self.write_uint32(context["response_ready"], 0)
        self.write_uint32(context["action"], actions["DELETE_FILE_FROM_SD"])
        self.write_str(context["dest_path"], path)
        self._drain_pending_writes(context)
        self.write_uint32(context["ready"], self.context_counter)
        self.context_counter += 1
        log.debug(f"context_counter incremented to {self.context_counter}.")

        self.wait_for_context_response(context)
        self._get_status()
        self.write_uint32(context["ready"], 0)
        self.wait_for_idle()

    def sd_list_dir(self, path: str) -> str:
        """Return a newline-separated listing of ``path`` on the SD card."""
        if not path.startswith("/"):
            raise ValueError(f"path shall start with '/' {path}")

        context = self.get_context()
        self.write_uint32(context["response_ready"], 0)
        self.write_uint32(context["action"], actions["LIST_SD_DIR"])
        self.write_str(context["dest_path"], path)
        self._drain_pending_writes(context)
        self.write_uint32(context["ready"], self.context_counter)
        self.context_counter += 1
        log.debug(f"context_counter incremented to {self.context_counter}.")

        self.wait_for_context_response(context)
        status_enum = self.read_uint32("status")
        nbytes = self.read_uint32(context["size"])
        data = self.read_memory(context["buffer"], nbytes) if nbytes else b""
        self.write_uint32(context["ready"], 0)
        self.wait_for_idle()
        if (status_enum & ERROR_MASK) == 0xBAD0_0000 and status_enum != 0xBAD0000C:
            self._get_status()
        if status_enum == 0xBAD0000C:
            log.warning("SD directory listing was truncated (output larger than 256 KiB).")
        return data.decode("utf-8", errors="replace")

    def start_gnwmanager(self, force=False, resume=True):
        if not force and self._gnwmanager_started:
            return

        self.reset_and_halt()

        firmware = (importlib.resources.files("gnwmanager") / "firmware.bin").read_bytes()
        log.debug(f"Loaded {len(firmware)} bytes of gnwmanager firmware.")

        log.debug("Loading gnwmanager firmware to device.")
        self.write_memory(0x240E_6800, firmware)  # See STM32H7B0VBTx_FLASH.ld

        log.debug("Setting memory and registers.")
        self.write_uint32("status", 0)  # To be 100% sure there's nothing residual in RAM.
        self.write_uint32("status_override", 0)  # To be 100% sure there's nothing residual in RAM.

        msp = int.from_bytes(firmware[:4], byteorder="little")
        pc = int.from_bytes(firmware[4:8], byteorder="little")
        self.backend.write_register("msp", msp)
        self.backend.write_register("pc", pc)

        log.debug("Resuming chip execution.")

        if resume:
            self.backend.resume()
            self.wait_for_idle()

            # Time has to be set **after** device is in an idle state
            log.debug("Setting device time.")
            self.write_uint32("utc_timestamp", timestamp_now())

        self._gnwmanager_started = True

    def is_locked(self) -> bool:
        """Returns ``True`` if the device is locked."""
        try:
            # See if reading from bank 1 is possible.
            self.read_uint32(0x0800_0000)
        except Exception:
            log.debug("device is locked.")
            return True
        log.debug("device is unlocked.")
        return False
