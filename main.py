import os
import sys
import math
import re
import time
from urllib.parse import unquote, urlparse

import requests

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ============================================================
# CONFIG
# ============================================================

DEFAULT_CHUNK_MB = 250

CLIENT_SECRET_FILE = "client_secret.json" #client_secret.json from google 
TOKEN_FILE = "token.json"

DRIVE_FOLDER_ID = "YOUR_FOLDER_ID"

SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

TEMP_DIR = "temp_parts"

DOWNLOAD_BUFFER = 8 * 1024 * 1024

MAX_RETRIES = 5
RETRY_DELAY = 5

USER_AGENT = "Mozilla/5.0"


# ============================================================
# GOOGLE DRIVE AUTH
# ============================================================

def get_drive_service():
    credentials = None

    if os.path.exists(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if credentials and credentials.expired and credentials.refresh_token:
        print("Refreshing Google authorization...")
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        print()
        print("Opening Google authorization...")

        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRET_FILE,
            SCOPES
        )

        credentials = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(credentials.to_json())

        print("Google authorization saved.")

    return build(
        "drive",
        "v3",
        credentials=credentials
    )


# ============================================================
# FILE NAME
# ============================================================

def get_filename(response, url):
    disposition = response.headers.get(
        "content-disposition",
        ""
    )

    match = re.search(
        r"filename\*=UTF-8''([^;]+)",
        disposition,
        re.IGNORECASE
    )

    if match:
        return unquote(match.group(1).strip('"'))

    match = re.search(
        r'filename="([^"]+)"',
        disposition,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    match = re.search(
        r"filename=([^;]+)",
        disposition,
        re.IGNORECASE
    )

    if match:
        return unquote(match.group(1).strip())

    # Fallback to the URL path.
    path = urlparse(response.url or url).path
    name = unquote(os.path.basename(path))

    if name:
        return name

    return "downloaded_file"


# ============================================================
# SIZE HELPERS
# ============================================================

def get_header_size(headers):
    for key in (
        "content-length",
        "x-estimated-content-length",
        "estimated-content-length"
    ):
        value = headers.get(key)

        if value:
            try:
                value = int(value)
                if value > 0:
                    return value
            except ValueError:
                pass

    return None


# ============================================================
# VERIFY REAL RANGE SUPPORT
# ============================================================

def verify_range_support(url, file_size):
    """
    Do not trust Accept-Ranges alone.

    We send a 1-byte Range request and require HTTP 206 plus
    a valid Content-Range header.
    """

    if not file_size:
        return False

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Range": "bytes=0-0"
            },
            stream=True,
            allow_redirects=True,
            timeout=(30, 60)
        )

        if response.status_code != 206:
            response.close()
            return False

        content_range = response.headers.get(
            "content-range",
            ""
        ).lower()

        # Expected form: bytes 0-0/TOTAL
        if not content_range.startswith("bytes 0-0/"):
            response.close()
            return False

        response.close()
        return True

    except requests.RequestException:
        return False


# ============================================================
# SOURCE INFORMATION
# ============================================================

def get_source_info(url):
    print()
    print("Checking source...")

    file_size = None
    filename = "downloaded_file"

    # --------------------------------------------------------
    # HEAD
    # --------------------------------------------------------

    try:
        response = requests.head(
            url,
            allow_redirects=True,
            timeout=(15, 30),
            headers={
                "User-Agent": USER_AGENT
            }
        )

        if response.ok:
            file_size = get_header_size(response.headers)
            filename = get_filename(response, url)

    except requests.RequestException:
        print("HEAD request unavailable.")

    # --------------------------------------------------------
    # GET headers if HEAD was incomplete
    # --------------------------------------------------------

    if file_size is None or filename == "downloaded_file":

        print("Trying normal GET request...")

        try:
            response = requests.get(
                url,
                stream=True,
                allow_redirects=True,
                timeout=(30, 60),
                headers={
                    "User-Agent": USER_AGENT
                }
            )

            response.raise_for_status()

            if file_size is None:
                file_size = get_header_size(response.headers)

            filename = get_filename(response, url)

            response.close()

        except requests.RequestException as error:
            raise RuntimeError(
                f"Source cannot be accessed: {error}"
            )

    # --------------------------------------------------------
    # REAL Range test
    # --------------------------------------------------------

    range_supported = False

    if file_size:
        print("Testing actual HTTP Range support...")

        range_supported = verify_range_support(
            url,
            file_size
        )

    return file_size, range_supported, filename


# ============================================================
# GOOGLE DRIVE UPLOAD
# ============================================================

def upload_to_drive(drive, filepath, drive_name):
    metadata = {
        "name": drive_name,
        "parents": [DRIVE_FOLDER_ID]
    }

    media = MediaFileUpload(
        filepath,
        mimetype="application/octet-stream",
        resumable=True,
        chunksize=8 * 1024 * 1024
    )

    for attempt in range(1, 4):
        try:
            request = drive.files().create(
                body=metadata,
                media_body=media,
                fields="id,name,size"
            )

            response = None

            while response is None:
                status, response = request.next_chunk()

                if status:
                    percent = int(
                        status.progress() * 100
                    )

                    print(
                        f"\rUploading {drive_name}: "
                        f"{percent}%",
                        end="",
                        flush=True
                    )

            print()
            print(f"✓ Uploaded {drive_name}")

            return response

        except Exception as error:
            print()
            print(
                f"Upload failed "
                f"(attempt {attempt}/3): {error}"
            )

            if attempt == 3:
                raise

            time.sleep(3)


# ============================================================
# COMMON PART UPLOAD
# ============================================================

def upload_part_file(
    drive,
    filepath,
    filename,
    part_number
):
    drive_name = (
        f"{filename}.part{part_number:03d}"
    )

    print()
    print(
        f"Uploading {drive_name} "
        f"({os.path.getsize(filepath) / 1024 / 1024:.2f} MB)..."
    )

    result = upload_to_drive(
        drive,
        filepath,
        drive_name
    )

    try:
        os.remove(filepath)
    except OSError:
        pass

    return result


# ============================================================
# RANGE DOWNLOAD
# ============================================================

def download_range_part(
    url,
    start,
    end,
    filepath
):
    expected = end - start + 1

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Range": f"bytes={start}-{end}"
            }

            response = requests.get(
                url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(30, 120)
            )

            if response.status_code != 206:
                response.close()

                raise RuntimeError(
                    f"Range request returned HTTP "
                    f"{response.status_code}, expected 206."
                )

            content_range = response.headers.get(
                "content-range",
                ""
            )

            expected_prefix = f"bytes {start}-{end}/"

            if not content_range.startswith(
                expected_prefix
            ):
                response.close()

                raise RuntimeError(
                    "Invalid Content-Range received: "
                    f"{content_range}"
                )

            written = 0

            with open(filepath, "wb") as part_file:

                for data in response.iter_content(
                    chunk_size=DOWNLOAD_BUFFER
                ):
                    if not data:
                        continue

                    remaining = expected - written

                    if len(data) > remaining:
                        data = data[:remaining]

                    part_file.write(data)
                    written += len(data)

                    if written >= expected:
                        break

            response.close()

            if written != expected:
                raise ConnectionError(
                    f"Range ended early: "
                    f"{written} / {expected} bytes"
                )

            actual_size = os.path.getsize(filepath)

            if actual_size != expected:
                raise RuntimeError(
                    f"Part size mismatch: "
                    f"{actual_size} / {expected}"
                )

            return

        except Exception as error:

            print()
            print(
                f"Range part {start}-{end} failed "
                f"(attempt {attempt}/{MAX_RETRIES}): {error}"
            )

            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError:
                pass

            if attempt == MAX_RETRIES:
                raise

            time.sleep(RETRY_DELAY)


# ============================================================
# RANGE MODE
#
# Intentionally sequential for stability.
# This avoids the previous multi-threaded download/upload
# segfault while preserving the important Range capability.
# ============================================================

def range_download_and_upload(
    url,
    filename,
    file_size,
    chunk_size,
    drive
):
    print()
    print("==============================")
    print("MODE: RANGE")
    print("==============================")

    total_parts = math.ceil(
        file_size / chunk_size
    )

    print(f"Total parts: {total_parts}")
    print("Workers: 1 (stable mode)")

    os.makedirs(
        TEMP_DIR,
        exist_ok=True
    )

    uploaded = []
    total_saved = 0

    for part_number in range(
        1,
        total_parts + 1
    ):
        start = (
            part_number - 1
        ) * chunk_size

        end = min(
            start + chunk_size - 1,
            file_size - 1
        )

        expected = end - start + 1

        filepath = os.path.join(
            TEMP_DIR,
            f"part_{part_number:05d}"
        )

        print()
        print(
            f"Downloading part "
            f"{part_number}/{total_parts} "
            f"({expected / 1024 / 1024:.2f} MB)..."
        )

        download_range_part(
            url,
            start,
            end,
            filepath
        )

        total_saved += expected

        percent = (
            total_saved /
            file_size *
            100
        )

        print(
            f"Downloaded: "
            f"{total_saved / 1024 / 1024:.2f} MB / "
            f"{file_size / 1024 / 1024:.2f} MB "
            f"({percent:.1f}%)"
        )

        result = upload_part_file(
            drive,
            filepath,
            filename,
            part_number
        )

        uploaded.append(result)

    print()
    print(
        f"✓ Created {len(uploaded)} parts"
    )

    return uploaded


# ============================================================
# NON-RANGE STREAMING MODE
#
# If the server does not support Range, reconnecting starts
# from byte 0 and skips bytes already saved.
#
# IMPORTANT:
# "total_saved" counts ONLY bytes written to our parts.
# Re-downloaded/skipped retry bytes are NOT counted.
# ============================================================

def sequential_download_and_upload(
    url,
    filename,
    file_size,
    chunk_size,
    drive
):
    print()
    print("==============================")
    print("MODE: RESUMABLE STREAMING")
    print("==============================")

    os.makedirs(
        TEMP_DIR,
        exist_ok=True
    )

    uploaded = []

    part_number = 1

    total_saved = 0

    # --------------------------------------------------------
    # Resume any existing complete/partial parts
    # --------------------------------------------------------

    while True:

        filepath = os.path.join(
            TEMP_DIR,
            f"part_{part_number:05d}"
        )

        if not os.path.exists(filepath):
            break

        size = os.path.getsize(filepath)

        if size < chunk_size:
            break

        # Complete local part from previous run.
        result = upload_part_file(
            drive,
            filepath,
            filename,
            part_number
        )

        uploaded.append(result)

        total_saved += size
        part_number += 1

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    while True:

        filepath = os.path.join(
            TEMP_DIR,
            f"part_{part_number:05d}"
        )

        current_size = (
            os.path.getsize(filepath)
            if os.path.exists(filepath)
            else 0
        )

        if file_size and total_saved + current_size >= file_size:
            break

        retry_count = 0

        while True:

            try:
                # Position in the ORIGINAL source.
                source_position = (
                    total_saved + current_size
                )

                print()
                print(
                    f"Part {part_number}: "
                    f"{current_size / 1024 / 1024:.2f} MB / "
                    f"{min(chunk_size, max(0, file_size - total_saved)) / 1024 / 1024:.2f} MB"
                    if file_size
                    else
                    f"Part {part_number}: "
                    f"{current_size / 1024 / 1024:.2f} MB / "
                    f"{chunk_size / 1024 / 1024:.2f} MB"
                )

                print(
                    f"Connecting to source "
                    f"from byte {source_position:,}..."
                )

                response = requests.get(
                    url,
                    stream=True,
                    allow_redirects=True,
                    timeout=(30, 120),
                    headers={
                        "User-Agent": USER_AGENT
                    }
                )

                response.raise_for_status()

                bytes_to_skip = source_position
                reached_eof = True

                with open(
                    filepath,
                    "ab"
                ) as part_file:

                    for data in response.iter_content(
                        chunk_size=DOWNLOAD_BUFFER
                    ):

                        if not data:
                            continue

                        # ------------------------------------------------
                        # Discard bytes already saved.
                        #
                        # These bytes are network traffic, but they are
                        # NOT counted as new file progress.
                        # ------------------------------------------------

                        if bytes_to_skip > 0:

                            if len(data) <= bytes_to_skip:
                                bytes_to_skip -= len(data)
                                continue

                            data = data[
                                bytes_to_skip:
                            ]

                            bytes_to_skip = 0

                        if not data:
                            continue

                        # ------------------------------------------------
                        # Only write enough to fill this part.
                        # ------------------------------------------------

                        remaining = (
                            chunk_size -
                            current_size
                        )

                        piece = data[:remaining]

                        part_file.write(piece)
                        part_file.flush()

                        current_size += len(piece)

                        total_position = (
                            total_saved +
                            current_size
                        )

                        if file_size:
                            percent = min(
                                100,
                                total_position /
                                file_size *
                                100
                            )

                            print(
                                f"\rTotal saved: "
                                f"{total_position / 1024 / 1024:.2f} MB / "
                                f"{file_size / 1024 / 1024:.2f} MB "
                                f"({percent:.1f}%)",
                                end="",
                                flush=True
                            )

                        # Part full.
                        if current_size >= chunk_size:
                            reached_eof = False
                            break

                        # If data crossed the part boundary,
                        # the remainder is intentionally not written.
                        # On the next connection it will be skipped
                        # from the original source position.
                        if len(data) > len(piece):
                            reached_eof = False
                            break

                response.close()

                # ------------------------------------------------
                # Part is complete.
                # ------------------------------------------------

                if current_size >= chunk_size:

                    print()

                    result = upload_part_file(
                        drive,
                        filepath,
                        filename,
                        part_number
                    )

                    uploaded.append(result)

                    total_saved += current_size
                    part_number += 1

                    break

                # ------------------------------------------------
                # Entire source finished.
                # ------------------------------------------------

                if file_size:

                    if (
                        total_saved +
                        current_size
                    ) >= file_size:

                        print()

                        result = upload_part_file(
                            drive,
                            filepath,
                            filename,
                            part_number
                        )

                        uploaded.append(result)

                        total_saved += current_size

                        return uploaded

                else:
                    # Unknown source size:
                    # a cleanly ended response means EOF.
                    print()

                    result = upload_part_file(
                        drive,
                        filepath,
                        filename,
                        part_number
                    )

                    uploaded.append(result)

                    return uploaded

                # If the server closed before the expected amount,
                # retry from the beginning and skip saved bytes.
                raise ConnectionError(
                    "Source connection ended before "
                    "the expected file size."
                )

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ReadTimeout,
                requests.exceptions.Timeout,
                ConnectionError
            ) as error:

                retry_count += 1

                # Always trust the file on disk.
                current_size = (
                    os.path.getsize(filepath)
                    if os.path.exists(filepath)
                    else 0
                )

                print()
                print(
                    f"Connection interrupted: {error}"
                )

                print(
                    f"Saved data preserved: "
                    f"{(total_saved + current_size) / 1024 / 1024:.2f} MB"
                )

                if retry_count >= MAX_RETRIES:
                    raise RuntimeError(
                        f"Maximum retries reached. "
                        f"Partial part remains at {filepath}"
                    ) from error

                print(
                    f"Retry "
                    f"{retry_count}/{MAX_RETRIES} "
                    f"in {RETRY_DELAY} seconds..."
                )

                time.sleep(RETRY_DELAY)

            except Exception:
                raise

    return uploaded


# ============================================================
# CLEANUP
# ============================================================

def cleanup_temp_dir():
    if not os.path.exists(TEMP_DIR):
        return

    try:
        for name in os.listdir(TEMP_DIR):
            path = os.path.join(
                TEMP_DIR,
                name
            )

            if os.path.isfile(path):
                os.remove(path)

        os.rmdir(TEMP_DIR)

    except OSError:
        pass


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) < 2:
        print(
            'Usage: python now.py "DOWNLOAD_URL"'
        )
        return

    url = sys.argv[1]

    print()
    print("==============================")
    print("FILE SPLITTER")
    print("==============================")

    # --------------------------------------------------------
    # Chunk size
    # --------------------------------------------------------

    chunk_input = input(
        f"Chunk size in MB "
        f"[default {DEFAULT_CHUNK_MB}]: "
    ).strip()

    if not chunk_input:
        chunk_mb = DEFAULT_CHUNK_MB

    else:
        try:
            chunk_mb = float(chunk_input)

        except ValueError:
            print("Invalid chunk size.")
            return

    if chunk_mb < 10:
        print("Minimum chunk size is 10 MB.")
        return

    if chunk_mb > 2048:
        print("Maximum chunk size is 2048 MB.")
        return

    chunk_size = int(
        chunk_mb * 1024 * 1024
    )

    print(
        f"Using chunk size: "
        f"{chunk_mb:g} MB"
    )

    # --------------------------------------------------------
    # Google Drive
    # --------------------------------------------------------

    drive = get_drive_service()

    # --------------------------------------------------------
    # Source information
    # --------------------------------------------------------

    try:
        (
            file_size,
            range_supported,
            filename
        ) = get_source_info(url)

    except Exception as error:
        print(
            f"Could not inspect source: {error}"
        )
        return

    print()
    print(
        f"Filename: {filename}"
    )

    if file_size:
        print(
            f"Size: "
            f"{file_size / 1024 / 1024:.2f} MB"
        )

        print(
            f"Parts: "
            f"{math.ceil(file_size / chunk_size)}"
        )

    else:
        print("Size: unknown")

    print(
        f"Range support: "
        f"{'YES' if range_supported else 'NO'}"
    )

    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    if range_supported and file_size:

        uploaded = range_download_and_upload(
            url,
            filename,
            file_size,
            chunk_size,
            drive
        )

    else:

        uploaded = sequential_download_and_upload(
            url,
            filename,
            file_size,
            chunk_size,
            drive
        )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    print()
    print("==============================")
    print("COMPLETE")
    print("==============================")
    print()

    for item in uploaded:

        print(
            f"{item['name']}"
        )

        print(
            f"ID: {item['id']}"
        )

        print()

    cleanup_temp_dir()

    print(
        "All parts uploaded successfully. 🚀"
    )


if __name__ == "__main__":
    main()
