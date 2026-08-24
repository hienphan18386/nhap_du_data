tell application "Google Chrome"
    repeat with w in windows
        repeat with tabNumber from (count of tabs of w) to 1 by -1
            set t to tab tabNumber of w
            try
                set tabName to execute t javascript "window.name"
                if tabName starts with "codex-medinet-worker-" then close t
            end try
        end repeat
    end repeat
end tell
