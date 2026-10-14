# Disable selected startup apps (same as Task Manager > Startup apps > Disable).
# Backs up the relevant registry keys first. Nothing is uninstalled or deleted.
# Run in Terminal (Admin):
#   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\OneDrive\Documents\UBC MCP\disable_startup_apps.ps1"

$targets = @('Docker Desktop','Lunar Client','LGHUB','iTunesHelper','MicrosoftEdgeAutoLaunch','Discord','GoogleDriveFS')

# --- 1. Backup -------------------------------------------------------------
$bk = "$env:USERPROFILE\OneDrive\Documents\UBC MCP\startup-backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Force -Path $bk | Out-Null
$keys = @{
  'HKCU_StartupApproved' = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved'
  'HKLM_StartupApproved' = 'HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved'
  'HKCU_Run'             = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Run'
  'HKLM_Run'             = 'HKLM\Software\Microsoft\Windows\CurrentVersion\Run'
  'HKLM_Run32'           = 'HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'
}
foreach ($k in $keys.GetEnumerator()) { reg export $k.Value "$bk\$($k.Key).reg" /y 2>$null | Out-Null }
"Backup saved to $bk  (to undo: double-click the *_StartupApproved.reg files there, then restart)" | Write-Host

# --- 2. Disable ------------------------------------------------------------
$disabled = [byte[]](3,0,0,0,0,0,0,0,0,0,0,0)   # value Task Manager writes for 'Disabled'

function Disable-Entries($runKey, $approvedKey) {
  if (-not (Test-Path $runKey)) { return }
  $props = (Get-ItemProperty $runKey).PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' }
  foreach ($p in $props) {
    foreach ($t in $targets) {
      if ($p.Name -like "*$t*") {
        if (-not (Test-Path $approvedKey)) { New-Item -Path $approvedKey -Force | Out-Null }
        Set-ItemProperty -Path $approvedKey -Name $p.Name -Value $disabled -Type Binary
        Write-Host "Disabled: $($p.Name)"
      }
    }
  }
}

$ap = 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved'
Disable-Entries 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'             "HKCU:\$ap\Run"
Disable-Entries 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'             "HKLM:\$ap\Run"
Disable-Entries 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run' "HKLM:\$ap\Run32"

# Startup-folder shortcuts (e.g. Google Drive can live here)
foreach ($pair in @(
  @("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup", "HKCU:\$ap\StartupFolder"),
  @("$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp", "HKLM:\$ap\StartupFolder"))) {
  if (Test-Path $pair[0]) {
    Get-ChildItem $pair[0] | ForEach-Object {
      foreach ($t in $targets) {
        if ($_.Name -like "*$t*" -or ($t -eq 'GoogleDriveFS' -and $_.Name -like '*Google Drive*')) {
          if (-not (Test-Path $pair[1])) { New-Item -Path $pair[1] -Force | Out-Null }
          Set-ItemProperty -Path $pair[1] -Name $_.Name -Value $disabled -Type Binary
          Write-Host "Disabled: $($_.Name)"
        }
      }
    }
  }
}

Write-Host "`nDone. Check Task Manager > Startup apps - these should now show 'Disabled'. Takes effect next restart."
