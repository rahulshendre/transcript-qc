"""Entry point of the packaged app (the Windows installer).

Starts the review screen the same way as `python app.py`. The app runs in a small console
window: closing that window stops it. If the app fails to start, the window stays open
with the reason instead of vanishing before anyone can read it.
"""

from __future__ import annotations

import sys
import traceback

from app import main as run_app


def main() -> None:
    try:
        run_app([])
    except KeyboardInterrupt:
        pass
    except BaseException as error:  # noqa: BLE001 (show any failure before the window closes)
        if isinstance(error, SystemExit) and not error.code:
            return
        traceback.print_exc()
        print("\nTranscript QC could not start. Send a photo of this window to the developer.")
        input("Press Enter to close.")
        sys.exit(1)


if __name__ == "__main__":
    main()
