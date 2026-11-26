#!/usr/bin/env python3
"""Command line entry point:  python main.py <input_file> <memory_size> [options]"""
import argparse
import csv
import json
import random
import sys

from vmm import Config, POLICIES, Simulator, VMMError, load_requests
from vmm.scheduler import SCHEDULER_POLICIES
from vmm.utils import inttohex, parse_size


def build_parser():
    p = argparse.ArgumentParser(description="Virtual memory manager simulator")
    p.add_argument("input_file", help="request file with lines 'pid,R|W,hex_address'")
    p.add_argument("memory_size", type=parse_size, help="physical memory in bytes (8192, 8K, 1M)")
    p.add_argument("--page-size", type=parse_size, default=1024, help="default 1024")
    p.add_argument("--address-bits", type=int, default=16, help="virtual address width (16)")
    p.add_argument("-a", "--algorithm", default="lru", choices=sorted(POLICIES))
    p.add_argument("--tlb-size", type=int, default=4, help="TLB entries, 0 disables (4)")
    p.add_argument("-s", "--scheduler", default="rr", choices=SCHEDULER_POLICIES)
    p.add_argument("--quantum", type=int, default=1, help="requests per time slice (1)")
    p.add_argument("--tlb-time", type=int, default=1)
    p.add_argument("--memory-time", type=int, default=10)
    p.add_argument("--disk-time", type=int, default=1000)
    p.add_argument("--seed", type=int, default=None, help="make the run reproducible")
    p.add_argument("-q", "--quiet", action="store_true", help="print only the summary")
    p.add_argument("--show-memory", action="store_true", help="print memory map after each access")
    p.add_argument("--strict", action="store_true", help="abort on malformed request lines")
    p.add_argument("--stats-json", metavar="FILE", help="write statistics as JSON")
    p.add_argument("--trace-csv", metavar="FILE", help="write per-access trace as CSV")
    p.add_argument("--compare", action="store_true", help="run every algorithm and compare")
    return p


def make_config(args, algorithm, seed):
    return Config(memory_size=args.memory_size, page_size=args.page_size,
                  address_bits=args.address_bits, algorithm=algorithm,
                  tlb_size=args.tlb_size, scheduler=args.scheduler, quantum=args.quantum,
                  tlb_time=args.tlb_time, memory_time=args.memory_time,
                  disk_time=args.disk_time, seed=seed)


def write_trace(path, trace, cfg):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["seq", "pid", "rw", "vaddr", "page", "offset", "frame", "paddr", "kind",
                    "victim_pid", "victim_page", "writeback", "cpu_cost", "io_time"])
        for i, r in enumerate(trace, 1):
            vp, vg = r.victim if r.victim else ("", "")
            w.writerow([i, r.pid, r.rw, inttohex(r.vaddr, cfg.address_bits), r.page, r.offset,
                        r.frame, "%0*X" % (cfg.paddr_hex_width, r.paddr), r.kind, vp, vg,
                        int(r.writeback), r.cpu_cost, r.io_time])


def compare(args, requests, seed):
    rows = []
    for name in sorted(POLICIES):
        cfg = make_config(args, name, seed)
        stats = Simulator(cfg, requests, log=None).run()
        t = stats.total()
        rows.append((name.upper(), t.page_faults, 100 * t.fault_rate, t.writebacks,
                     100 * t.tlb_hit_rate, t.avg_access_time, stats.total_time))
    rows.sort(key=lambda r: (r[1], r[6]))
    print("Algorithm comparison (seed=%s, %d frames)" % (seed, make_config(args, "lru", seed).num_frames))
    print("%-8s %7s %8s %11s %8s %10s %10s" %
          ("ALGO", "faults", "fault %", "writebacks", "TLB hit%", "avg time", "total time"))
    for r in rows:
        print("%-8s %7d %7.2f%% %11d %7.1f%% %10.2f %10d" % r)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        requests, errors = load_requests(args.input_file, strict=args.strict)
        for e in errors[:10]:
            print("warning: skipped %s" % e, file=sys.stderr)
        if len(errors) > 10:
            print("warning: ... and %d more malformed lines" % (len(errors) - 10), file=sys.stderr)
        if not requests:
            print("error: no valid requests found", file=sys.stderr)
            return 1
        seed = args.seed if args.seed is not None else random.randrange(1 << 30)
        if args.compare:
            compare(args, requests, seed)
            return 0
        cfg = make_config(args, args.algorithm, seed)
        sim = Simulator(cfg, requests, log=None if args.quiet else print,
                        show_memory=args.show_memory, collect_trace=bool(args.trace_csv))
        stats = sim.run()
    except (VMMError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    print("\n" + stats.format_report(cfg))
    if args.stats_json:
        with open(args.stats_json, "w") as fh:
            json.dump(stats.to_dict(), fh, indent=2)
    if args.trace_csv:
        write_trace(args.trace_csv, sim.trace, cfg)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:                      # e.g. output piped into `head`
        sys.stderr.close()
        sys.exit(0)
