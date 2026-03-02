param(
  [string]$Serial = "",
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

$ErrorActionPreference = "Stop"

function Has-Arg {
  param([string]$Name, [string[]]$AllArgs)
  foreach ($a in $AllArgs) {
    if ($a -eq $Name) { return $true }
  }
  return $false
}

function Find-VenvPython {
  param([string]$RepoRoot, [string]$PcSenderDir)

  $candidates = @()

  if ($env:VIRTUAL_ENV) {
    $candidates += (Join-Path $env:VIRTUAL_ENV "Scripts\\python.exe")
  }

  $candidates += (Join-Path $RepoRoot ".venv\\Scripts\\python.exe")
  $candidates += (Join-Path $PcSenderDir ".venv\\Scripts\\python.exe")
  # Backward-compat: some environments may have been created as ".venv-1".
  $candidates += (Join-Path $RepoRoot ".venv-1\\Scripts\\python.exe")

  foreach ($p in $candidates) {
    if (Test-Path $p) { return $p }
  }

  throw "No venv python found. Create/activate venv, or install one at $RepoRoot\\.venv."
}

$pcSenderDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $pcSenderDir
$scriptPath = Join-Path $pcSenderDir "app\\pc_realsense_smoke_test.py"

if (-not (Test-Path $scriptPath)) {
  throw "Smoke test script not found: $scriptPath"
}

$pythonExe = Find-VenvPython -RepoRoot $repoRoot -PcSenderDir $pcSenderDir

$finalArgs = @()
if (-not (Has-Arg "--serial" $Args) -and ($Serial -ne "")) {
  $finalArgs += @("--serial", $Serial)
}
if (-not (Has-Arg "--preview" $Args) -and -not (Has-Arg "--no-preview" $Args)) {
  $finalArgs += @("--preview")
}
if (-not (Has-Arg "--spatial" $Args)) { $finalArgs += @("--spatial") }
if (-not (Has-Arg "--temporal" $Args)) { $finalArgs += @("--temporal") }
if (-not (Has-Arg "--hole-filling" $Args)) { $finalArgs += @("--hole-filling") }
if (-not (Has-Arg "--center-window" $Args)) { $finalArgs += @("--center-window", "9") }

$finalArgs += $Args

Write-Host "Using python: $pythonExe"
Write-Host "Running: $scriptPath $($finalArgs -join ' ')"

& $pythonExe $scriptPath @finalArgs
