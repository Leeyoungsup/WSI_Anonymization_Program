Option Explicit
Dim shell, fso, root, python, quote
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
python = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.conda\envs\yslee\pythonw.exe"
quote = Chr(34)
If Not fso.FileExists(python) Then
    MsgBox "yslee Python was not found. See README.md for setup.", 16, "WSI Anonymization"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run quote & python & quote & " " & quote & root & "\app.py" & quote, 1, False
