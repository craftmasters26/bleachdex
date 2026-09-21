"""
Lets `image_path` / `card_image_path` fields hold EITHER a local file
path (rare - a manually-placed asset) OR a remote http(s) URL (e.g. a
raw.githubusercontent.com link). Everywhere in the codebase that needs
image bytes should go through fetch_image_bytes() instead of assuming
it's always a local path.

NOTHING IS WRITTEN TO DISK. This used to cache downloads to
admin/static/uploads/url_cache/ keyed by URL hash, so a repeat spawn
of the same character skipped the network call. That folder is gone
now - so instead there's an in-memory LRU (see lru_bytes_cache.py),
bounded by total bytes so it can't grow past a fixed budget regardless
of roster size. A repeat spawn/catch/render of the same character
skips the network round-trip AND the re-download entirely, at zero
disk usage - still nothing written to disk, still safe on a storage
quota, just no longer re-fetching the same bytes over and over.

I cannot test the actual HTTP fetch here - my build sandbox has no
internet access. The fetch/BytesIO logic is straightforward, but the
live download only gets proven once this runs on your host.
"""

import io
import urllib.request
import urllib.error
from typing import Optional

from lru_bytes_cache import BoundedByteCache

# Raw downloaded bytes only (not decoded images) - capped well under
# what a 512MB-class free host can spare. A typical roster's worth of
# character art fits comfortably inside this; if it doesn't, the LRU
# just evicts the least-recently-used entries as normal.
_URL_CACHE = BoundedByteCache(max_bytes=25 * 1024 * 1024)  # 25MB


def is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def fetch_image_bytes(path_or_url: str, timeout: int = 15) -> Optional[io.BytesIO]:
    """
    Returns a BytesIO of the image data - hand it straight to
    Image.open() or discord.File(), both accept a file-like object
    just as happily as a path string.

    If path_or_url is a local path, reads it straight off disk into
    the same BytesIO shape (no existence check beyond the read itself
    - callers already handle a missing/bad file via the None return).
    If it's a URL, a repeat request within the cache's lifetime is
    served from the in-memory LRU instead of re-downloading; otherwise
    it's fetched fresh and the result is cached for next time.
    Returns None if the URL can't be fetched, or the local file can't
    be read.
    """
    if not is_url(path_or_url):
        try:
            with open(path_or_url, "rb") as f:
                return io.BytesIO(f.read())
        except OSError:
            return None

    cached = _URL_CACHE.get(path_or_url)
    if cached is not None:
        return io.BytesIO(cached)

    try:
        req = urllib.request.Request(path_or_url, headers={"User-Agent": "BleachDex-Bot"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None

    _URL_CACHE.put(path_or_url, data)
    return io.BytesIO(data)