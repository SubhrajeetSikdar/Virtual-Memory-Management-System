"""Memory manager: page tables, frame table, TLB and demand paging."""
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple

from .exceptions import (AddressTranslationError, FrameNotFoundError, RequestFormatError,
                         SegmentationFault, SignalUser1, VMMError)
from .replacement import make_policy
from .tlb import TLB
from .utils import join_address, split_address

TLB_HIT, PAGE_HIT, PAGE_FAULT = "TLB_HIT", "PAGE_HIT", "PAGE_FAULT"


class PageTableEntry:
    __slots__ = ("present", "dirty", "referenced", "frame")

    def __init__(self):
        self.present = False
        self.dirty = False
        self.referenced = False
        self.frame = -1


@dataclass
class FaultInfo:
    frame: int
    victim: Optional[Tuple[int, int]]   # (pid, page) that was evicted
    writeback: bool


@dataclass
class AccessResult:
    pid: int
    rw: str
    vaddr: int
    page: int
    offset: int
    frame: int
    paddr: int
    kind: str
    cpu_cost: int
    io_time: int = 0
    victim: Optional[Tuple[int, int]] = None
    writeback: bool = False


class MemoryManager:
    def __init__(self, cfg, rng=None):
        self.cfg = cfg
        self.frames = [None] * cfg.num_frames           # frame -> (pid, page)
        self.free_frames = deque(range(cfg.num_frames))
        self.page_tables = {}                           # pid -> {page: PageTableEntry} (lazy)
        self.policy = make_policy(cfg.algorithm, cfg.num_frames, rng)
        self.tlb = TLB(cfg.tlb_size)
        self.signal = SignalUser1()                     # page-fault interrupt line
        self.signal.connect(self._page_fault_handler)

    # ---- process lifecycle -------------------------------------------------
    def create_process(self, pid):
        self.page_tables.setdefault(pid, {})

    def terminate_process(self, pid):
        """Free every frame of `pid`; returns how many were released."""
        table = self.page_tables.pop(pid, None)
        if table is None:
            return 0
        freed = 0
        for pte in table.values():
            if pte.present:
                self.frames[pte.frame] = None
                self.policy.on_evict(pte.frame)
                self.free_frames.append(pte.frame)
                freed += 1
        self.tlb.flush_pid(pid)
        return freed

    # ---- page table --------------------------------------------------------
    def get_entry(self, pid, page):
        pte = self.page_tables[pid].get(page)
        if pte is None or not pte.present:
            raise FrameNotFoundError(pid, page)
        return pte.frame

    def v2p(self, pid, vaddr):
        """Side-effect free translation (no TLB, no fault handling)."""
        self._check_range(pid, vaddr)
        page, offset = split_address(vaddr, self.cfg.offset_bits)
        try:
            frame = self.get_entry(pid, page)
        except FrameNotFoundError:
            raise AddressTranslationError(pid, vaddr) from None
        return join_address(frame, offset, self.cfg.offset_bits)

    def _check_range(self, pid, vaddr):
        if pid not in self.page_tables:
            raise VMMError("unknown process %s" % pid)
        if not 0 <= vaddr < self.cfg.address_space_size:
            raise SegmentationFault(pid, vaddr)

    # ---- the MMU access path ----------------------------------------------
    def access(self, pid, rw, vaddr):
        cfg = self.cfg
        if rw not in ("R", "W"):
            raise RequestFormatError("access type must be R or W, got %r" % rw)
        self._check_range(pid, vaddr)
        page, offset = split_address(vaddr, cfg.offset_bits)
        cost, io, victim, writeback = 0, 0, None, False

        frame = None
        if self.tlb.enabled:
            cost += cfg.tlb_time
            frame = self.tlb.lookup(pid, page)
        if frame is not None:
            kind = TLB_HIT
        else:
            cost += cfg.memory_time                      # page-table walk
            try:
                frame = self.get_entry(pid, page)
                kind = PAGE_HIT
            except FrameNotFoundError:
                kind = PAGE_FAULT
                self.signal.set(pid, page)               # raise SIGUSR1
                fault = self.signal.send()
                frame, victim, writeback = fault.frame, fault.victim, fault.writeback
                io = cfg.disk_time * (2 if writeback else 1)
            self.tlb.insert(pid, page, frame)
        cost += cfg.memory_time                          # the actual data access

        pte = self.page_tables[pid][page]
        pte.referenced = True
        if rw == "W":
            pte.dirty = True
        self.policy.on_access(frame)
        return AccessResult(pid, rw, vaddr, page, offset, frame,
                            join_address(frame, offset, cfg.offset_bits),
                            kind, cost, io, victim, writeback)

    def _page_fault_handler(self, pid, page):
        victim, writeback = None, False
        if self.free_frames:
            frame = self.free_frames.popleft()
        else:
            frame = self.policy.choose_victim()
            vpid, vpage = self.frames[frame]
            vpte = self.page_tables[vpid][vpage]
            writeback = vpte.dirty
            vpte.present = vpte.dirty = vpte.referenced = False
            vpte.frame = -1
            self.tlb.invalidate(vpid, vpage)
            self.policy.on_evict(frame)
            victim = (vpid, vpage)
        self.frames[frame] = (pid, page)
        pte = self.page_tables[pid].setdefault(page, PageTableEntry())
        pte.present, pte.frame = True, frame
        pte.dirty = pte.referenced = False               # fresh page: clean
        self.policy.on_load(frame)
        return FaultInfo(frame, victim, writeback)

    def snapshot(self):
        return list(self.frames)
