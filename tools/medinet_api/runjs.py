"""Run a JS file in the signed-in Medinet tab and print the result."""
import subprocess, sys, pathlib

def run_js(code: str) -> str:
    script = (
        'tell application "Google Chrome"\n'
        '  repeat with w in windows\n'
        '    repeat with t in tabs of w\n'
        '      if URL of t contains "medinet" then\n'
        '        return execute t javascript ' + as_str(code) + '\n'
        '      end if\n'
        '    end repeat\n'
        '  end repeat\n'
        '  return "__no_tab__"\n'
        'end tell\n')
    p = subprocess.run(["osascript", "-"], input=script, capture_output=True, text=True)
    if p.stderr.strip():
        return "ERR: " + p.stderr.strip()
    return p.stdout.strip()

def as_str(v: str) -> str:
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

if __name__ == "__main__":
    print(run_js(pathlib.Path(sys.argv[1]).read_text()))
