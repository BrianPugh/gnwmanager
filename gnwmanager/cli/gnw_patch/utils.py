from math import ceil

import logging

log = logging.getLogger(__name__)


def printi(msg, *args):
    log.info(msg, *args)


def printe(msg, *args):
    log.error(msg, *args)


def printd(msg, *args):
    log.debug(msg, *args)


def round_down_word(val):
    return (val // 4) * 4


def round_up_word(val):
    return ceil(val / 4) * 4


def round_down_page(val):
    return (val // 4096) * 4096


def round_up_page(val):
    return ceil(val / 4096) * 4096


def seconds_to_frames(seconds):
    return int(round(60 * seconds))


def fds_crc(data, checksum=0x8000):
    """
    Do not include any existing checksum, not even the blank checksums 00 00 or FF FF.
    The formula will automatically count 2 0x00 bytes without the programmer adding them manually.
    Also, do not include the gap terminator (0x80) in the data.
    If you wish to do so, change sum to 0x0000.
    """
    size = len(data)
    for i in range(size + 2):
        if i < size:
            byte = data[i]
        else:
            byte = 0x00

        for bit_index in range(8):
            bit = (byte >> bit_index) & 0x1
            carry = checksum & 0x1
            checksum = (checksum >> 1) | (bit << 15)
            if carry:
                checksum ^= 0x8408
    return checksum.to_bytes(2, "little")
