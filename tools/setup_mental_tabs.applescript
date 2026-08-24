tell application "Google Chrome"
    if (count of windows) is 0 then make new window
    tell window 1
        repeat with workerNumber from 1 to 6
            set workerTab to make new tab at end of tabs with properties {URL:"https://quanlyskcd.medinet.org.vn/"}
            delay 2
            execute workerTab javascript "window.name='codex-medinet-worker-" & workerNumber & "'; true"
        end repeat
    end tell
end tell
