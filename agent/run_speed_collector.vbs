Option Explicit

Dim fso, WshShell, cmd, rc, logFile, ts
Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

logFile = "C:\vd-speed-test\logs\vbs_heartbeat.log"

' Log start
Set ts = fso.OpenTextFile(logFile, 8, True)
ts.WriteLine Now & " : VBS started"
ts.Close

' Run python with logging (hidden) - Python handles its own lock file
cmd = "cmd.exe /c " & _
      """" & _
      """" & "C:\vd-speed-test\.venv\Scripts\python.exe" & """" & _
      " " & """" & "C:\vd-speed-test\agent\speed_collector.py" & """" & _
      " >> ""C:\vd-speed-test\logs\collector.log"" 2>&1" & _
      """"

rc = WshShell.Run(cmd, 0, True)

' Log finish
Set ts = fso.OpenTextFile(logFile, 8, True)
ts.WriteLine Now & " : VBS finished (rc=" & rc & ")"
ts.Close

WScript.Quit rc
