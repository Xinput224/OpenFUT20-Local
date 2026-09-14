[CmdletBinding()]
param(
    [string]$GamePath = "",
    [switch]$NoGameLaunch,
    [switch]$SafeGameLaunch,
    [switch]$LegitimateEA
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$SettingsPath = Join-Path $ProjectRoot 'launcher-settings.json'
$RuntimeRoot = Join-Path $ProjectRoot 'runtime'
# The FUT server owns status.json and updates it as FIFA advances through
# Blaze/EASW/FUT states. Keep launcher lifecycle status separate so the
# watcher is not blanked when the game presses Enter and the server records
# its next protocol milestone.
$StatusPath = Join-Path $RuntimeRoot 'launcher-status.json'
$ProtocolStatusPath = Join-Path $RuntimeRoot 'status.json'
$PidPath = Join-Path $RuntimeRoot 'launcher-processes.json'
$SessionPath = Join-Path $RuntimeRoot 'session.json'
$HostsPath = Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
# FIX17: also pin common FUT/utas hostnames to localhost so post-accountinfo
# auth calls cannot escape to live EA servers (which would fail silently).
$RedirectLines = @(
    '127.0.0.1 spring18.gosredirector.ea.com',
    '127.0.0.1 utas.external.s2.fut.ea.com',
    '127.0.0.1 utas.external.s3.fut.ea.com',
    '127.0.0.1 utas.external.fut.ea.com',
    '127.0.0.1 utas.s2.fut.ea.com',
    '127.0.0.1 utas.s3.fut.ea.com',
    '127.0.0.1 utas.fut.ea.com',
    '127.0.0.1 fut.ea.com'
)
$LegacyIdentityRedirectLines = @(
    '127.0.0.1 accounts.ea.com',
    '127.0.0.1 gateway.ea.com',
    '127.0.0.1 origin-a.akamaihd.net',
    '127.0.0.1 eaassets-a.akamaihd.net',
    '127.0.0.1 auth.ea.com',
    '127.0.0.1 signin.ea.com'
)
$RedirectLine = $RedirectLines[0]


# Open parity build: no Discord or launcher authorization gate.



function Write-StatusLine([string]$Label, [string]$Value, [ConsoleColor]$Color = [ConsoleColor]::White) {
    Write-Host ('{0,-16} {1}' -f ($Label + ':'), $Value) -ForegroundColor $Color
}

function Save-Status([hashtable]$Status) {
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    $Status.updatedAt = (Get-Date).ToString('o')
    $Status | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StatusPath -Encoding utf8
}

# V29: keep the FUT club in one Windows-local profile instead of tying the save
# to the extracted build folder.  runtime\data becomes a junction to this
# location, so coins, squads, club items, Player Picks and progress survive
# restarts and future OpenFUT20 build folders.
function Initialize-PersistentSave {
    if (-not $env:LOCALAPPDATA) {
        Write-Host '[SAVE] LOCALAPPDATA is unavailable; using this build folder for the save.' -ForegroundColor Yellow
        New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot 'data') | Out-Null
        return
    }

    $persistentRoot = Join-Path $env:LOCALAPPDATA 'OpenFUT20'
    $persistentData = Join-Path $persistentRoot 'data'
    $persistentBackups = Join-Path $persistentRoot 'backups'
    $projectData = Join-Path $RuntimeRoot 'data'
    $dbName = 'localfut20.sqlite3'
    $persistentDb = Join-Path $persistentData $dbName

    New-Item -ItemType Directory -Force -Path $persistentData | Out-Null
    New-Item -ItemType Directory -Force -Path $persistentBackups | Out-Null

    $projectItem = Get-Item -LiteralPath $projectData -Force -ErrorAction SilentlyContinue
    if ($projectItem -and (($projectItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        Write-Host ("[SAVE] Persistent FUT profile: {0}" -f $persistentDb) -ForegroundColor DarkGray
        return
    }

    # First V29 launch can discover the newest save from a nearby V27/V28 build
    # so the user does not have to rebuild the squad or re-enter coins just
    # because the new ZIP was extracted into a different folder.
    $projectLegacyDb = Join-Path $projectData $dbName
    if (-not (Test-Path -LiteralPath $persistentDb -PathType Leaf) -and
        -not (Test-Path -LiteralPath $projectLegacyDb -PathType Leaf)) {
        $searchRoots = @(
            (Split-Path -Path $ProjectRoot -Parent),
            (Join-Path $HOME 'Downloads'),
            (Join-Path $HOME 'Desktop'),
            (Join-Path $HOME 'Documents\GitHub')
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Container) } | Select-Object -Unique
        $candidates = @()
        foreach ($root in $searchRoots) {
            Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like 'OpenFUT20*' -and $_.FullName -ne $ProjectRoot } |
                ForEach-Object {
                    $candidate = Join-Path $_.FullName 'runtime\data\localfut20.sqlite3'
                    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                        $candidates += Get-Item -LiteralPath $candidate
                    }
                }
        }
        $sourceDb = @($candidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1)[0]
        if ($sourceDb) {
            Get-ChildItem -LiteralPath $sourceDb.Directory.FullName -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like 'localfut20.sqlite3*' } |
                Copy-Item -Destination $persistentData -Force
            Write-Host ("[SAVE] Imported previous OpenFUT20 club from: {0}" -f $sourceDb.FullName) -ForegroundColor Green
        }
    }

    if ($projectItem) {
        $legacyDb = Join-Path $projectData $dbName
        if (Test-Path -LiteralPath $legacyDb -PathType Leaf) {
            $useLegacy = -not (Test-Path -LiteralPath $persistentDb -PathType Leaf)
            if (-not $useLegacy) {
                try {
                    $useLegacy = (Get-Item -LiteralPath $legacyDb).LastWriteTimeUtc -gt (Get-Item -LiteralPath $persistentDb).LastWriteTimeUtc
                } catch { $useLegacy = $false }
            }
            if ($useLegacy) {
                if (Test-Path -LiteralPath $persistentDb -PathType Leaf) {
                    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
                    Copy-Item -LiteralPath $persistentDb -Destination (Join-Path $persistentBackups ("before-migration-{0}.sqlite3" -f $stamp)) -Force
                }
                Get-ChildItem -LiteralPath $projectData -Force -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -like 'localfut20.sqlite3*' } |
                    Copy-Item -Destination $persistentData -Force
                Write-Host '[SAVE] Migrated the existing build save into the persistent FUT profile.' -ForegroundColor Green
            } else {
                $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
                $legacyBackup = Join-Path $persistentBackups ("unused-build-save-{0}.sqlite3" -f $stamp)
                Copy-Item -LiteralPath $legacyDb -Destination $legacyBackup -Force -ErrorAction SilentlyContinue
            }
        }

        # Keep repository placeholders such as .gitkeep visible through the junction.
        Get-ChildItem -LiteralPath $projectData -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike 'localfut20.sqlite3*' } |
            ForEach-Object {
                if (-not $_.PSIsContainer) {
                    Copy-Item -LiteralPath $_.FullName -Destination $persistentData -Force -ErrorAction SilentlyContinue
                }
            }
        Remove-Item -LiteralPath $projectData -Recurse -Force
    }

    try {
        New-Item -ItemType Junction -Path $projectData -Target $persistentData -Force | Out-Null
        Write-Host ("[SAVE] Persistent FUT profile: {0}" -f $persistentDb) -ForegroundColor Green
    } catch {
        # A normal folder is still safe for this run; never fail game launch only
        # because the junction could not be created. Copy the persistent profile
        # back so this fallback never starts the user with an empty club.
        New-Item -ItemType Directory -Force -Path $projectData | Out-Null
        Get-ChildItem -LiteralPath $persistentData -Force -ErrorAction SilentlyContinue |
            Copy-Item -Destination $projectData -Force -ErrorAction SilentlyContinue
        Write-Host ("[SAVE] Could not create persistent junction; using {0}" -f $projectData) -ForegroundColor Yellow
    }
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-Listener([int]$Port) {
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Wait-ForPort([int]$Port, [int]$TimeoutSeconds = 15) {
    $until = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Get-Listener $Port) { return $true }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $until)
    return $false
}

function Add-RedirectHostsEntry {
    $lines = @(Get-Content -LiteralPath $HostsPath -ErrorAction Stop)
    # Match the FIFA 21 EA-App mode: identity and CDN hosts must remain live
    # so EA App can perform legitimate account authentication with public PKI.
    $lines = @($lines | Where-Object { $LegacyIdentityRedirectLines -notcontains $_ })
    $added = 0
    foreach ($entry in $RedirectLines) {
        if ($lines -notcontains $entry) {
            $lines += $entry
            $added++
        }
    }
    if ($added -gt 0) {
        # Write the complete preserved file once. This avoids partial updates
        # when multiple Add-Content calls race with antivirus/file indexing.
        $lines | Set-Content -LiteralPath $HostsPath -Encoding ascii
    }
    ipconfig /flushdns | Out-Null
    $final = @(Get-Content -LiteralPath $HostsPath -ErrorAction Stop)
    $missing = @($RedirectLines | Where-Object { $final -notcontains $_ })
    if ($missing.Count -gt 0) {
        throw "Hosts redirect verification failed; missing $($missing.Count) required entr$(if($missing.Count -eq 1){'y'}else{'ies' })."
    }
    Write-Host ("Hosts redirect: {0} new entries (FUT/utas + redirector)" -f $added) -ForegroundColor Cyan
    return $added
}

function Remove-RedirectHostsEntries {
    try {
        if (-not (Test-Path -LiteralPath $HostsPath -PathType Leaf)) { return }
        $lines = @(Get-Content -LiteralPath $HostsPath -ErrorAction Stop)
        $filtered = @($lines | Where-Object { $RedirectLines -notcontains $_ })
        if ($filtered.Count -ne $lines.Count) {
            $filtered | Set-Content -LiteralPath $HostsPath -Encoding ascii
            ipconfig /flushdns | Out-Null
            Write-Host '[CLEANUP] Removed Local FUT hosts redirects.' -ForegroundColor DarkGray
        }
    } catch {
        Write-Host ("[CLEANUP] Could not remove hosts redirects: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
    }
}

function Stop-LocalFUTOwnedServices {
    $pids = @()
    if (Test-Path -LiteralPath $PidPath -PathType Leaf) {
        try {
            $owned = Get-Content -LiteralPath $PidPath -Raw | ConvertFrom-Json
            foreach ($name in @('controlPid','serverPid','redirectorPid')) {
                $value = $owned.$name
                if ($value) { $pids += [int]$value }
            }
        } catch {}
    }

    # Include listeners as a fallback when the services were reused from a prior
    # launch and the current PowerShell process did not create them itself.
    foreach ($port in @($controlPort,$futPort,$futTlsPort,$blazePort,$redirectorPort)) {
        if (-not $port) { continue }
        $listener = Get-Listener ([int]$port)
        if ($listener) { $pids += @($listener | ForEach-Object { [int]$_.OwningProcess }) }
    }
    $pids = @($pids | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
    $rootPattern = [regex]::Escape($ProjectRoot)
    foreach ($pidValue in $pids) {
        try {
            $procInfo = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $pidValue) -ErrorAction SilentlyContinue
            if ($null -eq $procInfo) { continue }
            $name = [string]$procInfo.Name
            $cmdLine = [string]$procInfo.CommandLine
            $ownedByThisProject = (
                $name -in @('python.exe','pythonw.exe','py.exe','pyw.exe') -and
                $cmdLine -match '(?i)open_runner\.py' -and
                ($cmdLine -match $rootPattern)
            )
            if ($ownedByThisProject) {
                Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
                Write-Host ("[CLEANUP] Stopped Local FUT PID {0}." -f $pidValue) -ForegroundColor DarkGray
            }
        } catch {}
    }
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    Remove-RedirectHostsEntries
}

function Invoke-TrustPatch([string]$Python, [string]$RunnerScript, [int]$GamePid) {
    $cmd = 'echo.|"{0}" -3.13 "{1}" trust_patch --pid {2}' -f $Python, $RunnerScript, $GamePid
    $output = & cmd.exe /d /c $cmd 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

function Resolve-GamePath([string]$ExplicitPath, [object]$Settings) {
    if ($ExplicitPath) { return $ExplicitPath }
    if ($Settings.fifa_exe) { return [string]$Settings.fifa_exe }
    if ($Settings.gamePath) { return [string]$Settings.gamePath }
    $candidates = @(
        'C:\Program Files\EA Games\FIFA 20\FIFA20.exe',
        'C:\Program Files (x86)\Origin Games\FIFA 20\FIFA20.exe',
        'C:\Program Files\Origin Games\FIFA 20\FIFA20.exe',
        'C:\Program Files (x86)\Steam\steamapps\common\FIFA 20\FIFA20.exe'
    )
    return @($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1)[0]
}

function Resolve-EAClientPath {
    $candidates = @()
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles 'Electronic Arts\EA Desktop\EA Desktop\EALauncher.exe')
        $candidates += (Join-Path $env:ProgramFiles 'Electronic Arts\EA Desktop\EA Desktop\EALaunchHelper.exe')
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} 'Electronic Arts\EA Desktop\EA Desktop\EALauncher.exe')
        $candidates += (Join-Path ${env:ProgramFiles(x86)} 'Electronic Arts\EA Desktop\EA Desktop\EALaunchHelper.exe')
    }
    return @($candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1)[0]
}

function Resolve-EAContentId([string]$GameExe) {
    if (-not $GameExe) { return $null }
    $gameRoot = Split-Path -Path $GameExe -Parent
    $xmlCandidates = @(
        (Join-Path $gameRoot '__Installer\installerdata.xml'),
        (Join-Path $gameRoot '__Installer\InstallerData.xml'),
        (Join-Path $gameRoot 'installerdata.xml')
    )
    foreach ($xmlPath in $xmlCandidates) {
        if (-not (Test-Path -LiteralPath $xmlPath -PathType Leaf)) { continue }
        try {
            [xml]$xml = Get-Content -LiteralPath $xmlPath -Raw
            $nodes = @($xml.SelectNodes("//*[local-name()='contentID']"))
            foreach ($node in $nodes) {
                $value = [string]$node.InnerText
                if ($value -and $value.Trim()) { return $value.Trim() }
            }
        } catch {}
    }
    return $null
}

function Resolve-EAOfferId([string]$GameExe) {
    $contentId = Resolve-EAContentId $GameExe
    if ($contentId) { return $contentId }

    $installData = 'C:\ProgramData\EA Desktop\InstallData'
    if (-not (Test-Path -LiteralPath $installData -PathType Container)) { return $null }
    $gameRoot = (Split-Path -Path $GameExe -Parent).ToLowerInvariant()
    $bases = @(Get-ChildItem -LiteralPath $installData -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'base-*' })
    foreach ($b in $bases) {
        $offer = $b.Name.Substring(5)
        if (-not $offer) { continue }
        if ($b.FullName.ToLowerInvariant() -match 'fifa.?20') { return $offer }
        try {
            if (-not $b.PSIsContainer) {
                $txt = Get-Content -LiteralPath $b.FullName -Raw -ErrorAction SilentlyContinue
                if ($txt -and $txt.ToLowerInvariant().Contains($gameRoot)) { return $offer }
            }
        } catch {}
    }
    return $null
}

function Start-FIFA20([string]$ResolvedGame, [bool]$UseEAPath) {
    if (-not $UseEAPath) {
        Write-Host '[GAME] Direct launch mode selected.' -ForegroundColor Cyan
        return Start-Process -FilePath $ResolvedGame -WorkingDirectory (Split-Path -Path $ResolvedGame -Parent) -PassThru
    }

    $eaClient = Resolve-EAClientPath
    if (-not $eaClient) {
        throw 'LEGITIMATE EA GAME COPY is enabled, but EA App was not found. Install or repair EA App, then try again.'
    }
    $offerId = Resolve-EAOfferId $ResolvedGame
    if (-not $offerId) {
        throw 'LEGITIMATE EA GAME COPY is enabled, but the FIFA 20 EA offer/content ID could not be detected. Browse to FIFA20.exe inside the EA-installed FIFA 20 folder.'
    }

    $uri = 'origin2://game/launch/?offerIds={0}&autoDownload=1' -f [Uri]::EscapeDataString($offerId)
    Write-Host '[GAME] Legitimate EA copy enabled.' -ForegroundColor Green
    Write-Host '[GAME] Handing FIFA 20 launch to EA App...' -ForegroundColor Cyan
    try {
        # Use the registered origin2 protocol so EA App performs entitlement
        # validation and starts the installed game through its normal path.
        Start-Process -FilePath $uri | Out-Null
    } catch {
        # Fallback for systems where protocol ShellExecute is restricted.
        Start-Process -FilePath $eaClient -ArgumentList @($uri) | Out-Null
    }
    return $null
}

function Stop-StaleLocalFutListeners([int[]]$Ports) {
    $candidatePids = @()
    foreach ($port in $Ports) {
        $listener = Get-Listener $port
        if ($listener) { $candidatePids += @($listener | ForEach-Object { [int]$_.OwningProcess }) }
    }
    $candidatePids = @($candidatePids | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
    if (-not $candidatePids) { return }

    foreach ($pidValue in $candidatePids) {
        try {
            $procInfo = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $pidValue) -ErrorAction SilentlyContinue
            if ($null -eq $procInfo) { continue }
            $name = [string]$procInfo.Name
            $cmdLine = [string]$procInfo.CommandLine
            $looksLikeLocalFut = (
                $name -in @('python.exe','pythonw.exe','py.exe','pyw.exe') -and
                ($cmdLine -match '(?i)open_runner\.py|localfut20[\\/]server\.py|localfut20[\\/]control_server\.py|redirector_tls\.py')
            )
            if ($looksLikeLocalFut) {
                Write-Host ("      Refreshing stale Local FUT process PID {0}..." -f $pidValue) -ForegroundColor DarkGray
                Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }

    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    $deadline = (Get-Date).AddSeconds(12)
    do {
        $stillBusy = @($Ports | Where-Object { Get-Listener $_ })
        if (-not $stillBusy) { return }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
}

function Stop-ExistingFifaForEAMode {
    $existing = @(Get-Process -Name FIFA20 -ErrorAction SilentlyContinue)
    if (-not $existing) { return }
    Write-Host '[GAME] Closing the previous FIFA 20 instance so EA/FIFASetup can start a clean session...' -ForegroundColor Yellow
    foreach ($proc in $existing) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    $deadline = (Get-Date).AddSeconds(15)
    do {
        if (-not (Get-Process -Name FIFA20 -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
    throw 'The previous FIFA20.exe instance did not close. Close FIFA 20 manually and press PLAY again.'
}

function Test-ControlHealth([object]$Settings) {
    try {
        $hostName = if ($Settings.local_host) { [string]$Settings.local_host } else { '127.0.0.1' }
        $port = if ($Settings.control_port) { [int]$Settings.control_port } else { 47220 }
        $h = Invoke-RestMethod -Uri ("http://{0}:{1}/v1/health" -f $hostName, $port) -TimeoutSec 3
        return ($null -ne $h.ok -and $h.ok -eq $true)
    } catch { return $false }
}

function Bootstrap-LocalSession([object]$Settings) {
    $hostName = if ($Settings.local_host) { [string]$Settings.local_host } else { '127.0.0.1' }
    $port = if ($Settings.control_port) { [int]$Settings.control_port } else { 47220 }
    $body = @{ accountId=[string]$Settings.test_account_id; personaId=[int]$Settings.persona_id; displayName=[string]$Settings.display_name } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Method Post -Uri ("http://{0}:{1}/v1/session/bootstrap" -f $hostName, $port) -ContentType 'application/json' -Body $body -TimeoutSec 5
}

function Test-LocalRuntimeHealth([object]$Settings) {
    try {
        $hostName = if ($Settings.local_host) { [string]$Settings.local_host } else { '127.0.0.1' }
        $futPort = if ($Settings.fut_port) { [int]$Settings.fut_port } else { 8080 }
        $futTlsPort = if ($Settings.fut_tls_port) { [int]$Settings.fut_tls_port } else { 443 }
        $blazePort = if ($Settings.blaze_port) { [int]$Settings.blaze_port } else { 44321 }
        $account = Invoke-RestMethod -Uri ("http://{0}:{1}/ut/game/fifa20/user/accountinfo" -f $hostName, $futPort) -TimeoutSec 3
        # Accountinfo is intentionally a retail pre-auth document in FIX22.
        # Validate its persona/club path rather than the old local-only
        # isUnderAge field, which is not part of the retail response shape.
        $persona = @($account.userAccountInfo.personas) | Select-Object -First 1
        if ($null -eq $account.userAccountInfo -or $null -eq $persona -or @($persona.userClubList).Count -lt 1) { return $false }
        # These are localhost listeners; checking the listener table avoids the
        # noisy Test-NetConnection progress panel in the user-facing console.
        return [bool](Get-Listener $blazePort) -and [bool](Get-Listener $futTlsPort)
    } catch {
        return $false
    }
}

function Resolve-ProjectPath([string]$PathText) {
    if (-not $PathText) { return "" }
    if ([System.IO.Path]::IsPathRooted($PathText)) { return $PathText }
    return (Join-Path $ProjectRoot $PathText)
}

function Get-ProtocolSnapshot {
    if (-not (Test-Path -LiteralPath $ProtocolStatusPath -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $ProtocolStatusPath -Raw | ConvertFrom-Json } catch { return $null }
}

function Test-TitleAuthVerified {
    $snap = Get-ProtocolSnapshot
    if ($null -eq $snap) { return $false }
    if ($snap.status -eq 'FUT READY') { return $true }
    if ($null -ne $snap.milestones -and $null -ne $snap.milestones.AUTH) { return $true }
    return $false
}

function Wait-ForTitleAuth([int]$TimeoutSeconds = 35) {
    $until = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-TitleAuthVerified) { return $true }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $until)
    return $false
}

function Invoke-AutomaticCrashDiagnostics([string]$Reason = 'fifa-exit') {
    try {
        $collector = Join-Path $ProjectRoot 'tools\collect_pick_crash_diagnostics.py'
        if (-not (Test-Path -LiteralPath $collector -PathType Leaf)) {
            Write-Host '[DIAG] Automatic crash collector is missing; cleanup will continue.' -ForegroundColor Yellow
            return
        }
        $pyCommand = Get-Command py -ErrorAction Stop
        Write-Host '[DIAG] Capturing automatic FIFA exit/crash report...' -ForegroundColor Cyan
        $output = @(& $pyCommand.Source -3.13 $collector --reason $Reason 2>&1)
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {
            $reportPath = @($output | Where-Object { $_ -and ([string]$_).Trim() } | Select-Object -Last 1)[0]
            if ($reportPath) {
                Write-Host ("[DIAG] Saved: {0}" -f $reportPath) -ForegroundColor Green
            } else {
                Write-Host '[DIAG] Automatic report created under logs\crash-reports.' -ForegroundColor Green
            }
        } else {
            Write-Host ("[DIAG] Automatic collector exited with code {0}. Cleanup will continue." -f $exitCode) -ForegroundColor Yellow
            foreach ($line in $output) { Write-Host ("       {0}" -f $line) -ForegroundColor DarkGray }
        }
    } catch {
        Write-Host ("[DIAG] Automatic crash collection failed: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
    }
}

function Keep-LocalFUTAlive([string]$Message = 'Local FUT services are running while FIFA 20 is open.') {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor DarkCyan
    Write-Host ' FIFA 20 LOCAL FUT - RUNNING' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor DarkCyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host 'Local FUT will stop automatically after FIFA 20 closes.' -ForegroundColor DarkGray
    $lastSummary = ''
    $lastProtocol = ''
    $failedHealthChecks = 0
    $gameWasSeen = [bool](Get-Process -Name FIFA20 -ErrorAction SilentlyContinue)
    $missingGameChecks = 0
    $gameExitObserved = $false
    try {
        while ($true) {
            Start-Sleep -Seconds 2

            $servicesAlive = (Get-Listener $futPort) -and (Get-Listener $blazePort) -and (Get-Listener $controlPort) -and (Get-Listener $futTlsPort)
            if ($servicesAlive) {
                $failedHealthChecks = 0
            } else {
                $failedHealthChecks++
                if ($failedHealthChecks -ge 3) {
                    Write-Host ''
                    Write-Host 'Local FUT services are no longer running.' -ForegroundColor Yellow
                    break
                }
            }

            $fifaNow = @(Get-Process -Name FIFA20 -ErrorAction SilentlyContinue)
            if ($fifaNow.Count -gt 0) {
                $gameWasSeen = $true
                $missingGameChecks = 0
            } elseif ($gameWasSeen) {
                $missingGameChecks++
                # Three consecutive misses avoids reacting to a momentary query
                # failure while still shutting everything down within ~6 seconds.
                if ($missingGameChecks -ge 3) {
                    $gameExitObserved = $true
                    Write-Host ''
                    Write-Host '[GAME] FIFA 20 closed. Capturing diagnostics, then stopping Local FUT services...' -ForegroundColor Yellow
                    break
                }
            }

            if (Test-Path -LiteralPath $StatusPath) {
                try {
                    $current = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
                    $summary = "{0}|{1}|{2}" -f $current.status,$current.game,$current.connection
                    if ($summary -ne $lastSummary) { $lastSummary = $summary }
                } catch {}
            }
            $protocol = Get-ProtocolSnapshot
            if ($null -ne $protocol) {
                $protocolSummary = "{0}|{1}" -f $protocol.status,$protocol.detail
                if ($protocolSummary -ne $lastProtocol) { $lastProtocol = $protocolSummary }
            }
        }
    } finally {
        if ($gameExitObserved) {
            # Give Windows Error Reporting/Application Error a brief moment to
            # publish the FIFA crash event, then collect while Local FUT logs,
            # sockets, and the SQLite state are still available.
            Start-Sleep -Milliseconds 1500
            Invoke-AutomaticCrashDiagnostics -Reason 'fifa20-process-exited'
        }
        Stop-LocalFUTOwnedServices
        try {
            $status.status = 'STOPPED'
            $status.game = 'CLOSED'
            $status.connection = 'LOCAL FUT STOPPED AFTER FIFA EXIT'
            Save-Status $status
        } catch {}
    }
}

function Assert-ProjectFiles([object]$Settings) {
    $required = @(
        'open_runner.py',
        'runtime-open\runtime_entries.json',
        'localfut20-manifest.json',
        'localfut20\players.json',
        'localfut20\managers.json',
        'runtime-source\certs\spring18-cert.pem',
        'runtime-source\certs\spring18-key.pem',
        'runtime-source\gos2015-original-modulus.bin',
        'runtime-source\local-gos2015-modulus.bin'
    )
    $missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $ProjectRoot $_) -PathType Leaf) })
    if ($missing) { throw "Project is incomplete. Missing: $($missing -join ', ')" }
    $certPath = Resolve-ProjectPath ([string]$Settings.certificate_path)
    $keyPath = Resolve-ProjectPath ([string]$Settings.certificate_key_path)
    if ($certPath -and -not (Test-Path -LiteralPath $certPath -PathType Leaf)) {
        throw "Configured certificate_path does not exist: $($Settings.certificate_path)"
    }
    if ($keyPath -and -not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
        throw "Configured certificate_key_path does not exist: $($Settings.certificate_key_path)"
    }
}

$status = @{
    status = 'NOT READY'
    server = 'NOT STARTED'
    redirector = 'NOT STARTED'
    game = 'NOT STARTED'
    trustBridge = 'NOT APPLIED'
    connection = 'NOT STARTED'
    fut = 'NOT VERIFIED'
    detail = @()
}
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

if (-not $SafeGameLaunch -and -not $NoGameLaunch -and -not (Test-Administrator)) {
    Write-Host 'Administrator permission is required to update the hosts file and patch the running FIFA20.exe process.' -ForegroundColor Yellow
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath))
    if ($GamePath) { $argList += @('-GamePath', ('"{0}"' -f $GamePath)) }
    if ($NoGameLaunch) { $argList += '-NoGameLaunch' }
    if ($SafeGameLaunch) { $argList += '-SafeGameLaunch' }
    if ($LegitimateEA) { $argList += '-LegitimateEA' }
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argList
    exit 0
}

try {
    Clear-Host
    Write-Host '============================================================' -ForegroundColor DarkCyan
    Write-Host ' FIFA 20 LOCAL FUT' -ForegroundColor White
    Write-Host '============================================================' -ForegroundColor DarkCyan
    Write-Host '[1/5] Checking launcher files and settings...' -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $SettingsPath -PathType Leaf)) { throw "Missing launcher-settings.json at $SettingsPath" }
    $settings = Get-Content -LiteralPath $SettingsPath -Raw | ConvertFrom-Json
    if (-not $PSBoundParameters.ContainsKey('LegitimateEA') -and $settings.PSObject.Properties.Name -contains 'legitimate_ea_copy') {
        $LegitimateEA = [bool]$settings.legitimate_ea_copy
    }
    Assert-ProjectFiles $settings
    Write-Host '      OK - project files are ready.' -ForegroundColor Green
    Write-Host '[2/5] Preparing Python and local club data...' -ForegroundColor Cyan
    Initialize-PersistentSave

    $python = Get-Command py -ErrorAction Stop
    & $python.Source -3.13 -c 'import cryptography' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency missing: cryptography. Install it with: py -m pip install cryptography>=42' }
    & $python.Source -3.13 -c 'import PIL' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency missing: Pillow. Install dependencies with: py -3 -m pip install -r requirements.txt' }

    $offlineLog = Join-Path $RuntimeRoot 'offline-data.log'
    & $python.Source -3.13 (Join-Path $ProjectRoot 'open_runner.py') offline_data *> $offlineLog
    if ($LASTEXITCODE -ne 0) { throw "Database initialization failed. See $offlineLog" }
    Write-Host '      OK - Python dependencies and club data are ready.' -ForegroundColor Green
    Write-Host '[3/5] Starting Local FUT services...' -ForegroundColor Cyan

    $futPort = if ($settings.fut_port) { [int]$settings.fut_port } else { 8080 }
    $futTlsPort = if ($settings.fut_tls_port) { [int]$settings.fut_tls_port } else { 443 }
    $blazePort = if ($settings.blaze_port) { [int]$settings.blaze_port } else { 44321 }
    $redirectorPort = if ($settings.redirector_port) { [int]$settings.redirector_port } else { 42230 }
    $controlPort = if ($settings.control_port) { [int]$settings.control_port } else { 47220 }
    # accounts.ea.com and utas.* are pinned to localhost.  If 443 is owned by
    # another process the native client fails its next hop before any HTTP log,
    # so treat this as a required local FUT port.
    $portsToCheck = @($futPort, $futTlsPort, $blazePort, $controlPort)
    if (-not $SafeGameLaunch) { $portsToCheck += $redirectorPort }

    if ($LegitimateEA) {
        # Never reuse an already-running tester server for EA mode.  A previous
        # build/mode may have cached OSDK_CORE before the EA checkbox changed,
        # which leaves FIFA on the reconnect/age-restriction path.  Recycle only
        # Python listeners that clearly belong to a Local FUT runtime.
        Write-Host '      EA mode: refreshing Local FUT services for a clean title-auth session...' -ForegroundColor Cyan
        Stop-StaleLocalFutListeners $portsToCheck
    }

    $occupied = @()
    foreach ($port in $portsToCheck) {
        $listener = Get-Listener $port
        if ($listener) { $occupied += ("{0} (PID {1})" -f $port, $listener.OwningProcess) }
    }
    if ($occupied) {
        if (-not (Test-LocalRuntimeHealth $settings) -or -not (Test-ControlHealth $settings)) {
            throw "Required local port(s) already in use: $($occupied -join ', '). Run Stop-LocalFUT.cmd or CHECK_PORTS.cmd."
        }
        $status.server = "READY (reused existing FUT/Blaze services)"
        $status.redirector = if ($SafeGameLaunch) { 'SKIPPED by -SafeGameLaunch' } else { 'READY or already running' }
        Write-StatusLine 'Server' 'Reusing already-running healthy local services' Green
        $status.detail += 'Reused existing healthy local services.'
    } else {
        $serverLog = Join-Path $RuntimeRoot 'server.log'
        $controlLog = Join-Path $RuntimeRoot 'control.log'
        $controlError = Join-Path $RuntimeRoot 'control.error.log'
        $control = Start-Process -FilePath $python.Source -ArgumentList @('-3.13', ('"{0}"' -f (Join-Path $ProjectRoot 'open_runner.py')), 'control_server') -WorkingDirectory $ProjectRoot -RedirectStandardOutput $controlLog -RedirectStandardError $controlError -WindowStyle Hidden -PassThru
        if (-not (Wait-ForPort $controlPort)) {
            if (-not $control.HasExited) { Stop-Process -Id $control.Id -Force }
            throw "Control service did not become ready on port $controlPort. See $controlError"
        }
        $serverError = Join-Path $RuntimeRoot 'server.error.log'
        $server = Start-Process -FilePath $python.Source -ArgumentList @('-3.13', ('"{0}"' -f (Join-Path $ProjectRoot 'open_runner.py')), 'server') -WorkingDirectory $ProjectRoot -RedirectStandardOutput $serverLog -RedirectStandardError $serverError -WindowStyle Hidden -PassThru
        if (-not (Wait-ForPort $blazePort) -or -not (Wait-ForPort $futPort) -or -not (Wait-ForPort $futTlsPort)) {
            if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
            throw "FUT/Blaze server did not become ready on ports $blazePort, $futPort, and required FUT TLS port $futTlsPort. See $serverError"
        }
        $status.server = "READY (Blaze $blazePort, FUT $futPort, FUT TLS $futTlsPort)"
        Write-StatusLine 'Server' $status.server Green

        $redirector = $null
        if (-not $SafeGameLaunch) {
            $redirectorLog = Join-Path $RuntimeRoot 'redirector.log'
            $redirectorError = Join-Path $RuntimeRoot 'redirector.error.log'
            $redirector = Start-Process -FilePath $python.Source -ArgumentList @('-3.13', ('"{0}"' -f (Join-Path $ProjectRoot 'open_runner.py')), 'redirector_tls') -WorkingDirectory $ProjectRoot -RedirectStandardOutput $redirectorLog -RedirectStandardError $redirectorError -WindowStyle Hidden -PassThru
            if (-not (Wait-ForPort $redirectorPort)) {
                if (-not $redirector.HasExited) { Stop-Process -Id $redirector.Id -Force }
                if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
                throw "TLS redirector did not become ready on port $redirectorPort. See $redirectorError"
            }
            $status.redirector = "READY (TLS redirector $redirectorPort)"
            Write-StatusLine 'Redirector' $status.redirector Green
            Add-RedirectHostsEntry | Out-Null
            $status.connection = 'HOSTS REDIRECT INSTALLED; waiting for FIFA20 process and trust bridge'
        } else {
            $status.redirector = 'SKIPPED by -SafeGameLaunch'
        }

        @{ controlPid = $control.Id; serverPid = $server.Id; redirectorPid = if ($redirector) { $redirector.Id } else { $null }; projectRoot = $ProjectRoot } |
            ConvertTo-Json | Set-Content -LiteralPath $PidPath -Encoding utf8
    }

    if ($NoGameLaunch) {
        $status.status = 'LOCAL SERVICES READY'
        $status.game = 'SKIPPED by -NoGameLaunch'
        $status.connection = 'LOCAL SERVICES READY; hosts redirect not installed'
        Save-Status $status
        Write-StatusLine 'Game' $status.game Yellow
        Write-StatusLine 'Connection' $status.connection Yellow
        Write-Host "Status file: $StatusPath"
        exit 0
    }

    Write-Host '      OK - Local FUT services are ready.' -ForegroundColor Green
    Write-Host '[4/5] Starting FIFA 20...' -ForegroundColor Cyan
    $resolvedGame = Resolve-GamePath $GamePath $settings
    if (-not $resolvedGame -or -not (Test-Path -LiteralPath $resolvedGame -PathType Leaf)) {
        $status.status = 'LOCAL SERVICES READY'
        $status.game = 'NOT FOUND'
        $status.connection = 'WAITING; hosts redirect not installed'
        $status.detail += 'Set fifa_exe in launcher-settings.json or pass -GamePath with the full FIFA20.exe path.'
        Save-Status $status
        Write-StatusLine 'Game' $status.game Red
        Write-StatusLine 'Connection' $status.connection Yellow
        Write-Host 'Missing prerequisite: FIFA20.exe path. Set fifa_exe in launcher-settings.json.' -ForegroundColor Red
        exit 0
    }

    $session = Bootstrap-LocalSession $settings
    if ($null -eq $session.session.sessionId) { throw 'Local session bootstrap failed.' }
    $status.detail += ('Aurora-style session enrolled: ' + [string]$session.session.sessionId)
    $status.connection = 'SESSION ENROLLED; waiting for FIFA20 process'
    Save-Status $status

    if ($LegitimateEA) {
        Stop-ExistingFifaForEAMode
    }
    $fifa = Get-Process -Name FIFA20 -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending | Select-Object -First 1
    if (-not $fifa) {
        $game = Start-FIFA20 -ResolvedGame $resolvedGame -UseEAPath ([bool]$LegitimateEA)
        if ($LegitimateEA) {
            Write-Host '[GAME] EA App may open FIFASetup first. Click PLAY there once.' -ForegroundColor Yellow
            Write-Host '[GAME] Waiting for the final FIFA20.exe process; do not start a second copy.' -ForegroundColor DarkGray
        }
    }
    $deadline = (Get-Date).AddSeconds($(if ($LegitimateEA) { 300 } else { 120 }))
    do {
        $fifa = Get-Process -Name FIFA20 -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending | Select-Object -First 1
        if ($fifa) { break }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    if (-not $fifa) { throw "FIFA20.exe did not remain running within 120 seconds after launching $resolvedGame" }
    $status.game = "RUNNING (PID $($fifa.Id))"
    Write-StatusLine 'Game' $status.game Green
    Write-Host '[5/5] Connecting FIFA 20 to Local FUT...' -ForegroundColor Cyan

    if ($SafeGameLaunch) {
        $status.status = 'LOCAL SERVICES READY'
        $status.trustBridge = 'SKIPPED by -SafeGameLaunch'
        $status.connection = 'LOCAL SERVICES READY; stopped before TLS redirector, trust patch, and hosts routing'
        Save-Status $status
        Write-StatusLine 'Trust bridge' $status.trustBridge Yellow
        Write-StatusLine 'Connection' $status.connection Yellow
        Keep-LocalFUTAlive
        exit 0
    }

    # Direct launches can keep the small configured warm-up.  EA/FIFASetup
    # launches must be patched immediately: the title can attempt its first
    # redirector/TLS connection only a fraction of a second after FIFA20.exe
    # appears.  Waiting here can leave the game on "Press R to reconnect"
    # even though the patch succeeds later.
    $delay = if ($LegitimateEA) { 0 } else { [Math]::Max(0, [int]$settings.gameReadyDelaySeconds) }
    if ($delay -gt 0) { Start-Sleep -Seconds $delay }

    # FIFASetup/EA App may create more than one FIFA20.exe PID during hand-off.
    # Watch every PID, retry the same PID if it was seen before the trust table
    # was fully mapped, and stop only after real Blaze/FUT authentication.
    $patchedFifaPids = @{}
    $patchAttempts = @{}
    $lastAttemptAt = @{}
    $authDeadline = (Get-Date).AddSeconds($(if ($LegitimateEA) { 240 } else { 60 }))
    $lastPatchedPid = 0
    $patchSucceeded = $false
    $lastWaitMessage = [DateTime]::MinValue
    $reconnectHintShown = $false
    do {
        $allFifa = @(Get-Process -Name FIFA20 -ErrorAction SilentlyContinue | Sort-Object StartTime)
        if ($allFifa.Count -gt 0) {
            $newest = $allFifa | Sort-Object StartTime -Descending | Select-Object -First 1
            $status.game = "RUNNING (PID $($newest.Id))"

            foreach ($currentFifa in $allFifa) {
                $pidNow = [int]$currentFifa.Id
                if ($patchedFifaPids.ContainsKey($pidNow)) { continue }

                $now = Get-Date
                $canTry = (-not $lastAttemptAt.ContainsKey($pidNow)) -or (($now - [DateTime]$lastAttemptAt[$pidNow]).TotalMilliseconds -ge 650)
                if (-not $canTry) { continue }
                $lastAttemptAt[$pidNow] = $now
                $attempt = 1
                if ($patchAttempts.ContainsKey($pidNow)) { $attempt = [int]$patchAttempts[$pidNow] + 1 }
                $patchAttempts[$pidNow] = $attempt

                if ($attempt -eq 1) {
                    Write-Host ("[TRUST] FIFA20.exe detected (PID {0}). Patching immediately..." -f $pidNow) -ForegroundColor Cyan
                } elseif (($attempt % 5) -eq 0) {
                    Write-Host ("[TRUST] Retrying FIFA20.exe PID {0} (attempt {1})..." -f $pidNow, $attempt) -ForegroundColor DarkGray
                }

                if (Get-Process -Id $pidNow -ErrorAction SilentlyContinue) {
                    $patch = Invoke-TrustPatch $python.Source (Join-Path $ProjectRoot 'open_runner.py') $pidNow
                    $patch.Output | Add-Content -LiteralPath (Join-Path $RuntimeRoot 'trust-patch.log') -Encoding utf8
                    if ($patch.Output -match '\[SUCCESS\] Patched') {
                        $patchedFifaPids[$pidNow] = $true
                        $patchSucceeded = $true
                        $lastPatchedPid = $pidNow
                        $status.trustBridge = "PATCHED (FIFA20 PID $pidNow)"
                        Add-RedirectHostsEntry | Out-Null
                        Save-Status $status
                        Write-StatusLine 'Trust bridge' $status.trustBridge Green
                        Write-Host ("[GAME] Final FIFA20 process recognized: PID {0}. Waiting for local title authentication..." -f $pidNow) -ForegroundColor Green
                    }
                }
            }
        }

        if (Test-TitleAuthVerified) { break }

        $now = Get-Date
        if (($now - $lastWaitMessage).TotalSeconds -ge 5) {
            $lastWaitMessage = $now
            $alive = @(Get-Process -Name FIFA20 -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending | Select-Object -First 1)
            if ($alive) {
                $patchText = if ($patchSucceeded) { 'PATCHED' } else { 'waiting for patch' }
                Write-Host ("[WAIT] FIFA20.exe PID {0} is running; trust={1}; waiting for Blaze/title auth..." -f $alive.Id, $patchText) -ForegroundColor DarkGray
            } else {
                Write-Host '[WAIT] FIFA20.exe is not running right now; waiting for EA/FIFASetup hand-off...' -ForegroundColor DarkGray
            }
        }

        # If the first network attempt happened before the process could be
        # patched, FIFA 20 displays its own reconnect prompt.  Once the patch
        # is confirmed, one manual reconnect is enough to repeat the title
        # handshake through localhost.
        if ($LegitimateEA -and $patchSucceeded -and -not $reconnectHintShown) {
            $reconnectHintShown = $true
            Write-Host '[ACTION] If FIFA shows "Press R to reconnect", press R ONCE now. The final FIFA20.exe is recognized and patched.' -ForegroundColor Yellow
        }

        Start-Sleep -Milliseconds 150
    } while ((Get-Date) -lt $authDeadline)

    if (Test-TitleAuthVerified) {
        $protocol = Get-ProtocolSnapshot
        if ($null -ne $protocol -and $protocol.status -eq 'FUT READY') {
            $status.status = 'FUT READY'
            $status.connection = 'FUT READY; Ultimate Team hub reached'
            Write-StatusLine 'Connection' $status.connection Green
            Write-Host '      READY - Ultimate Team hub reached.' -ForegroundColor Green
        } else {
            $status.status = 'TITLE AUTH READY'
            $status.connection = 'LOCAL TITLE AUTH VERIFIED; waiting for FUT hub'
            Write-StatusLine 'Connection' $status.connection Green
            Write-Host '      Local title authentication verified. Open Ultimate Team.' -ForegroundColor Green
        }
    } elseif ($patchSucceeded) {
        $status.status = 'TITLE AUTH WAITING'
        $status.connection = 'FINAL FIFA PROCESS PATCHED; title authentication not verified yet'
        Write-StatusLine 'Connection' $status.connection Yellow
        Write-Host '      FIFA20.exe is patched, but the title did not authenticate yet.' -ForegroundColor Yellow
        if ($LegitimateEA) {
            Write-Host '      If FIFASetup is still open, click PLAY once and wait. The launcher is monitoring process replacement.' -ForegroundColor DarkGray
            Write-Host '      If FIFA shows an EA age restriction, that restriction belongs to the EA account; Local FUT reports an adult local profile.' -ForegroundColor DarkGray
        }
    } else {
        $status.trustBridge = 'FAILED; no final FIFA20.exe process was successfully patched'
        $status.connection = 'NOT READY'
        Write-StatusLine 'Trust bridge' $status.trustBridge Red
        Write-Host '      The final FIFA20.exe process could not be patched. See runtime\trust-patch.log.' -ForegroundColor Red
    }
    Save-Status $status
    Write-Host "Status file: $StatusPath"
    Keep-LocalFUTAlive
} catch {
    $status.status = 'FAILED'
    $status.server = if ($status.server -eq 'NOT STARTED') { 'FAILED' } else { $status.server }
    $status.connection = 'NOT READY'
    $status.detail += $_.Exception.Message
    Save-Status $status
    Write-StatusLine 'ERROR' $_.Exception.Message Red
    Write-Host "Status file: $StatusPath"
    exit 1
}
