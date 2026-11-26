"""Custom exceptions (replaces vmmmisc.py)."""


class VMMError(Exception):
    """Base class of every error raised by this package."""


class ConfigError(VMMError):
    """Invalid simulator configuration."""


class RequestFormatError(VMMError):
    """A line of the request file could not be parsed."""


def _fmt(addr):
    return "0x%04X" % addr if isinstance(addr, int) else str(addr)


class AddressTranslationError(VMMError):
    """Virtual -> physical translation failed because the page is not resident."""

    def __init__(self, pid, addr):
        super().__init__(pid, addr)
        self.pid = pid
        self.addr = addr

    def __str__(self):
        return "Address translation failed. pid: %s, addr: %s" % (self.pid, _fmt(self.addr))


class FrameNotFoundError(VMMError):
    """The page of a process is not mapped to any frame."""

    def __init__(self, pid, page):
        super().__init__(pid, page)
        self.pid = pid
        self.page = page

    def __str__(self):
        return "Frame not found. pid: %s, page: %s" % (self.pid, self.page)


class SegmentationFault(VMMError):
    """The virtual address is outside the process' address space."""

    def __init__(self, pid, addr):
        super().__init__(pid, addr)
        self.pid = pid
        self.addr = addr

    def __str__(self):
        return "Segmentation fault. pid: %s, addr: %s" % (self.pid, _fmt(self.addr))


class SignalUser1:
    """Simulated SIGUSR1: carries (pid, page) from the MMU to the OS fault handler."""

    def __init__(self):
        self.pid = -1
        self.page = -1
        self._handler = None

    def connect(self, handler):
        self._handler = handler

    def set(self, pid, page):
        self.pid = pid
        self.page = page

    def send(self, handler=None):
        handler = handler or self._handler
        if handler is None:
            raise VMMError("no handler connected to SIGUSR1")
        return handler(self.pid, self.page)
