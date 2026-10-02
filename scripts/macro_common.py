"""Small shared HTTP/observation helpers; no credentials or anti-bot bypass."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from http.cookiejar import CookieJar
import re
import time
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.parse import urlencode

from macro_catalog import SERIES

CACHE = None
_last_request = 0
OPENER = build_opener(HTTPCookieProcessor(CookieJar()))


def fetch(url, body=None, *, form=None):
    global _last_request
    encoded = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    if form is not None:
        if body is not None:
            raise ValueError("Choose JSON or form, not both")
        encoded = urlencode(form).encode()
    key = hashlib.sha256(url.encode() + (encoded or b"")).hexdigest()
    cache = Path(CACHE) / key if CACHE else None
    if cache and cache.exists():
        return cache.read_bytes()
    # Pace official sites; fail normally on access restrictions instead of bypassing.
    time.sleep(max(0, 1 - (time.monotonic() - _last_request)))
    _last_request = time.monotonic()
    headers = {"User-Agent": "finance-educational-data/1.0", "Accept": "*/*"}
    if body is not None:
        headers["Content-Type"] = "application/json;charset=UTF-8"
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    with OPENER.open(Request(url, data=encoded, headers=headers), timeout=45) as response:
        data = response.read()
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    return data


def number(value):
    text = str(value).strip().replace(",", "").replace("−", "-")
    if text in ("", "—", "…", "...", "-", "None", "null"):
        return None
    try:
        result = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"Not a number: {value!r}") from error
    if not result.is_finite():
        raise ValueError(f"Non-finite number: {value!r}")
    return result


def observation(series, period, value, url, published="", note=""):
    spec = SERIES[series]
    pattern = {"M": r"\d{4}-(0[1-9]|1[0-2])", "Q": r"\d{4}-Q[1-4]", "D": r"\d{4}-\d{2}-\d{2}"}[spec["frequency"]]
    if not re.fullmatch(pattern, period):
        raise ValueError(f"Wrong period for {series}: {period}")
    now = datetime.now(timezone.utc).date()
    if spec["frequency"] == "D":
        from datetime import date
        if date.fromisoformat(period) > now:
            raise ValueError("Future observation")
    elif spec["frequency"] == "M" and period > now.strftime("%Y-%m"):
        raise ValueError("Future observation month")
    elif spec["frequency"] == "Q" and period > f"{now.year}-Q{(now.month-1)//3+1}":
        raise ValueError("Future observation quarter")
    value = number(value)
    if value is None:
        return None
    bounds = (-100, 1000) if spec["unit"] == "%" else (-10000000, 100000000)
    if not bounds[0] <= value <= bounds[1]:
        raise ValueError(f"Implausible {series}: {value}")
    if series.startswith("pmi_") and not 0 <= value <= 100:
        raise ValueError("PMI outside 0..100")
    if series == "unemployment" and not 0 <= value <= 100:
        raise ValueError("Unemployment outside 0..100")
    if not url.startswith("https://"):
        raise ValueError("Missing HTTPS source URL")
    return dict(series_id=series, country="CHN", period=period, value=format(value, "f"),
                unit=spec["unit"], frequency=spec["frequency"], published_at=published,
                source_url=url, note=note)


def add(rows, *args, **kwargs):
    row = observation(*args, **kwargs)
    if row is not None:
        rows.append(row)
