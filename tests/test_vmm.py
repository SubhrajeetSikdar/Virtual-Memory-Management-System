
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vmm import (AddressTranslationError, Config, ConfigError, MemoryManager, POLICIES,
                 RequestFormatError, SegmentationFault, Simulator, generate_workload,
                 parse_requests)
from vmm.memory import PAGE_FAULT, PAGE_HIT, TLB_HIT
from vmm.replacement import make_policy
from vmm.tlb import TLB
from vmm.utils import bintohex, hextobin, inttobin, inttohex, parse_size


def cfg(frames=4, **kw):
    return Config(memory_size=frames * 1024, **kw)


class UtilsTest(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(inttohex(255), "00FF")
        self.assertEqual(inttohex(-1), "FFFF")
        self.assertEqual(inttobin(5), "0000000000000101")
        self.assertEqual(hextobin("0x0400"), "0000010000000000")
        self.assertEqual(bintohex("1111111111111111"), "FFFF")

    def test_parse_size(self):
        self.assertEqual(parse_size("8K"), 8192)
        self.assertEqual(parse_size("2m"), 2 << 20)
        with self.assertRaises(ValueError):
            parse_size("abc")


class ConfigTest(unittest.TestCase):
    def test_non_power_of_two_frames_ok(self):
        self.assertEqual(Config(memory_size=3 * 1024).num_frames, 3)   # old code crashed

    def test_invalid(self):
        for kw in ({"memory_size": 0}, {"memory_size": 1500}, {"memory_size": 4096, "page_size": 1000},
                   {"memory_size": 4096, "algorithm": "x"}, {"memory_size": 4096, "address_bits": 8}):
            with self.assertRaises(ConfigError):
                Config(**kw)


class PolicyTest(unittest.TestCase):
    def load(self, name, n=3):
        p = make_policy(name, n, random.Random(0))
        for f in range(n):
            p.on_load(f)
        return p

    def test_fifo(self):
        p = self.load("fifo")
        p.on_access(0)
        self.assertEqual(p.choose_victim(), 0)

    def test_lru(self):
        p = self.load("lru")
        p.on_access(0)
        self.assertEqual(p.choose_victim(), 1)

    def test_lfu(self):
        p = self.load("lfu")
        for f in (0, 0, 1, 2, 2):
            p.on_access(f)
        self.assertEqual(p.choose_victim(), 1)

    def test_clock_second_chance(self):
        p = self.load("clock")           # all referenced -> hand sweeps, evicts frame 0
        self.assertEqual(p.choose_victim(), 0)
        p.on_evict(0)
        p.on_load(0)
        self.assertEqual(p.choose_victim(), 1)

    def test_random_and_evict(self):
        p = self.load("random")
        p.on_evict(1)
        for _ in range(20):
            self.assertIn(p.choose_victim(), (0, 2))


class TLBTest(unittest.TestCase):
    def test_lru_eviction_and_invalidate(self):
        t = TLB(2)
        t.insert(1, 0, 5)
        t.insert(1, 1, 6)
        t.lookup(1, 0)
        t.insert(1, 2, 7)
        self.assertIsNone(t.lookup(1, 1))
        self.assertEqual(t.lookup(1, 0), 5)
        t.invalidate(1, 0)
        self.assertIsNone(t.lookup(1, 0))

    def test_disabled(self):
        t = TLB(0)
        t.insert(1, 1, 1)
        self.assertEqual(len(t), 0)


class MemoryTest(unittest.TestCase):
    def mm(self, frames=2, **kw):
        m = MemoryManager(cfg(frames, algorithm="fifo", **kw), random.Random(0))
        for pid in (1, 2):
            m.create_process(pid)
        return m

    def test_fault_then_hits(self):
        m = self.mm()
        self.assertEqual(m.access(1, "R", 0x0010).kind, PAGE_FAULT)
        self.assertEqual(m.access(1, "R", 0x0020).kind, TLB_HIT)
        m.tlb.flush_pid(1)
        self.assertEqual(m.access(1, "R", 0x0030).kind, PAGE_HIT)

    def test_physical_address_correct_for_many_frames(self):
        # old code truncated the physical address to 16 bits
        m = MemoryManager(Config(memory_size=1 << 20, address_bits=20), random.Random(0))
        m.create_process(1)
        for page in range(100):
            m.access(1, "R", page << 10)
        r = m.access(1, "R", (99 << 10) | 0x3FF)
        self.assertEqual(r.paddr, (99 << 10) | 0x3FF)

    def test_dirty_writeback_and_clean_reload(self):
        m = self.mm(frames=1)
        m.access(1, "W", 0x0000)
        r = m.access(1, "R", 0x0400)
        self.assertTrue(r.writeback)
        self.assertEqual(r.victim, (1, 0))
        r = m.access(1, "R", 0x0000)                 # reloaded page must be clean
        self.assertFalse(r.writeback)
        self.assertEqual(r.io_time, m.cfg.disk_time)

    def test_evicted_page_leaves_tlb(self):
        m = self.mm(frames=1)
        m.access(1, "R", 0x0000)
        m.access(1, "R", 0x0400)
        self.assertEqual(m.access(1, "R", 0x0000).kind, PAGE_FAULT)

    def test_terminate_frees_frames(self):
        m = self.mm(frames=2)
        m.access(1, "R", 0)
        m.access(1, "R", 0x400)
        self.assertEqual(m.terminate_process(1), 2)
        r = m.access(2, "R", 0)
        self.assertIsNone(r.victim)

    def test_segfault_and_v2p(self):
        m = self.mm()
        with self.assertRaises(SegmentationFault):
            m.access(1, "R", 0x10000)
        with self.assertRaises(AddressTranslationError):
            m.v2p(1, 0x0400)
        m.access(1, "R", 0x0400)
        self.assertEqual(m.v2p(1, 0x0404), (m.page_tables[1][1].frame << 10) | 4)

    def test_isolation_between_processes(self):
        m = self.mm(frames=2)
        a = m.access(1, "R", 0)
        b = m.access(2, "R", 0)
        self.assertNotEqual(a.frame, b.frame)


class ParserTest(unittest.TestCase):
    def test_parse(self):
        reqs, errs = parse_requests(["# c", "", "1, w, 0x0400  # x", "bad", "1,X,00", "2,R,zz"])
        self.assertEqual(len(reqs), 1)
        self.assertEqual((reqs[0].pid, reqs[0].rw, reqs[0].vaddr), (1, "W", 0x400))
        self.assertEqual(len(errs), 3)

    def test_strict(self):
        with self.assertRaises(RequestFormatError):
            parse_requests(["nonsense"], strict=True)


class SimulatorTest(unittest.TestCase):
    def requests(self, n=40, seed=3):
        reqs, _ = parse_requests(generate_workload(4, n, seed=seed))
        return reqs

    def test_all_requests_served_for_every_combo(self):
        reqs = self.requests()
        for algo in POLICIES:
            for sched in ("rr", "fifo", "random"):
                for tlb in (0, 4):
                    s = Simulator(cfg(4, algorithm=algo, scheduler=sched, tlb_size=tlb, seed=1),
                                  reqs, log=None).run()
                    t = s.total()
                    self.assertEqual(t.accesses, len(reqs), (algo, sched, tlb))
                    self.assertEqual(len(s.finish_times), 4)
                    self.assertEqual(t.page_faults + t.page_hits, t.accesses)

    def test_deterministic_with_seed(self):
        reqs = self.requests()
        a = Simulator(cfg(3, algorithm="random", scheduler="random", seed=9), reqs, log=None).run()
        b = Simulator(cfg(3, algorithm="random", scheduler="random", seed=9), reqs, log=None).run()
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_segfault_kills_only_that_process(self):
        reqs, _ = parse_requests(["1,R,0000", "2,R,FFFF", "1,R,0400"])
        reqs = [r for r in reqs]
        s = Simulator(cfg(2, address_bits=11), reqs, log=None).run()   # 2 KiB address space
        self.assertEqual(s.per_pid[2].segfaults, 1)
        self.assertEqual(s.per_pid[1].accesses, 2)

    def test_quantum_and_fifo_terminate(self):
        reqs = self.requests(10)
        s = Simulator(cfg(2, quantum=5), reqs, log=None).run()
        self.assertEqual(s.total().accesses, 40)

    def test_no_faults_after_warmup_when_memory_is_large(self):
        reqs, _ = parse_requests(["1,R,0000"] * 5 + ["1,W,0400"] * 5)
        s = Simulator(cfg(8), reqs, log=None).run()
        self.assertEqual(s.total().page_faults, 2)

    def test_error_propagates(self):
        sim = Simulator(cfg(2), parse_requests(["1,R,0000"])[0], log=None)
        sim.mm.access = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
        with self.assertRaises(RuntimeError):
            sim.run()


if __name__ == "__main__":
    unittest.main()
