import hashlib
import lzma


def sha256(data):
    return hashlib.sha256(data).digest()


EMPTY_HASH_DIGEST = sha256(b"")


def compress_lzma(data):
    compressed_data = lzma.compress(
        data,
        format=lzma.FORMAT_ALONE,
        filters=[
            {
                "id": lzma.FILTER_LZMA1,
                "preset": 6,
                "dict_size": 16 * 1024,
            }
        ],
    )

    return compressed_data[13:]
