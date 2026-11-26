"""Threaded simulation: an OS-scheduler thread dispatches work to an MMU thread.

The two threads hand control back and forth through queues (strict alternation), so the
run is race-free and deterministic for a given seed. Time is simulated in ticks instead
of time.sleep(), so a run finishes instantly.
"""
import queue
import random
import threading
from collections import deque

from .memory import PAGE_FAULT, TLB_HIT, MemoryManager
from .exceptions import SegmentationFault
from .scheduler import Scheduler
from .stats import Stats

_KIND_TEXT = {TLB_HIT: "TLB hit   ", "PAGE_HIT": "Page hit  ", PAGE_FAULT: "PAGE FAULT"}


class Simulator:
    def __init__(self, config, requests, log=print, show_memory=False, collect_trace=False):
        self.cfg = config
        self.log = log or (lambda *a, **k: None)
        self.show_memory = show_memory
        self.trace = [] if collect_trace else None
        self.rng = random.Random(config.seed)
        self.mm = MemoryManager(config, self.rng)
        self.scheduler = Scheduler(config.scheduler, config.quantum, self.rng)
        self.stats = Stats()
        self.clock = 0
        self.requests = {}
        for r in requests:
            if r.pid not in self.requests:
                self.requests[r.pid] = deque()
                self.mm.create_process(r.pid)
                self.scheduler.add(r.pid)
                self.stats.register(r.pid)
            self.requests[r.pid].append((r.rw, r.vaddr))
        self._cmd_q = queue.Queue()
        self._resp_q = queue.Queue()
        self._error = None

    # ---- public ------------------------------------------------------------
    def run(self):
        mmu = threading.Thread(target=self._mmu_loop, name="MMU", daemon=True)
        sched = threading.Thread(target=self._scheduler_loop, name="OS-Scheduler", daemon=True)
        mmu.start()
        sched.start()
        sched.join()
        mmu.join()
        if self._error:
            raise self._error
        self.stats.total_time = self.clock
        return self.stats

    # ---- OS scheduler thread -----------------------------------------------
    def _scheduler_loop(self):
        sched = self.scheduler
        try:
            while True:
                sched.wake_ready(self.clock)
                pid = sched.pick()
                if pid is None:
                    nxt = sched.next_wake_time()
                    if nxt is None:
                        break                              # nothing ready, nothing blocked
                    self.stats.idle_time += nxt - self.clock
                    self.clock = nxt                       # CPU idles until a disk read ends
                    continue
                self._cmd_q.put((pid, sched.quantum, self.clock))
                kind, payload = self._resp_q.get()
                if kind == "error":
                    raise payload
                status, cpu, io = payload
                self.clock += cpu
                if status == "ready":
                    sched.add(pid)
                elif status == "blocked":
                    sched.block(pid, self.clock + io)
                    self.log("    pid %d blocked for %d ticks (disk I/O). Blocked queue: %s"
                             % (pid, io, sched.blocked_pids()))
                else:                                      # done / killed
                    self.stats.finish_times[pid] = self.clock + io
        except BaseException as exc:                       # noqa: BLE001 - re-raised in run()
            self._error = exc
        finally:
            self._cmd_q.put(None)                          # tell the MMU thread to stop

    # ---- MMU thread --------------------------------------------------------
    def _mmu_loop(self):
        while True:
            cmd = self._cmd_q.get()
            if cmd is None:
                return
            try:
                self._resp_q.put(("ok", self._serve(*cmd)))
            except BaseException as exc:                   # noqa: BLE001
                self._resp_q.put(("error", exc))
                return

    def _serve(self, pid, quantum, now):
        """Run up to `quantum` requests of `pid`. Returns (status, cpu_ticks, io_ticks)."""
        cfg, pending = self.cfg, self.requests[pid]
        status, cpu, io, done = "ready", 0, 0, 0
        while pending and done < quantum:
            rw, vaddr = pending.popleft()
            done += 1
            try:
                res = self.mm.access(pid, rw, vaddr)
            except SegmentationFault as exc:
                self.stats.per_pid[pid].segfaults += 1
                self.log("[t=%8d] %s -- terminating pid %d" % (now + cpu, exc, pid))
                pending.clear()
                status = "killed"
                break
            self.stats.record(res)
            if self.trace is not None:
                self.trace.append(res)
            self._log_access(now + cpu, res)
            cpu += res.cpu_cost
            if res.io_time:
                io = res.io_time
                status = "blocked"
                break
        if not pending and status != "killed":
            status = "done"
        if status in ("done", "killed"):
            freed = self.mm.terminate_process(pid)
            self.log("    pid %d exited; freed %d frame(s)" % (pid, freed))
        return status, cpu, io

    def _log_access(self, t, r):
        cfg = self.cfg
        line = "[t=%8d] pid %-3d %s vaddr=0x%0*X page=%-4d %s " % (
            t, r.pid, r.rw, cfg.vaddr_hex_width, r.vaddr, r.page, _KIND_TEXT[r.kind])
        if r.kind == PAGE_FAULT:
            if r.victim:
                line += "| evicted pid %d page %d%s " % (
                    r.victim[0], r.victim[1], " (dirty, written back)" if r.writeback else "")
            line += "| loaded in frame %d " % r.frame
        line += "| paddr=0x%0*X" % (cfg.paddr_hex_width, r.paddr)
        self.log(line)
        if self.show_memory:
            cells = ["-" if f is None else "%d:%d" % f for f in self.mm.snapshot()]
            self.log("    Main Memory (pid:page): | " + " | ".join(cells) + " |")
