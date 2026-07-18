# PyInstaller runtime hook: runs before the app's own code.
#
# The bundled Firefox rides along as pw-browsers.tar.gz (see importer.spec, which
# cannot hand the raw browser to PyInstaller without its .dylib rpath rewrite
# failing). Here we unpack it once, next to the executable, and point Playwright
# at it via PLAYWRIGHT_BROWSERS_PATH -- so the machine needs nothing installed.
import os
import sys


def _prepare_browsers():
    if not getattr(sys, "frozen", False):
        return  # running from source: use the normal per-user Playwright cache

    archive = os.path.join(sys._MEIPASS, "pw-browsers.tar.gz")
    if not os.path.exists(archive):
        return

    # A persistent cache beside the executable, so the ~200 MB unpack happens
    # only on the first run, not every launch.
    target = os.path.join(os.path.dirname(sys.executable), "browser-cache")
    done_marker = os.path.join(target, ".unpacked")

    if not os.path.exists(done_marker):
        import tarfile

        print("First run: unpacking the bundled Firefox (one time only)...")
        os.makedirs(target, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(target)  # tar restores exec bits and symlinks
        with open(done_marker, "w") as f:
            f.write("ok")

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = target


_prepare_browsers()
