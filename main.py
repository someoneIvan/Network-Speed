import time
from concurrent.futures import ThreadPoolExecutor

import requests

# Timeouts in seconds.
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
MEASURE_SECONDS = 10.0

DOWNLOAD_URL = "https://speed.cloudflare.com/__down"
UPLOAD_URL = "https://speed.cloudflare.com/__up"
DOWNLOAD_BYTES = 50_000_000  # Cloudflare does not accept 100 MB
UPLOAD_BYTES = 10_000_000

IP_URL = "https://api.ipify.org"
GEO_URL = "https://ipwho.is/"

CHUNK_SIZE = 64 * 1024


def _measure_download(session):
    """Measure download speed in Mbit/s, downloading for at most MEASURE_SECONDS."""
    with session.get(
        DOWNLOAD_URL,
        params={"bytes": DOWNLOAD_BYTES},
        stream=True,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    ) as response:
        response.raise_for_status()
        started = time.perf_counter()
        received = 0
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            received += len(chunk)
            if time.perf_counter() - started >= MEASURE_SECONDS:
                break
        elapsed = time.perf_counter() - started

    if elapsed <= 0:
        raise RuntimeError("download finished too fast to measure")
    return received * 8 / elapsed / 1_000_000


def _measure_upload(session):
    """Measure upload speed in Mbit/s."""
    payload = b"\0" * UPLOAD_BYTES
    started = time.perf_counter()
    response = session.post(
        UPLOAD_URL,
        data=payload,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    elapsed = time.perf_counter() - started
    response.raise_for_status()

    if elapsed <= 0:
        raise RuntimeError("upload finished too fast to measure")
    return UPLOAD_BYTES * 8 / elapsed / 1_000_000


def get_internet_speed():
    try:
        # One session for both phases reuses the TLS connection to Cloudflare
        # instead of paying for a second handshake before the upload.
        with requests.Session() as session:
            download_speed = _measure_download(session)
            upload_speed = _measure_upload(session)
        return f"Download: {download_speed:.2f} Mbit/s, Upload: {upload_speed:.2f} Mbit/s"
    except (requests.RequestException, RuntimeError) as exc:
        return f"Unavailable ({exc.__class__.__name__})"


def get_ip():
    try:
        response = requests.get(IP_URL, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as exc:
        return f"Unavailable ({exc.__class__.__name__})"


def get_location():
    try:
        response = requests.get(GEO_URL, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            return "Unknown"
        return f"{data.get('city') or 'Unknown'}, {data.get('country') or 'Unknown'}"
    except (requests.RequestException, ValueError) as exc:
        return f"Unknown ({exc.__class__.__name__})"


def main():
    with ThreadPoolExecutor(max_workers=3) as executor:
        speed_future = executor.submit(get_internet_speed)
        ip_future = executor.submit(get_ip)
        location_future = executor.submit(get_location)

        print(f"Speed: {speed_future.result()}")
        print(f"IP: {ip_future.result()}")
        print(f"Location: {location_future.result()}")


if __name__ == "__main__":
    main()
