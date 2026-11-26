#!/usr/bin/env python3
"""Generate a synthetic request file:  python generate_workload.py -p 4 -n 100 > requests.txt"""
import argparse

from vmm import generate_workload
from vmm.utils import parse_size

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("-p", "--processes", type=int, default=4)
ap.add_argument("-n", "--per-process", type=int, default=50)
ap.add_argument("--address-bits", type=int, default=16)
ap.add_argument("--page-size", type=parse_size, default=1024)
ap.add_argument("--locality", type=float, default=0.8, help="probability of hitting the working set")
ap.add_argument("--working-set", type=int, default=4, help="pages per process working set")
ap.add_argument("--write-ratio", type=float, default=0.3)
ap.add_argument("--seed", type=int)
a = ap.parse_args()
print("\n".join(generate_workload(a.processes, a.per_process, a.address_bits, a.page_size,
                                  a.locality, a.working_set, a.write_ratio, a.seed)))
