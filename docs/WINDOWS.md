# Windows

Two ways to run the tool on a Windows laptop: the installer (nothing else to install) or from the
source with Python, as the brief asks (`python app.py`).

## Installer

`Transcript-QC-Setup.exe`, 64-bit Windows 10 or 11. No admin password and no internet needed.

**Install**

1. Double-click `Transcript-QC-Setup.exe`.
2. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**. The app is
   not signed, so Windows shows this once.
3. Click through the installer. Tick "Create a desktop shortcut" if you want one. It opens the app at
   the end.

**Use**

1. Open **Transcript QC** from the Start menu or the desktop shortcut. A small black window opens,
   and the review screen opens in the browser (Chrome or Edge).
2. Keep the black window open while you work. Closing it stops the app.
3. Choose File A (the transcript being scored) and File B (the reference), check the movie, writer
   and episode, and click **Compare**. Then review as in [REVIEW_UI.md](REVIEW_UI.md).
4. **Export QC .docx** and **Export CSV** save into the browser's Downloads folder.

Reviews are saved as you go in `C:\Users\<you>\Transcript QC\sessions`. Opening the same two files
again brings the review back where it stopped.

If the app cannot start, the black window stays open with the reason. Send a photo of it.

**Uninstall:** Settings > Apps > Installed apps > Transcript QC > Uninstall. Saved reviews in
`C:\Users\<you>\Transcript QC` are kept.

## From the source

Python 3.11 or newer from python.org (tick "Add python.exe to PATH").

```
py -3.11 -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python app.py
```

The command-line comparison works the same way:

```
.venv\Scripts\python qc_compare.py --a examples\sample_A.docx --b examples\sample_B.docx --out out\sample_QC.docx
```

If the QC .docx or CSV is open in Word or Excel, Windows will not let the tool replace it. The tool
says so; close the file and run again.

## Building the installer

Needs Python 3.11+ and [Inno Setup 6](https://jrsoftware.org/isdl.php).

```
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

This makes a clean virtualenv, freezes the app with PyInstaller (`packaging/launcher.py`) and wraps
it with Inno Setup (`packaging/windows/installer.iss`). Output: `dist\Transcript-QC-Setup.exe`. The
review screen is already built into the package, so Node is not needed.

## What is checked on Windows

Development happens on a Mac, so Windows is checked by GitHub Actions (`.github/workflows/ci.yml`)
on every push:

* **Tests** on `windows-latest` with Python 3.11: the full suite, including the review-screen tests
  that drive a real Chrome. The tests that need the Episode 50 files skip, because those files are
  not in the repo.
* **Installer:** builds `Transcript-QC-Setup.exe`, installs it silently, starts the installed app and
  runs `packaging/smoke_test.py` against it: the sample pair is uploaded, the six counts must match,
  and the QC .docx and CSV must download. The installer is attached to the run.

Not yet checked: a real reviewer's laptop, and opening the QC .docx in Word.
