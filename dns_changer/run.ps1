# Run DNS Changer as Administrator
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
    # Relaunch as admin
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$scriptDir'; python main.py; Read-Host 'Press Enter to exit...'`"" -Verb RunAs
}
