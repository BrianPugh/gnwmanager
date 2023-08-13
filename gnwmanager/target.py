from collections import namedtuple
from time import sleep, time
from types import MethodType

from pyocd.core.target import Target

from gnwmanager.exceptions import DataError
from gnwmanager.status import flashapp_status_enum_to_str
from gnwmanager.utils import compress_lzma, sha256
from gnwmanager.validation import validate_extflash_offset

Variable = namedtuple("Variable", ["address", "size"])

_comm = {
    "framebuffer": Variable(0x2400_0000, 320 * 240 * 2),
    "flashapp_comm": Variable(0x2402_5800, 0xC4000),
}
contexts = [{} for i in range(2)]


def _populate_comm():
    # Communication Variables; put in a function to prevent variable leakage.
    _comm["flashapp_state"] = last_variable = Variable(_comm["flashapp_comm"].address, 4)
    _comm["program_status"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["utc_timestamp"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["program_chunk_idx"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["program_chunk_count"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    _comm["active_context_index"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    for i in range(2):
        struct_start = _comm["flashapp_comm"].address + ((i + 1) * 4096)
        contexts[i]["ready"] = last_variable = Variable(struct_start, 4)
        contexts[i]["size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["address"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["erase"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["erase_bytes"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["compressed_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["expected_sha256"] = last_variable = Variable(last_variable.address + last_variable.size, 32)

        # Don't ever directly use this, just here for alignment purposes
        contexts[i]["__buffer_ptr"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    struct_start = _comm["flashapp_comm"].address + (3 * 4096)
    _comm["active_context"] = last_variable = Variable(struct_start, 4096)

    for i in range(2):
        contexts[i]["buffer"] = last_variable = Variable(last_variable.address + last_variable.size, 256 << 10)


_populate_comm()


def mixin_object(obj, cls):
    for name, method in cls.__dict__.items():
        if callable(method):
            setattr(obj, name, MethodType(method, obj))


class GnWTargetMixin(Target):
    def read_int(self, key) -> int:
        if isinstance(key, str):
            addr = _comm[key].address
        elif isinstance(key, int):
            addr = key
        elif isinstance(key, Variable):
            addr = key.address
        else:
            raise TypeError
        return self.read32(addr)

    def write_int(self, key, val):
        if isinstance(key, str):
            addr = _comm[key].address
        elif isinstance(key, int):
            addr = key
        elif isinstance(key, Variable):
            addr = key.address
        else:
            raise TypeError

        self.write32(addr, val)

    def write_mem(self, key, val):
        if isinstance(key, str):
            addr = _comm[key].address
        elif isinstance(key, int):
            addr = key
        elif isinstance(key, Variable):
            addr = key.address
        else:
            raise TypeError

        self.write_memory_block8(addr, val)

    def wait_for_idle(self, timeout=10):
        """Block until the on-device status is IDLE."""
        time()
        t_deadline = time() + timeout
        error_mask = 0xFFFF_0000

        while True:
            status_enum = self.read_int("program_status")
            status_str = flashapp_status_enum_to_str.get(status_enum, "UNKNOWN")
            if status_str == "IDLE":
                break
            elif (status_enum & error_mask) == 0xBAD0_0000:
                raise DataError(status_str)
            if time() > t_deadline:
                raise TimeoutError
            sleep(0.05)

    def wait_for_all_contexts_complete(self, timeout=10):
        time()
        t_deadline = time() + timeout
        for context in contexts:
            while self.read_int(context["ready"]):
                if time() > t_deadline:
                    raise TimeoutError
                sleep(0.05)
        self.wait_for_idle(timeout=t_deadline - time())

    def get_context(self, timeout=10):
        time()
        t_deadline = time() + timeout
        while True:
            for context in contexts:
                if not self.read_int(context["ready"]):
                    return context
                if time() > t_deadline:
                    raise TimeoutError
            sleep(0.05)

    def _init_context_counter(self):
        if not hasattr(self, "context_counter"):
            self.context_counter = 1

    def write_ext(
        self,
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
        offset: int
            Offset into extflash to write.
        size: int
            Number of bytes to write.
        erase: bool
            Erases flash prior to write.
            Defaults to ``True``.
        """
        self._init_context_counter()
        validate_extflash_offset(offset)
        if not data:
            return
        if len(data) > (256 << 10):
            raise ValueError("Too large of data for a single write.")

        context = self.get_context()

        if blocking:
            self.wait_for_idle()
            self.halt()

        self.write_int(context["address"], offset)
        self.write_int(context["size"], len(data))

        if erase:
            self.write_int(context["erase"], 1)  # Perform an erase at `program_address`
            self.write_int(context["erase_bytes"], len(data))

        digest = sha256(data)
        if compress:
            data = compress_lzma(data)
            self.write_int(context["compressed_size"], len(data))

        self.write_mem(context["expected_sha256"], digest)
        self.write_mem(context["buffer"], data)

        self.write_int(context["ready"], self.context_counter)
        self.context_counter += 1

        if blocking:
            self.resume()
            self.wait_for_all_contexts_complete()
