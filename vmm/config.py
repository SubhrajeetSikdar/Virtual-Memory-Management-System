"""Simulation configuration and validation."""
from dataclasses import dataclass, field
from typing import Optional

from .exceptions import ConfigError
from .replacement import POLICIES
from .scheduler import SCHEDULER_POLICIES
from .utils import is_power_of_two


@dataclass
class Config:
    memory_size: int                 # physical memory in bytes
    page_size: int = 1024            # bytes, power of two
    address_bits: int = 16           # virtual address width
    algorithm: str = "lru"
    tlb_size: int = 4                # 0 disables the TLB
    scheduler: str = "rr"
    quantum: int = 1                 # requests per time slice
    tlb_time: int = 1                # simulated ticks
    memory_time: int = 10
    disk_time: int = 1000            # per page-in and per dirty write-back
    seed: Optional[int] = None

    offset_bits: int = field(init=False, repr=False, default=0)
    num_frames: int = field(init=False, repr=False, default=0)
    address_space_size: int = field(init=False, repr=False, default=0)
    num_pages: int = field(init=False, repr=False, default=0)

    def __post_init__(self):
        self.algorithm = self.algorithm.lower()
        self.scheduler = self.scheduler.lower()
        self.validate()
        self.offset_bits = self.page_size.bit_length() - 1
        self.num_frames = self.memory_size // self.page_size
        self.address_space_size = 1 << self.address_bits
        self.num_pages = 1 << (self.address_bits - self.offset_bits)

    def validate(self):
        if self.page_size <= 0 or not is_power_of_two(self.page_size):
            raise ConfigError("page size must be a positive power of two")
        if self.memory_size < self.page_size:
            raise ConfigError("memory size must hold at least one page")
        if self.memory_size % self.page_size:
            raise ConfigError("memory size must be a multiple of the page size")
        if not 1 <= self.address_bits <= 64 or \
                self.address_bits <= self.page_size.bit_length() - 1:
            raise ConfigError("address bits must exceed the page offset bits (and be <= 64)")
        if self.algorithm not in POLICIES:
            raise ConfigError("unknown algorithm %r (choose from %s)"
                              % (self.algorithm, ", ".join(POLICIES)))
        if self.scheduler not in SCHEDULER_POLICIES:
            raise ConfigError("unknown scheduler %r (choose from %s)"
                              % (self.scheduler, ", ".join(SCHEDULER_POLICIES)))
        if self.tlb_size < 0 or self.quantum < 1:
            raise ConfigError("tlb size must be >= 0 and quantum >= 1")
        if min(self.tlb_time, self.memory_time, self.disk_time) < 0:
            raise ConfigError("time costs must not be negative")

    @property
    def vaddr_hex_width(self):
        return (self.address_bits + 3) // 4

    @property
    def paddr_hex_width(self):
        return max(1, ((self.memory_size - 1).bit_length() + 3) // 4)
