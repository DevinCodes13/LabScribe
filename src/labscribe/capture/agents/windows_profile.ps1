# ============================================================
# LabScribe capture agent — Windows VM (DC01, WKS01)
# ============================================================
# Records every PowerShell session (commands + output) into the
# LabScribe shared folder using Start-Transcript. Nothing outside
# the terminal is ever recorded.
#
# ONE-TIME INSTALL (inside the VM):
#   1. In VirtualBox, add the shared folder (Devices > Shared
#      Folders) and note its UNC path, e.g. \\VBOXSVR\LabCapture
#   2. In PowerShell:  notepad $PROFILE
#      (say Yes if it asks to create the file)
#   3. Paste this whole snippet, adjust $LabScribeShare if your
#      share path differs, save, open a new PowerShell window.
# ============================================================

$LabScribeShare = "{{WIN_CAPTURE_PATH}}\transcripts"

if (Test-Path $LabScribeShare) {
    $stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
    $file = Join-Path $LabScribeShare "${stamp}_$($env:COMPUTERNAME).txt"
    try {
        Start-Transcript -Path $file -Append | Out-Null
        Write-Host "[LabScribe] transcript -> $file" -ForegroundColor DarkGreen
    } catch {
        # Never block the shell just because recording failed
        Write-Host "[LabScribe] transcript failed to start: $_" -ForegroundColor DarkYellow
    }
} else {
    Write-Host "[LabScribe] shared folder not reachable - session NOT recorded" -ForegroundColor DarkYellow
}
