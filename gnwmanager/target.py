from collections import namedtuple
from time import sleep, time
from types import MethodType

from pyocd.core.target import Target

from gnwmanager.exceptions import DataError
from gnwmanager.status import flashapp_status_enum_to_str

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
        contexts[i]["decompressed_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["expected_sha256"] = last_variable = Variable(last_variable.address + last_variable.size, 32)
        contexts[i]["expected_sha256_decompressed"] = last_variable = Variable(
            last_variable.address + last_variable.size, 32
        )

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
        else:
            raise TypeError
        return self.read32(addr)

    def write_int(self, key, val):
        if isinstance(key, str):
            addr = _comm[key].address
        elif isinstance(key, int):
            addr = key
        else:
            raise TypeError

        self.write32(addr, val)

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
