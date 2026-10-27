' Chay Dynamic Island khong hien cua so den.
' Thu tu tim Python: .venv -> python-path.txt -> pythonw trong PATH
Option Explicit
Dim fso, sh, base, pyw, script, txt, f

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
script = base & "\main.py"

pyw = base & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pyw) Then
    txt = base & "\python-path.txt"
    If fso.FileExists(txt) Then
        Set f = fso.OpenTextFile(txt, 1)
        Do While Not f.AtEndOfStream
            pyw = Trim(f.ReadLine())
            ' Bỏ qua dòng trống và dòng comment
            If Len(pyw) > 0 And Left(pyw, 1) <> "#" Then
                Exit Do
            End If
        Loop
        f.Close
    End If
End If

If Not fso.FileExists(pyw) Then
    pyw = "pythonw.exe"
End If

sh.CurrentDirectory = base
sh.Run """" & pyw & """ """ & script & """", 0, False
