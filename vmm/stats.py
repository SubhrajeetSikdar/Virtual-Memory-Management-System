"""Statistics collection and reporting."""
from collections import defaultdict
from dataclasses import dataclass, fields

from .memory import PAGE_FAULT, TLB_HIT


def _ratio(a, b):
    return a / b if b else 0.0


@dataclass
class Counters:
    accesses: int = 0
    reads: int = 0
    writes: int = 0
    tlb_hits: int = 0
    tlb_misses: int = 0
    page_hits: int = 0
    page_faults: int = 0
    evictions: int = 0
    writebacks: int = 0
    segfaults: int = 0
    cpu_time: int = 0
    io_time: int = 0

    def merge(self, other):
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))

    @property
    def fault_rate(self):
        return _ratio(self.page_faults, self.accesses)

    @property
    def tlb_hit_rate(self):
        return _ratio(self.tlb_hits, self.tlb_hits + self.tlb_misses)

    @property
    def avg_access_time(self):
        return _ratio(self.cpu_time + self.io_time, self.accesses)

    def as_dict(self):
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d.update(fault_rate=self.fault_rate, tlb_hit_rate=self.tlb_hit_rate,
                 avg_access_time=self.avg_access_time)
        return d


class Stats:
    def __init__(self):
        self.per_pid = defaultdict(Counters)
        self.finish_times = {}
        self.total_time = 0
        self.idle_time = 0
        self.tlb_enabled = True

    def register(self, pid):
        self.per_pid[pid]

    def record(self, r):
        c = self.per_pid[r.pid]
        c.accesses += 1
        if r.rw == "R":
            c.reads += 1
        else:
            c.writes += 1
        if r.kind == TLB_HIT:
            c.tlb_hits += 1
        else:
            c.tlb_misses += 1
        if r.kind == PAGE_FAULT:
            c.page_faults += 1
            if r.victim is not None:
                c.evictions += 1
            if r.writeback:
                c.writebacks += 1
        else:
            c.page_hits += 1
        c.cpu_time += r.cpu_cost
        c.io_time += r.io_time

    def total(self):
        t = Counters()
        for c in self.per_pid.values():
            t.merge(c)
        return t

    def to_dict(self):
        return {"total": self.total().as_dict(),
                "per_process": {str(p): c.as_dict() for p, c in sorted(self.per_pid.items())},
                "finish_times": {str(p): t for p, t in sorted(self.finish_times.items())},
                "total_time": self.total_time, "idle_time": self.idle_time}

    def format_report(self, cfg):
        t = self.total()
        tlb = "%.1f%%" % (100 * t.tlb_hit_rate) if cfg.tlb_size else "disabled"
        lines = [
            "=" * 64,
            "SIMULATION SUMMARY  (algorithm=%s, frames=%d, page=%dB, TLB=%d, sched=%s)"
            % (cfg.algorithm.upper(), cfg.num_frames, cfg.page_size, cfg.tlb_size, cfg.scheduler),
            "=" * 64,
            "Memory accesses : %d (%d reads, %d writes)" % (t.accesses, t.reads, t.writes),
            "Page faults     : %d (%.2f%%)" % (t.page_faults, 100 * t.fault_rate),
            "Page hits       : %d" % t.page_hits,
            "TLB hit rate    : %s" % tlb,
            "Evictions       : %d (dirty write-backs: %d)" % (t.evictions, t.writebacks),
            "Segfaults       : %d" % t.segfaults,
            "Avg access time : %.2f ticks" % t.avg_access_time,
            "Simulated time  : %d ticks (CPU idle: %d)" % (self.total_time, self.idle_time),
            "-" * 64,
            "%-6s %9s %7s %9s %10s %12s" % ("PID", "accesses", "faults", "fault %", "writebacks",
                                            "finished@"),
        ]
        for pid, c in sorted(self.per_pid.items()):
            lines.append("%-6s %9d %7d %8.2f%% %10d %12s" % (
                pid, c.accesses, c.page_faults, 100 * c.fault_rate, c.writebacks,
                self.finish_times.get(pid, "-")))
        return "\n".join(lines)
