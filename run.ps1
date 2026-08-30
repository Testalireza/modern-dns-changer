# Run Modern DNS Changer as Administrator
# Right-click this file > "Run with PowerShell"
# or double-click run.ps1 (may need to enable script execution)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    python main.py
    Read-Host "Press Enter to exit..."
} else {
    # Relaunch as admin.  Passing the command as an array of separate
    # arguments (rather than one giant quoted string) keeps paths containing
    # spaces and non-ASCII characters intact.
    try {
        $cmd = "cd '$scriptDir'; python main.py; Read-Host 'Press Enter to exit...'"
        $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cmd)
        $proc = Start-Process powershell -ArgumentList $argList -Verb RunAs -PassThru -ErrorAction Stop
    } catch {
        Write-Host "Failed to relaunch as Administrator: $_" -ForegroundColor Red
        Read-Host "Press Enter to exit..."
        exit 1
    }
}
