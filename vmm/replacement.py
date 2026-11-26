"""Page replacement policies. All operations are O(1) except LFU's victim search."""
import random
from abc import ABC, abstractmethod
from collections import OrderedDict

from .exceptions import VMMError


class ReplacementPolicy(ABC):
    name = "base"

    def __init__(self, num_frames, rng=None):
        self.num_frames = num_frames
        self.rng = rng or random.Random()

    @abstractmethod
    def on_load(self, frame):
        """A page has just been placed in `frame`."""

    def on_access(self, frame):
        """The page in `frame` was referenced."""

    @abstractmethod
    def on_evict(self, frame):
        """`frame` was freed (evicted or its process exited)."""

    @abstractmethod
    def choose_victim(self):
        """Return the frame to evict (memory is full when this is called)."""


class FIFOPolicy(ReplacementPolicy):
    name = "fifo"

    def __init__(self, num_frames, rng=None):
        super().__init__(num_frames, rng)
        self._q = OrderedDict()

    def on_load(self, frame):
        self._q[frame] = None

    def on_evict(self, frame):
        self._q.pop(frame, None)

    def choose_victim(self):
        if not self._q:
            raise VMMError("no resident frame to evict")
        return next(iter(self._q))


class LRUPolicy(FIFOPolicy):
    name = "lru"

    def on_access(self, frame):
        if frame in self._q:
            self._q.move_to_end(frame)


class LFUPolicy(ReplacementPolicy):
    """Least frequently used; ties are broken by least recent use."""
    name = "lfu"

    def __init__(self, num_frames, rng=None):
        super().__init__(num_frames, rng)
        self._count = {}
        self._stamp = {}
        self._seq = 0

    def on_load(self, frame):
        self._count[frame] = 0
        self._seq += 1
        self._stamp[frame] = self._seq

    def on_access(self, frame):
        if frame in self._count:
            self._count[frame] += 1
            self._seq += 1
            self._stamp[frame] = self._seq

    def on_evict(self, frame):
        self._count.pop(frame, None)
        self._stamp.pop(frame, None)

    def choose_victim(self):
        if not self._count:
            raise VMMError("no resident frame to evict")
        return min(self._count, key=lambda f: (self._count[f], self._stamp[f]))


class ClockPolicy(ReplacementPolicy):
    """Second-chance (clock) algorithm."""
    name = "clock"

    def __init__(self, num_frames, rng=None):
        super().__init__(num_frames, rng)
        self._ref = [False] * num_frames
        self._res = [False] * num_frames
        self._n = 0
        self._hand = 0

    def on_load(self, frame):
        if not self._res[frame]:
            self._res[frame] = True
            self._n += 1
        self._ref[frame] = True

    def on_access(self, frame):
        self._ref[frame] = True

    def on_evict(self, frame):
        if self._res[frame]:
            self._res[frame] = False
            self._n -= 1
        self._ref[frame] = False

    def choose_victim(self):
        if self._n == 0:
            raise VMMError("no resident frame to evict")
        while True:
            f = self._hand
            self._hand = (f + 1) % self.num_frames
            if not self._res[f]:
                continue
            if self._ref[f]:
                self._ref[f] = False
            else:
                return f


class RandomPolicy(ReplacementPolicy):
    name = "random"

    def __init__(self, num_frames, rng=None):
        super().__init__(num_frames, rng)
        self._frames = []
        self._pos = {}

    def on_load(self, frame):
        if frame not in self._pos:
            self._pos[frame] = len(self._frames)
            self._frames.append(frame)

    def on_evict(self, frame):
        i = self._pos.pop(frame, None)
        if i is None:
            return
        last = self._frames.pop()
        if i < len(self._frames):
            self._frames[i] = last
            self._pos[last] = i

    def choose_victim(self):
        if not self._frames:
            raise VMMError("no resident frame to evict")
        return self.rng.choice(self._frames)


POLICIES = {p.name: p for p in (FIFOPolicy, LRUPolicy, LFUPolicy, ClockPolicy, RandomPolicy)}


def make_policy(name, num_frames, rng=None):
    try:
        return POLICIES[name](num_frames, rng)
    except KeyError:
        raise VMMError("unknown replacement policy %r (choose from %s)"
                       % (name, ", ".join(POLICIES))) from None
