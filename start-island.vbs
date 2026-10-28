' Chay Dynamic Island khong hien cua so den.
' Thu tu tim Python:
'   1) .venv cua repo        2) python-path.txt
'   3) py launcher (-3)      4) pythonw.exe trong PATH
Option Explicit

Dim fso, sh, base, script, pyw, txt, f, line, probe

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
script = base & "\main.py"

If Not fso.FileExists(script) Then
    MsgBox "Khong tim thay main.py trong:" & vbCrLf & base, 16, "Dynamic Island"
    WScript.Quit 1
End If

pyw = ""

' 1) Moi truong rieng cua repo (uu tien)
If pyw = "" Then
    If fso.FileExists(base & "\.venv\Scripts\pythonw.exe") Then
        pyw = """" & base & "\.venv\Scripts\pythonw.exe" & """"
    End If
End If

' 2) Duong dan tu ghi trong python-path.txt (bo qua dong trong va dong #)
If pyw = "" Then
    txt = base & "\python-path.txt"
    If fso.FileExists(txt) Then
        Set f = fso.OpenTextFile(txt, 1)
        Do While Not f.AtEndOfStream
            line = Trim(f.ReadLine())
            If Len(line) > 0 And Left(line, 1) <> "#" Then
                If fso.FileExists(line) Then
                    pyw = """" & line & """"
                End If
                Exit Do
            End If
        Loop
        f.Close
    End If
End If

' 3) py launcher (cai chung voi Python tu python.org)
If pyw = "" Then
    On Error Resume Next
    probe = -1
    probe = sh.Run("pyw.exe -3 -c ""import sys""", 0, True)
    If Err.Number = 0 And probe = 0 Then
        pyw = "pyw.exe -3"
    End If
    Err.Clear
    On Error GoTo 0
End If

' 4) pythonw.exe co san trong PATH
If pyw = "" Then
    On Error Resume Next
    probe = -1
    probe = sh.Run("pythonw.exe -c ""import sys""", 0, True)
    If Err.Number = 0 And probe = 0 Then
        pyw = "pythonw.exe"
    End If
    Err.Clear
    On Error GoTo 0
End If

If pyw = "" Then
    MsgBox "Khong tim thay Python." & vbCrLf & vbCrLf & _
           "Hay chay setup.bat mot lan de tao moi truong, " & _
           "hoac cai Python 3.11+ tu python.org.", 16, "Dynamic Island"
    WScript.Quit 1
End If

sh.CurrentDirectory = base
sh.Run pyw & " """ & script & """", 0, False
