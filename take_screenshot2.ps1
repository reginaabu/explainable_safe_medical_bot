Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
}
"@
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

# Open a fresh tab at localhost:8501
Start-Process "chrome.exe" "--new-tab http://localhost:8501"
Start-Sleep -Seconds 4

# Find the Medical Evidence window
$win = Get-Process chrome | Where-Object { $_.MainWindowTitle -match "Medical Evidence" } | Select-Object -First 1
if ($win) {
    [Win32]::ShowWindow($win.MainWindowHandle, 3)
    [Win32]::SetForegroundWindow($win.MainWindowHandle)
    Start-Sleep -Seconds 2
    # Ctrl+Home
    [Win32]::keybd_event(0x11, 0, 0, 0)
    [Win32]::keybd_event(0x24, 0, 0, 0)
    [Win32]::keybd_event(0x24, 0, 2, 0)
    [Win32]::keybd_event(0x11, 0, 2, 0)
    Start-Sleep -Seconds 1
}

$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp    = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$g      = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$bmp.Save("C:/Regina/Upgrad/Project/track1-medical-retrieval-bm25/screenshot_top.png")
$g.Dispose(); $bmp.Dispose()
Write-Host "Done."
