"""Number / address helpers (fixed and generalised version of the old utils.py)."""


def is_power_of_two(n):
    return n > 0 and (n & (n - 1)) == 0


def inttohex(int_, bits=16):
    """Integer -> upper-case, zero-padded hex string (two's complement for negatives)."""
    width = (bits + 3) // 4
    return format(int_ % (1 << bits), "0{}X".format(width))


def inttobin(int_, bits=16):
    """Integer -> zero-padded binary string of exactly `bits` digits."""
    return format(int_ % (1 << bits), "0{}b".format(bits))


def hextobin(hex_, bits=16):
    return inttobin(int(hex_, 16), bits)


def bintohex(bin_, bits=16):
    return inttohex(int(bin_, 2), bits)


def parse_address(text):
    """Parse a hexadecimal address such as '04A0' or '0x04A0'."""
    try:
        value = int(text.strip(), 16)
    except ValueError:
        raise ValueError("invalid hexadecimal address: %r" % text) from None
    if value < 0:
        raise ValueError("address must not be negative: %r" % text)
    return value


def parse_size(text):
    """Parse '8192', '8K', '2M' ... into a number of bytes."""
    text = str(text).strip().upper()
    mult = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30}
    try:
        if text and text[-1] in mult:
            return int(text[:-1]) * mult[text[-1]]
        return int(text)
    except ValueError:
        raise ValueError("invalid size: %r" % text) from None


def split_address(vaddr, offset_bits):
    """Return (page_number, offset)."""
    return vaddr >> offset_bits, vaddr & ((1 << offset_bits) - 1)


def join_address(frame, offset, offset_bits):
    return (frame << offset_bits) | offset
