<#
  Registers a Windows Scheduled Task that runs the uploader silently in the
  background every time you log in. Run this once from an elevated or
  regular PowerShell prompt:

      .\register_startup_task.ps1

  To remove it later:
      Unregister-ScheduledTask -TaskName "ScreenshotUploader" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)
if (-not $pythonw) {
    $pythonw = (Get-Command python.exe -ErrorAction Stop)
    Write-Warning "pythonw.exe not found; falling back to python.exe (a console window will briefly flash on login)."
}

$action = New-ScheduledTaskAction -Execute $pythonw.Source -Argument "`"$scriptDir\uploader.py`"" -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "ScreenshotUploader" -Action $action -Trigger $trigger -Settings $settings -Description "Uploads the latest Windows screenshot to the cloud server" -Force

Write-Output "Scheduled task 'ScreenshotUploader' registered. It will start automatically on your next login."
Write-Output "To start it right now without logging out, run: Start-ScheduledTask -TaskName ScreenshotUploader"
