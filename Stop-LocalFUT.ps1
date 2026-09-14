$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot 'runtime'
$PidPath = Join-Path $RuntimeRoot 'launcher-processes.json'
$SessionPath = Join-Path $RuntimeRoot 'session.json'
$VendorRoot = Join-Path $ProjectRoot 'runtime-source'
$HostsPath = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
# FIX17: remove all local FUT/utas redirects we may have installed.
$Patterns = @(
    '^\s*127\.0\.0\.1\s+spring18\.gosredirector\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+utas\.external\.s2\.fut\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+utas\.external\.s3\.fut\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+utas\.external\.fut\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+utas\.s2\.fut\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+utas\.s3\.fut\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+utas\.fut\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+fut\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+accounts\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+gateway\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+origin-a\.akamaihd\.net\s*$',
    '^\s*127\.0\.0\.1\s+eaassets-a\.akamaihd\.net\s*$',
    '^\s*127\.0\.0\.1\s+auth\.ea\.com\s*$',
    '^\s*127\.0\.0\.1\s+signin\.ea\.com\s*$'
)
$Pattern = $Patterns[0]

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath))
    exit 0
}

if (Test-Path -LiteralPath $PidPath) {
    $tracked = Get-Content -LiteralPath $PidPath -Raw | ConvertFrom-Json
    foreach ($name in 'controlPid', 'serverPid', 'redirectorPid') {
        $id = [int]$tracked.$name
        if ($id -gt 0 -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $id -Force
            Write-Host "Stopped tracked $name process $id."
        }
    }
    Remove-Item -LiteralPath $PidPath -Force
} else {
    Write-Host "No tracked launcher processes were found; checking for this launcher's orphaned local-runtime processes."
}

# A failed start can occur after the services are created but before their PIDs
# are saved. Restrict fallback cleanup to Python processes started through this
# launcher's OpenFUT20 runner and one of the three service entry points.
$runnerPath = (Join-Path $ProjectRoot 'open_runner.py').ToLowerInvariant()
$ownedEntries = @('control_server', 'server', 'redirector_tls')
Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe','py.exe','pyw.exe') } | ForEach-Object {
    $commandLine = [string]$_.CommandLine
    if ($commandLine -and $commandLine.ToLowerInvariant().Contains($runnerPath)) {
        $entryMatch = $ownedEntries | Where-Object { $commandLine -match ('(^|\s|\")' + [regex]::Escape($_) + '($|\s|\")') }
        if ($entryMatch) {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped orphaned OpenFUT20 local-runtime process $($_.ProcessId)."
        }
    }
}

$lines = @(Get-Content -LiteralPath $HostsPath -ErrorAction Stop)
$filtered = $lines | Where-Object {
    $line = $_
    -not ($Patterns | Where-Object { $line -match $_ })
}
if ($filtered.Count -ne $lines.Count) {
    $filtered | Set-Content -LiteralPath $HostsPath -Encoding ascii
    ipconfig /flushdns | Out-Null
    Write-Host 'Removed local FUT/utas hosts redirect entries.'
} else {
    Write-Host 'No FIFA/FUT hosts redirect entries were present.'
}

Remove-Item -LiteralPath $SessionPath -Force -ErrorAction SilentlyContinue
