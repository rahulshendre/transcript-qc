"""Check a running Transcript QC app end to end: python packaging/smoke_test.py [url]

Waits for the page, uploads the sample pair from examples/, checks the six counts and downloads
the QC document and the CSV. Used on the installed Windows app in CI; works on any running copy.
Standard library only, so it runs without the tool's own packages.
"""

from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
EXPECTED = {"Major": 5, "Language": 4, "Punctuation": 6, "CC": 3, "Repeated": 1, "Minor": 2}


def wait_for(url: str, seconds: int = 120) -> str:
    end = time.time() + seconds
    while True:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.read().decode("utf-8")
        except OSError:
            if time.time() > end:
                raise SystemExit(f"FAIL: nothing answered at {url} in {seconds} s") from None
            time.sleep(2)


def upload(url: str) -> dict:
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for field, name in (("file_a", "sample_A.docx"), ("file_b", "sample_B.docx")):
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
                f"filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n")
        body.write(head.encode())
        body.write((EXAMPLES / name).read_bytes())
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        f"{url}/api/sessions", data=body.getvalue(), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main(argv: list[str]) -> None:
    url = (argv[0] if argv else "http://127.0.0.1:8765").rstrip("/")
    page = wait_for(url + "/")
    if "<div id=\"root\">" not in page:
        raise SystemExit("FAIL: the page is not the review screen")
    print("page served")

    state = upload(url)
    if state["counts"] != EXPECTED:
        raise SystemExit(f"FAIL: counts {state['counts']} != {EXPECTED}")
    print(f"sample counts match: {state['counts']}")

    docx = download(f"{url}/api/sessions/{state['id']}/export/docx?force=true")
    with zipfile.ZipFile(io.BytesIO(docx)) as package:
        xml = package.read("word/document.xml").decode("utf-8")
    if "<w:ins " not in xml or "<w:del " not in xml:
        raise SystemExit("FAIL: the QC document has no tracked changes")
    print(f"QC document exported ({len(docx)} bytes, tracked changes present)")

    csv_bytes = download(f"{url}/api/sessions/{state['id']}/export/csv?force=true")
    csv_text = csv_bytes.decode("utf-8-sig")
    rows = csv_text.strip().splitlines()
    print(f"CSV exported ({len(rows) - 1} rows)")
    print("OK")


if __name__ == "__main__":
    main(sys.argv[1:])
