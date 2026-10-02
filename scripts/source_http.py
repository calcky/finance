"""Bounded retries for public data reads, including read-only search POSTs."""

from http.client import IncompleteRead
import socket
import time
from urllib.error import HTTPError, URLError


def transient(error):
    if isinstance(error, HTTPError):
        # Do not retry access refusals or rate limits; respect the source.
        return error.code in (500, 502, 503, 504)
    reason = error.reason if isinstance(error, URLError) else error
    return (isinstance(reason, (TimeoutError, ConnectionError, IncompleteRead))
            or isinstance(reason, socket.gaierror) and reason.errno == socket.EAI_AGAIN)


def read(request, opener, timeout=45):
    """Read the entire response before returning; never cache a partial body."""
    for attempt in range(1, 4):
        try:
            with opener(request, timeout=timeout) as response:
                return response.read()
        except (OSError, IncompleteRead) as error:
            error.source_url = request.full_url
            error.add_note(f"Source: {request.get_method()} {request.full_url}")
            retry = attempt < 3 and transient(error)
            print(f"HTTP {'retry' if retry else 'failed'} {attempt}/3 "
                  f"{request.get_method()} {request.full_url}: "
                  f"{type(error).__name__}: {error}", flush=True)
            if not retry:
                raise
            time.sleep(2 ** attempt)


def describe(error):
    """Compact failure for status reports without losing chained source context."""
    parts, seen = [], set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        part = f"{type(error).__name__}: {error}"
        if getattr(error, "source_url", None):
            part += f" [source: {error.source_url}]"
        parts.append(part)
        error = error.__cause__
    return " <- ".join(parts)
