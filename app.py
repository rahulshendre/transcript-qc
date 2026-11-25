"""Start the review screen: python app.py

Opens the page in your browser. Everything runs on this computer.
"""

from __future__ import annotations

import argparse
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn

from transcript_qc.web.app import create_app, default_home


def free_port(start: int, host: str = "127.0.0.1") -> int:
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex((host, port)) != 0:
                return port
    raise SystemExit(f"No free port found from {start} to {start + 29}.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Transcript QC review screen")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--sessions-dir", type=Path, help="where reviews are saved")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    port = free_port(args.port, args.host)
    home = args.sessions_dir or default_home() / "sessions"
    url = f"http://{args.host}:{port}"
    print(f"Transcript QC is running at {url}  (reviews are saved in {home})", flush=True)
    print("Press Ctrl+C or close this window to stop.", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(home), host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
