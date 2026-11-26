"""OS process scheduler with ready and blocked (waiting for disk) queues."""
import heapq
import itertools
import sys
from collections import deque

SCHEDULER_POLICIES = ("rr", "fifo", "random")


class Scheduler:
    def __init__(self, policy, quantum, rng):
        self.policy = policy
        # FIFO (FCFS) runs a process until it finishes or blocks on a page fault.
        self.quantum = sys.maxsize if policy == "fifo" else quantum
        self.rng = rng
        self.ready = deque()
        self._blocked = []
        self._seq = itertools.count()

    def add(self, pid):
        self.ready.append(pid)

    def block(self, pid, wake_time):
        heapq.heappush(self._blocked, (wake_time, next(self._seq), pid))

    def wake_ready(self, now):
        while self._blocked and self._blocked[0][0] <= now:
            self.ready.append(heapq.heappop(self._blocked)[2])

    def next_wake_time(self):
        return self._blocked[0][0] if self._blocked else None

    def blocked_pids(self):
        return [pid for _, _, pid in sorted(self._blocked)]

    def pick(self):
        if not self.ready:
            return None
        if self.policy == "random":
            self.ready.rotate(-self.rng.randrange(len(self.ready)))
        return self.ready.popleft()
