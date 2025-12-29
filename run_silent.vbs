Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """" & "pythonw.exe" & """ """ & "C:\vd-speed-test\speed_collector.py" & """", 0, False
