# Battery lag diagnostic - READ-ONLY (changes no settings)
# Run on battery, while the lag is happening:
#   Right-click Start > Terminal (Admin), then:
#   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\OneDrive\Documents\UBC MCP\battery_lag_diag.ps1"

$out = "$env:USERPROFILE\OneDrive\Documents\UBC MCP\diag"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$r = "$out\report.txt"
"Battery lag diagnostic - $(Get-Date)" | Out-File $r

function Section($t) { "`n===== $t =====" | Out-File $r -Append }

Section "Power source / battery"
Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus | Format-List | Out-File $r -Append

Section "Active power plan"
powercfg /getactivescheme | Out-File $r -Append

Section "Processor power settings (AC vs DC)"
powercfg /query SCHEME_CURRENT SUB_PROCESSOR | Out-File $r -Append

Section "Windows power mode overlay"
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes" -ErrorAction SilentlyContinue | Format-List | Out-File $r -Append

Section "CPU / GPU"
Get-CimInstance Win32_Processor | Select-Object Name, CurrentClockSpeed, MaxClockSpeed, LoadPercentage | Format-List | Out-File $r -Append
Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, CurrentRefreshRate | Format-List | Out-File $r -Append

Section "Top CPU processes (3 samples, 5 s apart)"
1..3 | ForEach-Object {
  "-- sample $_ --" | Out-File $r -Append
  Get-Counter '\Process(*)\% Processor Time' -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty CounterSamples |
    Where-Object { $_.InstanceName -notin '_total','idle' } |
    Sort-Object CookedValue -Descending | Select-Object -First 12 InstanceName, @{n='CPU';e={[math]::Round($_.CookedValue/$env:NUMBER_OF_PROCESSORS,1)}} |
    Format-Table -AutoSize | Out-File $r -Append
  Start-Sleep 5
}

Section "Top memory processes"
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name, Id, @{n='MB';e={[math]::Round($_.WorkingSet64/1MB)}} | Format-Table -AutoSize | Out-File $r -Append

Section "Startup / background apps"
Get-CimInstance Win32_StartupCommand | Select-Object Name, Command | Format-Table -AutoSize | Out-File $r -Append

Section "Battery report + 60-second energy trace (saved as HTML)"
powercfg /batteryreport /output "$out\battery-report.html" | Out-File $r -Append
powercfg /energy /duration 60 /output "$out\energy-report.html" | Out-File $r -Append

"`nDone. Tell Claude: 'diag done'." | Out-File $r -Append
Write-Host "Done - report saved to $out. Tell Claude 'diag done'."
