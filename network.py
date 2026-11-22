"""Network measurements and lookup helpers."""

import time
from concurrent.futures import ThreadPoolExecutor

import requests

# Timeouts in seconds.
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
MEASURE_SECONDS = 10.0
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

DOWNLOAD_URL = "https://speed.cloudflare.com/__down"
UPLOAD_URL = "https://speed.cloudflare.com/__up"
DOWNLOAD_BYTES = 50_000_000  # Cloudflare does not accept 100 MB
UPLOAD_BYTES = 10_000_000

IP_URL = "https://api.ipify.org"
GEO_URL = "https://ipwho.is/"

CHUNK_SIZE = 64 * 1024


class MeasurementCancelled(Exception):
    """Raised internally when a measurement is cancelled."""


def _check_cancelled(cancel):
    if cancel is not None and cancel():
        raise MeasurementCancelled


def _error_text(exc, prefix="Unavailable"):
    return f"{prefix} ({exc.__class__.__name__})"


def _get(url):
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response


def _to_mbit(byte_count, elapsed, phase):
    if elapsed <= 0:
        raise RuntimeError(f"{phase} finished too fast to measure")
    return byte_count * 8 / elapsed / 1_000_000


def _measure_download(session, cancel=None):
    """Measure download speed in Mbit/s, downloading for at most MEASURE_SECONDS."""
    _check_cancelled(cancel)
    with session.get(
        DOWNLOAD_URL,
        params={"bytes": DOWNLOAD_BYTES},
        stream=True,
        timeout=TIMEOUT,
    ) as response:
        response.raise_for_status()
        started = time.perf_counter()
        received = 0
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            received += len(chunk)
            if time.perf_counter() - started >= MEASURE_SECONDS:
                break
            _check_cancelled(cancel)
        elapsed = time.perf_counter() - started

    return _to_mbit(received, elapsed, "download")


def _measure_upload(session, cancel=None):
    """Measure upload speed in Mbit/s."""
    _check_cancelled(cancel)
    payload = b"\0" * UPLOAD_BYTES
    started = time.perf_counter()
    response = session.post(UPLOAD_URL, data=payload, timeout=TIMEOUT)
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    _check_cancelled(cancel)

    return _to_mbit(UPLOAD_BYTES, elapsed, "upload")


def measure_speed(cancel=None):
    """Return (download, upload) in Mbit/s. Raises on failure."""
    # One session for both phases reuses the TLS connection to Cloudflare
    # instead of paying for a second handshake before the upload.
    with requests.Session() as session:
        download_speed = _measure_download(session, cancel)
        upload_speed = _measure_upload(session, cancel)
    return download_speed, upload_speed


def get_ip(cancel=None):
    _check_cancelled(cancel)
    try:
        return _get(IP_URL).text.strip()
    except requests.RequestException as exc:
        return _error_text(exc)


def get_location(cancel=None):
    _check_cancelled(cancel)
    try:
        data = _get(GEO_URL).json()
        if not data.get("success"):
            return "Unknown"
        return f"{data.get('city') or 'Unknown'}, {data.get('country') or 'Unknown'}"
    except (requests.RequestException, ValueError) as exc:
        return _error_text(exc, "Unknown")


def collect_results(cancel=None):
    """Run every check concurrently and return a result payload."""
    with ThreadPoolExecutor(max_workers=3) as executor:
        speed_future = executor.submit(measure_speed, cancel)
        ip_future = executor.submit(get_ip, cancel)
        location_future = executor.submit(get_location, cancel)

        try:
            speed = speed_future.result()
        except (requests.RequestException, RuntimeError) as exc:
            speed = _error_text(exc)
        ip = ip_future.result()
        location = location_future.result()

    return {"speed": speed, "ip": ip, "location": location}
