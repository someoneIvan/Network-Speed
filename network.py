"""Network measurements and lookup helpers."""

import statistics
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

PING_URL = "https://speed.cloudflare.com/__down"
PING_SAMPLES = 5
PING_BYTES = 0

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


def measure_ping(session=None, samples=PING_SAMPLES, cancel=None):
    """Return the median round-trip time in milliseconds.

    A warm-up request is made first so the TLS handshake is not counted. The
    remaining samples are sent over the same connection.
    """
    _check_cancelled(cancel)
    own_session = session is None
    if own_session:
        session = requests.Session()

    try:
        with session.get(
            PING_URL,
            params={"bytes": PING_BYTES},
            timeout=TIMEOUT,
        ) as response:
            response.raise_for_status()

        timings = []
        for _ in range(samples):
            _check_cancelled(cancel)
            started = time.perf_counter()
            with session.get(
                PING_URL,
                params={"bytes": PING_BYTES},
                timeout=TIMEOUT,
            ) as response:
                response.raise_for_status()
            timings.append((time.perf_counter() - started) * 1000)

        if not timings:
            raise RuntimeError("ping measurement produced no samples")
        return statistics.median(timings)
    finally:
        if own_session:
            session.close()


def measure_speed(cancel=None):
    """Return (download, upload, ping). Speeds are Mbit/s, ping is in ms."""
    # One session for all phases reuses the TLS connection to Cloudflare
    # instead of paying for a new handshake before every request.
    with requests.Session() as session:
        try:
            ping = measure_ping(session, cancel=cancel)
        except MeasurementCancelled:
            raise
        except requests.RequestException as exc:
            # A failed ping must not abort the speed measurement.
            ping = _error_text(exc)

        download_speed = _measure_download(session, cancel)
        upload_speed = _measure_upload(session, cancel)
    return download_speed, upload_speed, ping


def get_ip(cancel=None):
    _check_cancelled(cancel)
    try:
        return _get(IP_URL).text.strip()
    except requests.RequestException as exc:
        return _error_text(exc)


def get_geo(cancel=None):
    """Return (location, provider) from the geolocation service."""
    _check_cancelled(cancel)
    try:
        data = _get(GEO_URL).json()
        if not data.get("success"):
            return "Unknown", "Unknown"

        location = (
            f"{data.get('city') or 'Unknown'}, "
            f"{data.get('country') or 'Unknown'}"
        )
        connection = data.get("connection")
        if not isinstance(connection, dict):
            connection = {}
        provider = (
            connection.get("isp")
            or connection.get("org")
            or "Unknown"
        )
        return location, provider
    except (requests.RequestException, ValueError) as exc:
        return _error_text(exc, "Unknown"), "Unknown"


def get_location(cancel=None):
    return get_geo(cancel)[0]


def get_provider(cancel=None):
    return get_geo(cancel)[1]


def collect_results(cancel=None):
    """Run every check concurrently and return a result payload."""
    with ThreadPoolExecutor(max_workers=3) as executor:
        speed_future = executor.submit(measure_speed, cancel)
        ip_future = executor.submit(get_ip, cancel)
        geo_future = executor.submit(get_geo, cancel)

        ping = "Unavailable"
        try:
            speed_result = speed_future.result()
        except (requests.RequestException, RuntimeError) as exc:
            speed = _error_text(exc)
        else:
            if isinstance(speed_result, tuple) and len(speed_result) == 3:
                download, upload, ping = speed_result
                speed = (download, upload)
            else:
                speed = speed_result

        ip = ip_future.result()
        location, provider = geo_future.result()

    return {
        "speed": speed,
        "ping": ping,
        "provider": provider,
        "ip": ip,
        "location": location,
    }
