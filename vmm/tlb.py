"""Translation Lookaside Buffer (fully associative, LRU)."""
from collections import OrderedDict


class TLB:
    def __init__(self, size):
        self.size = size
        self._e = OrderedDict()

    @property
    def enabled(self):
        return self.size > 0

    def lookup(self, pid, page):
        key = (pid, page)
        frame = self._e.get(key)
        if frame is not None:
            self._e.move_to_end(key)
        return frame

    def insert(self, pid, page, frame):
        if not self.enabled:
            return
        key = (pid, page)
        self._e[key] = frame
        self._e.move_to_end(key)
        if len(self._e) > self.size:
            self._e.popitem(last=False)

    def invalidate(self, pid, page):
        self._e.pop((pid, page), None)

    def flush_pid(self, pid):
        for key in [k for k in self._e if k[0] == pid]:
            del self._e[key]

    def __len__(self):
        return len(self._e)
