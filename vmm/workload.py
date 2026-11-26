"""Request-file parsing and synthetic workload generation."""
import random
from dataclasses import dataclass

from .exceptions import RequestFormatError
from .utils import inttohex, parse_address


@dataclass(frozen=True)
class Request:
    pid: int
    rw: str
    vaddr: int


def parse_line(line):
    """Parse 'pid,R|W,hexaddr'. Returns None for blank/comment lines."""
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 3:
        raise RequestFormatError("expected 'pid,R|W,hex_address'")
    try:
        pid = int(parts[0])
    except ValueError:
        raise RequestFormatError("invalid pid %r" % parts[0]) from None
    if pid < 0:
        raise RequestFormatError("pid must not be negative")
    rw = parts[1].upper()
    if rw not in ("R", "W"):
        raise RequestFormatError("access type must be R or W, got %r" % parts[1])
    try:
        return Request(pid, rw, parse_address(parts[2]))
    except ValueError as exc:
        raise RequestFormatError(str(exc)) from None


def parse_requests(lines, strict=False):
    """Returns (requests, errors). Bad lines are skipped unless strict=True."""
    requests, errors = [], []
    for n, line in enumerate(lines, 1):
        try:
            req = parse_line(line)
        except RequestFormatError as exc:
            if strict:
                raise RequestFormatError("line %d: %s" % (n, exc)) from None
            errors.append("line %d: %s" % (n, exc))
            continue
        if req:
            requests.append(req)
    return requests, errors


def load_requests(path, strict=False):
    with open(path, "r") as fh:
        return parse_requests(fh, strict)


def generate_workload(processes=4, per_process=50, address_bits=16, page_size=1024,
                      locality=0.8, working_set=4, write_ratio=0.3, seed=None):
    """Interleaved request lines with temporal locality (a drifting working set per process)."""
    rng = random.Random(seed)
    offset_bits = page_size.bit_length() - 1
    num_pages = 1 << (address_bits - offset_bits)
    working_set = max(1, min(working_set, num_pages))
    sets = {p: rng.sample(range(num_pages), working_set) for p in range(1, processes + 1)}
    remaining = {p: per_process for p in sets}
    lines = []
    while remaining:
        pid = rng.choice(list(remaining))
        ws = sets[pid]
        if rng.random() < locality:
            page = rng.choice(ws)
        else:
            page = rng.randrange(num_pages)
            ws[rng.randrange(len(ws))] = page            # the working set drifts
        vaddr = (page << offset_bits) | rng.randrange(page_size)
        rw = "W" if rng.random() < write_ratio else "R"
        lines.append("%d,%s,%s" % (pid, rw, inttohex(vaddr, address_bits)))
        remaining[pid] -= 1
        if not remaining[pid]:
            del remaining[pid]
    return lines
