# Start the TraktTV Shows Tracker backend (Windows).
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
& "$Root\run.bat" @args
