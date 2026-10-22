param([switch]$Demo, [switch]$Init, [int]$Port = 8080)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtime = Join-Path $PSScriptRoot '.runtime\python.exe'
if (-not (Test-Path -LiteralPath $runtime)) {
    $runtime = 'python'
}
$serverArgs = @('app/server.py', '--port', "$Port")
if ($Demo) { $serverArgs += '--demo' }
if ($Init) { $serverArgs += '--init' }
& $runtime @serverArgs
