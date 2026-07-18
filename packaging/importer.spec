# PyInstaller spec -- build with:  pyinstaller packaging/importer.spec
# Run from the repo root so the relative paths below resolve.
#
# Produces a single self-contained executable (medinet-importer[.exe]) with the
# Python runtime, Playwright and a full Firefox baked in -- nothing to install on
# the target machine. Build it once per OS (PyInstaller cannot cross-compile);
# see .github/workflows/build.yml for the Windows/macOS/Linux matrix.

import os
import shutil

import playwright

# Paths in a spec resolve against the spec's own folder (SPECPATH), not the CWD.
# Everything below is relative to the repo root, one level up.
ROOT = os.path.dirname(SPECPATH)

# PyInstaller's bundled playwright hook collects the whole package including the
# browsers on its own, so we start empty and strip the browsers back out after
# Analysis (see below) rather than trying to out-vote that hook here.
datas = []
binaries = []
hiddenimports = []

# Ship the whole browser as one .tar.gz. tar preserves the executable bits and
# the symlinks inside Firefox's .app that a plain file copy (or zip) would lose,
# and keeping it as an opaque archive avoids PyInstaller's dylib rpath rewrite
# (which fails on Firefox's .dylibs). The runtime hook unpacks it on first launch.
pw_root = os.path.dirname(playwright.__file__)
browsers_root = os.path.join(pw_root, "driver", "package", ".local-browsers")
assets_dir = os.path.join(ROOT, "build", "assets")
os.makedirs(assets_dir, exist_ok=True)
archive = shutil.make_archive(
    os.path.join(assets_dir, "pw-browsers"), "gztar", root_dir=browsers_root
)
datas.append((archive, "."))  # -> pw-browsers.tar.gz at the bundle root

# The sample list, seeded next to the executable on first run (see load_records()).
datas.append((os.path.join(ROOT, "app", "data", "children.json"), "data"))

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "app", "importer.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[os.path.join(ROOT, "packaging", "pyi_rth_playwright.py")],
    excludes=[],
    cipher=block_cipher,
)

# Drop the raw browser tree the bundled playwright hook pulled in. PyInstaller
# would otherwise try to rewrite the rpaths of Firefox's .dylibs and fail. The
# browser reaches the app through pw-browsers.tar.gz instead (added above).
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
    [],
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
