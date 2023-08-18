from collections import namedtuple
from math import ceil
from time import sleep, time
from types import MethodType
from typing import List, Literal

from pyocd.core.target import Target

from gnwmanager.exceptions import DataError
from gnwmanager.status import flashapp_status_enum_to_str
from gnwmanager.utils import EMPTY_HASH_DIGEST, compress_lzma, sha256
from gnwmanager.validation import validate_extflash_offset, validate_intflash_offset

Variable = namedtuple("Variable", ["address", "size"])

actions = {
    "ERASE_AND_FLASH": 0,
    "HASH": 1,
}


_comm = {
    "framebuffer": Variable(0x2400_0000, 320 * 240 * 2),
    "flashapp_comm": Variable(0x2402_5800, 0xC4000),
}
contexts = [{} for i in range(2)]


def _populate_comm():
    # Communication Variables; put in a function to prevent variable leakage.
    _comm["status"] = last_variable = Variable(_comm["flashapp_comm"].address, 4)
    _comm["status_override"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["utc_timestamp"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["progress"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["flash_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["min_erase_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    for i in range(2):
        struct_start = _comm["flashapp_comm"].address + ((i + 1) * 4096)

        contexts[i]["return_buffer_ptr"] = last_variable = Variable(struct_start, 4)

        contexts[i]["size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["offset"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["erase"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["erase_bytes"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["compressed_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["expected_sha256"] = last_variable = Variable(last_variable.address + last_variable.size, 32)
        contexts[i]["bank"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["action"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["response_ready"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

        contexts[i]["ready"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    struct_start = _comm["flashapp_comm"].address + (3 * 4096)
    _comm["active_context"] = last_variable = Variable(struct_start, 4096)

    for i in range(2):
        contexts[i]["buffer"] = last_variable = Variable(last_variable.address + last_variable.size, 256 << 10)


_populate_comm()


def _round_up(value, mod) -> int:
    return int(ceil(value / mod) * mod)


def _chunk_bytes(data: bytes, chunk_size: int) -> List[bytes]:
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


def mixin_object(obj, cls):
    for name, method in cls.__dict__.items():
        if callable(method):
            setattr(obj, name, MethodType(method, obj))


def _key_to_address(key) -> int:
    if isinstance(key, str):
        addr = _comm[key].address
    elif isinstance(key, int):
        addr = key
    elif isinstance(key, Variable):
        addr = key.address
    else:
        raise TypeError
    return addr


class GnWTargetMixin(Target):
    def read_int(self, key) -> int:
        addr = _key_to_address(key)
        return self.read32(addr)

    def write_int(self, key, val):
        addr = _key_to_address(key)
        self.write32(addr, val)

    def read_mem(self, key, size=None):
        if isinstance(key, str):
            if size is not None:
                raise ValueError
            addr, size = _comm[key].address, _comm[key].size
        elif isinstance(key, int):
            if size is None:
                raise ValueError
            addr = key
        elif isinstance(key, Variable):
            if size is not None:
                raise ValueError
            addr, size = key.address, key.size
        else:
            raise TypeError

        return bytes(self.read_memory_block8(addr, size))

    def write_mem(self, key, val):
        addr = _key_to_address(key)
        self.write_memory_block8(addr, val)

    def wait_for_idle(self, timeout=20):
        """Block until the on-device status is IDLE."""
        time()
        t_deadline = time() + timeout
        error_mask = 0xFFFF_0000

        while True:
            status_enum = self.read_int("status")
            status_str = flashapp_status_enum_to_str.get(status_enum, "UNKNOWN")
            if status_str == "IDLE":
                break
            elif (status_enum & error_mask) == 0xBAD0_0000:
                raise DataError(status_str)
            if time() > t_deadline:
                raise TimeoutError
            sleep(0.05)

    def wait_for_all_contexts_complete(self, timeout=20):
        time()
        t_deadline = time() + timeout
        for context in contexts:
            while self.read_int(context["ready"]):
                if time() > t_deadline:
                    raise TimeoutError
                sleep(0.05)
        self.wait_for_idle(timeout=t_deadline - time())

    def get_context(self, timeout=20):
        if not hasattr(self, "context_counter"):
            self.context_counter = 1

        time()
        t_deadline = time() + timeout
        while True:
            for context in contexts:
                if not self.read_int(context["ready"]):
                    return context
                if time() > t_deadline:
                    raise TimeoutError
            sleep(0.05)

    def wait_for_context_response(self, context, timeout=20):
        time()
        t_deadline = time() + timeout
        while not self.read_int(context["response_ready"]):
            if time() > t_deadline:
                raise TimeoutError

            sleep(0.05)

    def read_hashes(self, offset, size) -> List[bytes]:
        validate_extflash_offset(offset)
        n_chunks = int(ceil(size / (256 << 10)))

        context = self.get_context()

        self.write_int(context["response_ready"], 0)
        self.write_int(context["action"], actions["HASH"])
        self.write_int(context["offset"], offset)
        self.write_int(context["size"], size)
        self.write_int(context["ready"], self.context_counter)
        self.context_counter += 1

        self.wait_for_context_response(context)

        hashes = self.read_mem(context["buffer"], n_chunks * 32)

        # Free the context
        self.write_int(context["ready"], 0)

        return _chunk_bytes(hashes, 32)

    def prog(
        self,
        bank: Literal[0, 1, 2],
        offset: int,
        data: bytes,
        erase: bool = True,
        blocking: bool = True,
        compress: bool = True,
    ) -> None:
        """Write data to extflash.

        Limited to RAM constraints (i.e. <256KB writes).

        ``program_chunk_idx`` must externally be set.

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
        """
        if bank not in (0, 1, 2):
            raise ValueError

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

        context = self.get_context()

        if blocking:
            self.wait_for_idle()
            self.halt()

        self.write_int(context["action"], actions["ERASE_AND_FLASH"])
        self.write_int(context["offset"], offset)
        self.write_int(context["size"], len(data))
        self.write_int(context["bank"], bank)

        if erase:
            self.write_int(context["erase"], 1)  # Perform an erase at `offset`
            self.write_int(context["erase_bytes"], len(data))
        else:
            self.write_int(context["erase"], 0)

        self.write_mem(context["expected_sha256"], sha256(data))

        if compress:
            self.write_int(context["compressed_size"], len(compressed_data))
            self.write_mem(context["buffer"], compressed_data)
        else:
            self.write_int(context["compressed_size"], 0)
            self.write_mem(context["buffer"], data)

        self.write_int(context["ready"], self.context_counter)
        self.context_counter += 1

        if blocking:
            self.resume()
            self.wait_for_all_contexts_complete()
            self.wait_for_idle()  # Wait for the early-return context to complete.

    def erase_ext(self, offset: int, size: int, whole_chip: bool = False, **kwargs) -> None:
        """Erase a range of data on extflash.

        On-device flashapp will round up to nearest minimum erase size.
        ``program_chunk_idx`` must externally be set.

        Parameters
        ----------
        offset: int
            Offset into extflash to erase.
        size: int
            Number of bytes to erase.
        whole_chip: bool
            If ``True``, ``size`` is ignored and the entire chip is erased.
            Defaults to ``False``.
        """
        validate_extflash_offset(offset)

        if size <= 0 and not whole_chip:
            raise ValueError("Size must be >0; 0 erases the entire chip.")

        context = self.get_context()

        self.write_int(context["action"], actions["ERASE_AND_FLASH"])
        self.write_int(context["offset"], offset)
        self.write_int(context["erase"], 1)  # Perform an erase at `offset`
        self.write_int(context["size"], 0)
        self.write_int(context["bank"], 0)

        if whole_chip:
            self.write_int(context["erase_bytes"].address, 0)  # Note: a 0 value erases the whole chip
        else:
            self.write_int(context["erase_bytes"].address, size)

        self.write_mem(context["expected_sha256"], EMPTY_HASH_DIGEST)

        self.write_int(context["ready"], self.context_counter)
        self.context_counter += 1

        self.wait_for_all_contexts_complete(**kwargs)
        self.wait_for_idle()

    def erase_int(self, bank: int, offset: int, size: int, **kwargs) -> None:
        validate_intflash_offset(offset)

        if size <= 0:
            raise ValueError

        size = _round_up(size, 8192)

        if bank not in (1, 2):
            raise ValueError

        context = self.get_context()

        self.write_int(context["action"], actions["ERASE_AND_FLASH"])
        self.write_int(context["offset"], offset)
        self.write_int(context["erase"], 1)  # Perform an erase at `offset`
        self.write_int(context["size"], 0)
        self.write_int(context["bank"], bank)

        self.write_mem(context["expected_sha256"], EMPTY_HASH_DIGEST)

        self.write_int(context["ready"], self.context_counter)
        self.context_counter += 1

        self.wait_for_all_contexts_complete(**kwargs)
        self.wait_for_idle()
