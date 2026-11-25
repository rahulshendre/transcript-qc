# Build "Transcript QC" for 64-bit Windows. Run from any folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
#
# A clean virtualenv with the tool installed, frozen with PyInstaller, then wrapped by
# Inno Setup (installer.iss) into one installer. The review screen is already built into
# transcript_qc\web\static, so Node is not needed. Needs Inno Setup 6
# (https://jrsoftware.org/isdl.php). Output: dist\Transcript QC\ (the app folder) and
# dist\Transcript-QC-Setup.exe.
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Work = Join-Path $Root "build\windows"
$Py = if ($env:PYTHON) { $env:PYTHON } else { "python" }

New-Item -ItemType Directory -Force -Path $Work | Out-Null
if (-not (Test-Path "$Work\venv\Scripts\pyinstaller.exe")) {
    & $Py -m venv "$Work\venv"
    & "$Work\venv\Scripts\python.exe" -m pip install -q --upgrade pip
}
& "$Work\venv\Scripts\python.exe" -m pip install -q "$Root" pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

& "$Work\venv\Scripts\pyinstaller.exe" --noconfirm --clean `
    --name "Transcript QC" `
    --workpath "$Work\pyi" --distpath "$Root\dist" --specpath $Work `
    --paths $Root `
    --collect-data transcript_qc `
    --collect-submodules transcript_qc `
    --collect-data docx `
    --collect-submodules uvicorn `
    "$Root\packaging\launcher.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { throw "Inno Setup 6 not found at $Iscc" }
$Version = (Select-String -Path "$Root\pyproject.toml" -Pattern '^version = "(.+)"' | Select-Object -First 1).Matches[0].Groups[1].Value
& $Iscc /Q "/DAppVersion=$Version" "/DSourceDir=$Root\dist\Transcript QC" `
    "/DOutputDir=$Root\dist" "$PSScriptRoot\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Get-Item "$Root\dist\Transcript-QC-Setup.exe" |
    Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB) } }
