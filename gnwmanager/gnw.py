import importlib.resources
import logging
from collections import namedtuple
from copy import deepcopy
from itertools import count
from math import ceil
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

actions: Dict[str, int] = {
    "ERASE_AND_FLASH": 0,
    "HASH": 1,
}

_comm: Dict[str, Variable] = {
    "framebuffer": Variable(0x2400_0000, 320 * 240 * 2),
    "flashapp_comm": Variable(0x2402_5800, 0xC4000),
}
_contexts: List[Dict[str, Variable]] = [{} for _ in range(2)]


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

        _contexts[i]["ready"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    struct_start = _comm["flashapp_comm"].address + (3 * 1024)
    _comm["active_context"] = last_variable = Variable(struct_start, 1024)

    for i in range(2):
        _contexts[i]["buffer"] = last_variable = Variable(last_variable.address + last_variable.size, 256 << 10)


_populate_comm()


def _round_up(value, mod) -> int:
    return int(ceil(value / mod) * mod)


def _chunk_bytes(data: bytes, chunk_size: int) -> List[bytes]:
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

    def wait_for_idle(self, timeout: float = 20):
        """Block until the on-device status is IDLE."""
        log.debug("Waiting for device to idle.")
        t_start = time()
        t_deadline = t_start + timeout

        for i in count():
            status_str = self._get_status()
            if status_str == "IDLE":
                break
            if i % 10 == 0:
                log.debug(f"waiting for device to IDLE; current status: {status_str}")
            if time() > t_deadline:
                raise TimeoutError("wait_for_idle")
            sleep(0.1)
        log.debug(f"Waited {time() - t_start:.3f}s for device idle.")

    def wait_for_all_contexts_complete(self, timeout=20):
        log.debug("Waiting for all contexts to complete.")
        t_start = time()
        t_deadline = t_start + timeout
        for i, context in enumerate(_contexts):
            while self.read_uint32(context["ready"]):
                if time() > t_deadline:
                    raise TimeoutError("wait_for_all_contexts_complete")
                sleep(0.1)
            log.debug(f"Context {i} complete.")
        log.debug(f"Waited {time() - t_start:.3f}s for all contexts to complete.")
        self.wait_for_idle(timeout=t_deadline - time())

    def wait_for_context_response(self, context, timeout=20):
        context_index = _contexts.index(context)
        log.debug(f"Waiting on context {context_index} for response.")
        t_start = time()
        t_deadline = t_start + timeout
        while not self.read_uint32(context["response_ready"]):
            if time() > t_deadline:
                raise TimeoutError("wait_for_context_response")
            sleep(0.1)
        log.debug(f"Waited {time() - t_start:.3f}s for context {context_index} response.")

    def reset_context_counter(self):
        self.context_counter = 1
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
        status_enum = self.read_uint32("status")
        status_str = flashapp_status_enum_to_str.get(status_enum, "UNKNOWN")
        if raise_on_error and (status_enum & ERROR_MASK) == 0xBAD0_0000:
            if status_str in ("BAD_HASH_RAM", "BAD_HASH_FLASH"):
                expected_hash = self.read_memory("expected_hash")
                actual_hash = self.read_memory("actual_hash")
                raise DataError(f"{status_str}:\nExpected: {expected_hash.hex()}\nActual: {actual_hash.hex()}")
            else:
                raise DataError(status_str)
        return status_str

    def get_context(self, timeout=20):
        t_start = time()
        t_deadline = t_start + timeout
        while True:
            for i, context in enumerate(_contexts):
                if not self.read_uint32(context["ready"]):
                    log.debug(f"Got context {i} in {time() - t_start:.3f}s.")
                    return context
                self._get_status()
                if time() > t_deadline:
                    log.debug(f"Timeout ({timeout}s) reached waiting to get an available context.")
                    raise TimeoutError
            sleep(0.1)

    def filesystem(self, offset: Optional[int] = None, **kwargs):
        from gnwmanager.filesystem import get_filesystem

        if offset is None:
            offset = self.default_filesystem_offset
            log.debug(f"Using GnW default offset {offset} for filesystem.")

        return get_filesystem(self, offset=offset, **kwargs)

    def read_hashes(self, offset, size) -> List[bytes]:
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
            self.write_uint32(context["compressed_size"], len(compressed_data))
            self.write_memory(context["buffer"], compressed_data)
        else:
            self.write_uint32(context["compressed_size"], 0)
            self.write_memory(context["buffer"], data)

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
    ):
        """High level convenience function for flashing any-length data to any flash location."""
        if bank == 0:
            data = pad_bytes(data, self.external_flash_block_size)
            if len(data) > self.external_flash_size:
                raise ValueError("Data cannot fit into external flash.")

            self._flash_ext(offset, data, progress=progress)
        elif bank in (1, 2):
            data = pad_bytes(data, 8192)
            if len(data) > (256 << 10):
                raise ValueError("Data cannot fit into internal flash.")

            self.program(bank, offset, data)
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
        for i, packet in enumerate(tqdm(packets) if progress else packets):
            log.info(f"Programming packet {i + 1}/{len(packets)}.")
            self.program(0, packet.addr, packet.data, blocking=False)
            self.write_uint32("progress", int(26 * (i + 1) / len(packets)))

        self.wait_for_all_contexts_complete()

    def start_gnwmanager(self, force=False, resume=True):
        if not force and self._gnwmanager_started:
            return

        self.reset_and_halt()

        # TODO: this is deprecated, but the replacement was introduced in python3.9.
        # Migrate to ``as_file`` once python3.8 hits EOL.
        with importlib.resources.path("gnwmanager", "firmware.bin") as f:
            firmware = f.read_bytes()
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
