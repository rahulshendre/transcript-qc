import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from app import free_port

ROOT = Path(__file__).resolve().parent.parent


def test_free_port_skips_a_port_that_is_taken():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        assert free_port(taken) != taken


def test_python_app_py_starts_the_review_screen(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "app.py"), "--no-browser", "--port", str(port),
         "--sessions-dir", str(tmp_path / "s")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        page = None
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as reply:
                    page = reply.read().decode("utf-8")
                break
            except OSError:
                time.sleep(0.1)
        assert page is not None, "the app did not start"
        assert "<title>Transcript QC</title>" in page          # the built screen is served
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as reply:
            assert b'"ok":true' in reply.read().replace(b" ", b"")
    finally:
        process.terminate()
        output = process.communicate(timeout=10)[0]
    assert "Transcript QC is running at" in output


def test_the_built_page_ships_with_the_package():
    static = ROOT / "transcript_qc" / "web" / "static"
    assert (static / "index.html").is_file()
    fonts = list((static / "assets").glob("noto-sans-devanagari-devanagari-*.woff2"))
    assert len(fonts) >= 3
    html = (static / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html   # nothing is fetched from the internet
    for script in (static / "assets").glob("*.js"):
        assert "fonts.googleapis" not in script.read_text(encoding="utf-8")
