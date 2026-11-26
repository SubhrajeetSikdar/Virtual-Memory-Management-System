# Virtual Memory Manager (VMM) Simulator

A multi-threaded, demand-paging virtual memory simulator in pure Python 3 (no dependencies).
An OS-scheduler thread dispatches processes to an MMU thread, which translates virtual
addresses through a TLB and per-process page tables, handles page faults through a simulated
`SIGUSR1` interrupt, and evicts pages with a pluggable replacement algorithm.

## Features

- **Page replacement algorithms:** `fifo`, `lru`, `lfu`, `clock` (second chance), `random`
- **TLB:** fully associative, LRU, invalidated on eviction and process exit (size 0 disables it)
- **Demand paging** with present / dirty / referenced bits; dirty pages cost an extra disk write-back
- **Schedulers:** `rr` (round robin with configurable quantum), `fifo` (run until block/finish), `random`
- **Blocked queue with simulated disk I/O:** page-faulting processes sleep while others run
- **Simulated clock** (ticks) instead of `time.sleep`, so runs finish instantly and are reproducible
- **Process exit:** frames are freed when a process finishes or is killed
- **Segmentation faults** for addresses outside the address space (only that process is killed)
- **Configurable** memory size, page size, address width, timing costs, seed
- **Statistics:** faults, hit rates, write-backs, average access time, per-process table
- **Algorithm comparison mode** (`--compare`), JSON stats export, CSV access trace
- **Workload generator** with locality, **robust input parser**, unit tests

## Usage

```bash
python main.py <input_file> <memory_size> [options]

python main.py sample_requests.txt 4096 --seed 1 --show-memory
python main.py workload_large.txt 8K -a clock --tlb-size 8 -q
python main.py workload_large.txt 8K --compare --seed 5
python main.py workload_large.txt 8K -a lru --stats-json stats.json --trace-csv trace.csv
```

`memory_size` is in bytes and accepts `K`/`M`/`G` suffixes. It must be a multiple of the page size
(it no longer has to be a power of two number of frames).

| Option | Default | Meaning |
|---|---|---|
| `-a, --algorithm` | `lru` | `fifo`, `lru`, `lfu`, `clock`, `random` |
| `-s, --scheduler` | `rr` | `rr`, `fifo`, `random` |
| `--quantum` | 1 | requests per time slice |
| `--page-size` | 1024 | bytes, power of two |
| `--address-bits` | 16 | virtual address width |
| `--tlb-size` | 4 | 0 disables the TLB |
| `--tlb-time / --memory-time / --disk-time` | 1 / 10 / 1000 | simulated cost in ticks |
| `--seed` | random | reproducible runs |
| `-q, --quiet` | | summary only |
| `--show-memory` | | print frame map after each access |
| `--strict` | | abort on malformed input lines |
| `--stats-json / --trace-csv` | | export results |
| `--compare` | | run all algorithms on the same input |

### Input format

```
# pid,R|W,hex_address      (blank lines and # comments are allowed)
1,R,04A0
2,w,0x0C10
```

Generate a synthetic workload: `python generate_workload.py -p 4 -n 100 --locality 0.8 --seed 7 > requests.txt`

### Cost model

TLB hit = `tlb + mem`. TLB miss, page resident = `tlb + 2*mem`. Page fault = `tlb + 2*mem` of CPU
time plus `disk` ticks of blocking I/O (`2*disk` if a dirty page is written back first).

## File structure

```
main.py                CLI
generate_workload.py   synthetic request generator
vmm/
  config.py            configuration + validation
  memory.py            page tables, frames, TLB use, fault handler (MMU access path)
  replacement.py       FIFO / LRU / LFU / Clock / Random
  tlb.py               TLB
  scheduler.py         ready + blocked queues, scheduling policies
  simulator.py         scheduler thread + MMU thread
  stats.py             statistics and report
  workload.py          parser + generator
  exceptions.py        AddressTranslationError, FrameNotFoundError, SegmentationFault,
                       SignalUser1, ... (replaces vmmmisc.py)
  utils.py             inttohex / inttobin / hextobin / bintohex + parsing helpers
tests/test_vmm.py      26 unit tests  (python -m unittest discover -s tests)
```

## Bugs fixed compared to the original version

1. `vmm.py` read the input and started threads at import time, and `main.py` did the same again,
   so everything ran twice. Now `vmm` is an importable package and only `main.py` starts a run.
2. A process was only re-queued after a page fault, so processes with several requests silently
   lost their remaining requests after a direct access. Processes are now always re-queued.
3. The scheduler called `os._exit(0)` while the MMU might still be working. Replaced by a
   clean two-thread hand-off with proper shutdown and error propagation.
4. Physical addresses were truncated to 16 bits (frame number overflow). Now computed with shifts.
5. Evicted pages kept their dirty bit and stale frame number; reloaded pages were wrongly dirty.
6. Stale translations: evictions and exits now invalidate cached translations.
7. `processExit` was never called, leaking frames. Processes now free their frames when done.
8. `math.log(P, 2)` crashed or mis-sized for non powers of two / tiny memory. Replaced by validation.
9. Crashes on blank lines, malformed lines, bad hex, addresses beyond 16 bits (silently wrapped).
10. Random victim could pick an empty frame; `getSwapCandidate` mixed up "free frame" and "victim".
11. `inttobin` for negatives wasn't padded; `.upper()[2:]` hacks removed.
12. Exceptions' `__str__` returned `repr(...)`, with a typo ("Tranlation").
13. README described the wrong files and had empty sections.

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT
