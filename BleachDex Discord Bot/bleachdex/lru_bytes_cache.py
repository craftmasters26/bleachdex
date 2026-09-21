"""
Small in-memory, size-bounded LRU cache for byte blobs (downloaded
character art, rendered card PNGs).

Process-local only — resets on restart. That's fine: everything cached
here is cheap to regenerate, this only removes the *repeat* cost of
doing the same expensive work again within a single bot run (which is
most of the work, since the same ~roster of characters gets spawned/
caught/rendered over and over).

Bounded by TOTAL BYTES, not just item count, so it can never grow past
a fixed memory budget no matter how many distinct keys get cached —
important on RAM-constrained free hosts (see your hosting situation).
Nothing is ever written to disk.
"""

from collections import OrderedDict
from typing import Hashable, Optional


class BoundedByteCache:
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self._data: "OrderedDict[Hashable, bytes]" = OrderedDict()
        self._total = 0

    def get(self, key: Hashable) -> Optional[bytes]:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: Hashable, value: bytes) -> None:
        if key in self._data:
            self._total -= len(self._data[key])
        self._data[key] = value
        self._data.move_to_end(key)
        self._total += len(value)
        while self._total > self.max_bytes and self._data:
            _, oldest = self._data.popitem(last=False)
            self._total -= len(oldest)

    def __len__(self) -> int:
        return len(self._data)