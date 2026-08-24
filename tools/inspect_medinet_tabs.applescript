set reportText to ""
tell application "Google Chrome"
    repeat with windowNumber from 1 to (count of windows)
        set w to window windowNumber
        repeat with tabNumber from 1 to (count of tabs of w)
            set t to tab tabNumber of w
            set tabURL to URL of t
            if tabURL contains "medinet.org.vn" then
                set pageKind to "app"
                if tabURL contains "/Ui/Login" then set pageKind to "login"
                set tabName to ""
                try
                    set tabName to execute t javascript "window.name"
                end try
                set reportText to reportText & windowNumber & ":" & tabNumber & "|" & pageKind & "|" & tabName & linefeed
            end if
        end repeat
    end repeat
end tell
return reportText
