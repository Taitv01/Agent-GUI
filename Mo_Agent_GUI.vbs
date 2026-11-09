Option Explicit
Dim fso, shell, baseDir, pyw, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = baseDir
pyw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe")
If Not fso.FileExists(pyw) Then
    pyw = "pythonw.exe"
End If
cmd = """" & pyw & """ -X utf8 -m automation.review_loop.gui"
shell.Run cmd, 1, False
