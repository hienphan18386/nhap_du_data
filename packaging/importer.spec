# PyInstaller spec -- build with:  pyinstaller packaging/importer.spec
# Run from the repo root so the relative paths below resolve.
#
# Produces a single self-contained executable (medinet-importer[.exe]) with the
# Python runtime and Playwright's node driver inside. It drives the user's own
# installed Chrome or Firefox, so NO browser binary is bundled -- the executable
# stays small. Build once per OS (PyInstaller cannot cross-compile); see
# .github/workflows/build.yml for the Windows/macOS/Linux matrix.

import glob
import os

import playwright

# Paths in a spec resolve against the spec's own folder (SPECPATH), not the CWD.
ROOT = os.path.dirname(SPECPATH)

# Start empty; PyInstaller's bundled playwright hook collects the package (its
# node driver included) during Analysis.
datas = []
binaries = []
hiddenimports = []

# The bundled hook misses the node driver's package.json files, so the driver dies
# with "Cannot find module './../../package.json'" when it reads its own version.
# Add every package.json under the driver (skipping the browsers we do not ship).
pw_root = os.path.dirname(playwright.__file__)
for pj in glob.glob(os.path.join(pw_root, "driver", "**", "package.json"), recursive=True):
    if ".local-browsers" in pj.replace("\\", "/"):
        continue
    datas.append((pj, os.path.join("playwright", os.path.relpath(os.path.dirname(pj), pw_root))))

# Optional sample list, seeded next to the executable on first run (see load_records()).
# Local real data is intentionally gitignored, so CI builds must not require it.
sample_children = os.path.join(ROOT, "app", "data", "children.json")
if os.path.exists(sample_children):
    datas.append((sample_children, "data"))

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "app", "importer.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

# Safety net: if a Playwright browser was ever installed into the package, drop it.
# We never drive a bundled browser, and PyInstaller chokes trying to rewrite the
# rpaths of Firefox's .dylibs ("load commands do not fit").
def _no_browsers(entry):
    return ".local-browsers" not in entry[0].replace("\\", "/")

a.binaries = TOC([e for e in a.binaries if _no_browsers(e)])
a.datas = TOC([e for e in a.datas if _no_browsers(e)])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    # 'u' = unbuffered stdio. The frozen bootloader ignores PYTHONUNBUFFERED, and
    # with buffered stdio the user sees no output at all (even the "please log in"
    # prompt), which reads as the app not launching.
    [("u", None, "OPTION")],
    name="medinet-importer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
