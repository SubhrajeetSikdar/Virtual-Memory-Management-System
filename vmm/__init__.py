"""Virtual Memory Manager simulator."""
from .config import Config
from .exceptions import (AddressTranslationError, ConfigError, FrameNotFoundError,
                         RequestFormatError, SegmentationFault, SignalUser1, VMMError)
from .memory import MemoryManager
from .replacement import POLICIES
from .simulator import Simulator
from .stats import Stats
from .workload import Request, generate_workload, load_requests, parse_requests

__version__ = "2.0.0"
