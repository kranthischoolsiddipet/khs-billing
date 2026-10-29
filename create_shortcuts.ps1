$targetDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $targetDir) { $targetDir = Get-Location }

$batPath = Join-Path $targetDir "START_KHS_BILLING.bat"
$iconPath = Join-Path $targetDir "khs_logo.ico"
$shortcutName = "KHS Billing.lnk"

# 1. Desktop
$desktopPath = [System.Environment]::GetFolderPath('Desktop')
$wsh = New-Object -ComObject WScript.Shell

$deskShortcut = $wsh.CreateShortcut((Join-Path $desktopPath $shortcutName))
$deskShortcut.TargetPath = $batPath
$deskShortcut.WorkingDirectory = $targetDir
$deskShortcut.Description = "Kranthi High School - Billing & Receipt Management System"
if (Test-Path $iconPath) {
    $deskShortcut.IconLocation = "$iconPath,0"
}
$deskShortcut.Save()
Write-Host "[OK] Desktop shortcut created: $(Join-Path $desktopPath $shortcutName)" -ForegroundColor Green

# 2. Start Menu
$startMenuPrograms = [System.Environment]::GetFolderPath('Programs')
$startFolder = Join-Path $startMenuPrograms "Kranthi High School"
if (-not (Test-Path $startFolder)) {
    New-Item -ItemType Directory -Path $startFolder -Force | Out-Null
}
$startShortcut = $wsh.CreateShortcut((Join-Path $startFolder $shortcutName))
$startShortcut.TargetPath = $batPath
$startShortcut.WorkingDirectory = $targetDir
$startShortcut.Description = "Kranthi High School - Billing & Receipt Management System"
if (Test-Path $iconPath) {
    $startShortcut.IconLocation = "$iconPath,0"
}
$startShortcut.Save()
Write-Host "[OK] Start Menu shortcut created: $(Join-Path $startFolder $shortcutName)" -ForegroundColor Green

# Also put directly in root of Start Menu Programs
$startRootShortcut = $wsh.CreateShortcut((Join-Path $startMenuPrograms $shortcutName))
$startRootShortcut.TargetPath = $batPath
$startRootShortcut.WorkingDirectory = $targetDir
$startRootShortcut.Description = "Kranthi High School - Billing & Receipt Management System"
if (Test-Path $iconPath) {
    $startRootShortcut.IconLocation = "$iconPath,0"
}
$startRootShortcut.Save()

# 3. User Pinned Taskbar directory (for Windows Taskbar integration)
$appData = [System.Environment]::GetFolderPath('ApplicationData')
$taskbarDir = Join-Path $appData "Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"
if (Test-Path $taskbarDir) {
    $tbShortcut = $wsh.CreateShortcut((Join-Path $taskbarDir $shortcutName))
    $tbShortcut.TargetPath = $batPath
    $tbShortcut.WorkingDirectory = $targetDir
    $tbShortcut.Description = "Kranthi High School - Billing & Receipt Management System"
    if (Test-Path $iconPath) {
        $tbShortcut.IconLocation = "$iconPath,0"
    }
    $tbShortcut.Save()
    Write-Host "[OK] Taskbar pinned directory shortcut added" -ForegroundColor Green
}
