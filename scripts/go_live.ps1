# Official start / go-live orchestrator (Phase N).
#
#   .\scripts\go_live.ps1
#   .\scripts\go_live.ps1 -SkipDeploy
#   .\scripts\go_live.ps1 -Strict
#
# Creates/redeploys Fly testnet when missing, sets CORS, requests certs,
# seeds if possible, runs launch_check. Does not invent Persona/PyPI/npm secrets.

param(
    [switch]$SkipDeploy,
    [switch]$SkipCerts,
    [switch]$SkipSeed,
    [switch]$Strict,
    [string]$App = "syntrends-testnet",
    [string]$Org = "",
    [string]$PrimaryHost = "testnet.syntrends.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step([string]$msg) { Write-Host ("`n== {0} ==" -f $msg) -ForegroundColor Cyan }
function Ok([string]$msg) { Write-Host ("OK    {0}" -f $msg) -ForegroundColor Green }
function Warn([string]$msg) { Write-Host ("WARN  {0}" -f $msg) -ForegroundColor Yellow }
function Fail([string]$msg) { Write-Host ("FAIL  {0}" -f $msg) -ForegroundColor Red }

$blockers = New-Object System.Collections.Generic.List[string]
$emptyObj = '{}'
$emptyArr = '[]'

Step "0 Preconditions"
if (-not (Get-Command fly -ErrorAction SilentlyContinue)) {
    Fail "fly CLI missing"
    [void]$blockers.Add("Install flyctl from https://fly.io/docs/flyctl/install/")
} else {
    Ok "flyctl present"
}

$who = (fly auth whoami 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    Fail "fly auth whoami failed - run fly auth login"
    [void]$blockers.Add("fly auth login")
} else {
    Ok ("fly auth: {0}" -f $who)
}

$orgsTrim = (fly orgs list --json 2>&1 | Out-String).Trim()
if ($orgsTrim -eq $emptyObj -or $orgsTrim -eq $emptyArr -or $orgsTrim.Length -lt 3) {
    Fail "No Fly organization visible (token/org broken)"
    [void]$blockers.Add("Open https://fly.io/dashboard - fix personal org, then fly auth logout and fly auth login")
    [void]$blockers.Add("Rotate Fly API token if stale (Dashboard - Account - Access Tokens)")
} else {
    Ok "Fly orgs reachable"
    if (-not $Org) {
        try {
            $parsed = $orgsTrim | ConvertFrom-Json
            if ($parsed -is [System.Array] -and $parsed.Count -gt 0) {
                $Org = $parsed[0].Slug
                if (-not $Org) { $Org = $parsed[0].slug }
            } elseif ($parsed.Slug) {
                $Org = $parsed.Slug
            }
        } catch {
            Warn "Could not parse orgs JSON for default Org"
        }
    }
}

Step "1 Print cutover commands"
& (Join-Path $PSScriptRoot "public_launch.ps1") print-cutover

if ($blockers.Count -gt 0 -and -not $SkipDeploy) {
    Fail "Stopping before deploy - fix Fly org/auth first"
    Write-Host ""
    Write-Host "Blockers:" -ForegroundColor Red
    foreach ($b in $blockers) { Write-Host (" - {0}" -f $b) }
    Write-Host ""
    Write-Host "After Fly works, re-run: .\scripts\go_live.ps1"
    Write-Host "Then set Persona secrets + publish SDKs (docs/PUBLIC_LAUNCH.md)."
    exit 2
}

if ($SkipDeploy) {
    Warn "SkipDeploy set - not creating/deploying"
} else {
    Step "2 Ensure app exists"
    $appsOut = fly apps list --json 2>&1 | Out-String
    if ($appsOut -notmatch [regex]::Escape($App)) {
        if (-not $Org) {
            Fail "Need -Org org-slug to create app"
            [void]$blockers.Add("Re-run with -Org your-fly-org-slug")
            exit 2
        }
        Write-Host ("Creating app {0} in org {1} ..." -f $App, $Org)
        fly apps create $App -o $Org -y
        if ($LASTEXITCODE -ne 0) { Fail "apps create failed"; exit 1 }
        Ok ("created {0}" -f $App)
    } else {
        Ok ("app {0} already exists" -f $App)
    }

    Step "3 CORS origins (no Persona secrets)"
    $cors = (Get-Content (Join-Path $Root "ops\public_urls.json") -Raw | ConvertFrom-Json).cors_origins_csv
    fly secrets set ("CORS_ORIGINS={0}" -f $cors) -a $App
    if ($LASTEXITCODE -ne 0) { Warn "CORS secrets set failed" } else { Ok "CORS_ORIGINS set" }

    Step "4 Deploy"
    fly deploy -c deploy/fly.testnet.toml -a $App
    if ($LASTEXITCODE -ne 0) { Fail "deploy failed"; exit 1 }
    Ok "deployed"

    if (-not $SkipSeed) {
        Step "5 Seed testnet (best-effort)"
        fly ssh console -a $App -C "python -m demo.seed_testnet" 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Warn "seed failed or timed out - seed manually later"
        } else {
            Ok "seeded"
        }
    }
}

if (-not $SkipCerts -and $blockers.Count -eq 0) {
    Step ("6 TLS cert for {0}" -f $PrimaryHost)
    fly certs add $PrimaryHost -a $App 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Warn ("certs add failed - add DNS then fly certs add {0} -a {1}" -f $PrimaryHost, $App)
        [void]$blockers.Add(("DNS for {0} pointing at Fly" -f $PrimaryHost))
    } else {
        Ok "cert requested - complete DNS from fly certs show"
        fly certs show $PrimaryHost -a $App 2>&1 | Out-Host
    }
}

if ($blockers.Count -eq 0 -or $SkipDeploy) {
    Step "7 Wake + health (fallback URL)"
    & (Join-Path $PSScriptRoot "fly_testnet.ps1") start
    & (Join-Path $PSScriptRoot "ops_check.ps1") -Url "https://syntrends-testnet.fly.dev"

    Step "8 launch_check"
    $lcArgs = @("scripts/launch_check.py", "--also-fallback")
    if ($Strict) {
        $lcArgs += @("--require-persona", "--require-packages")
    }
    & python @lcArgs
    $lc = $LASTEXITCODE
} else {
    $lc = 2
}

Step "9 Remaining human steps"
Write-Host ("1. Persona secrets on Fly + webhook https://{0}/owners/api/kyc/webhook" -f $PrimaryHost)
Write-Host ("2. Marketing CTAs on syntrends.com -> https://{0}/owners/" -f $PrimaryHost)
Write-Host "3. Publish SDKs via Actions (PYPI_API_TOKEN, NPM_TOKEN) version 0.1.0"
Write-Host "4. git tag testnet-v1.0 / v0.1.0 and push"
Write-Host "5. Send docs/INVITE_TEMPLATE.md to 3-10 testers"
Write-Host ("6. Actions var SYNTRENDS_E2E_URL=https://{0}" -f $PrimaryHost)

if ($blockers.Count -gt 0) {
    Write-Host ""
    Write-Host "Outstanding blockers:" -ForegroundColor Yellow
    foreach ($b in $blockers) { Write-Host (" - {0}" -f $b) }
}

if ($lc -ne 0) { exit $lc }
if ($blockers.Count -gt 0) { exit 2 }
Ok "go_live automated path finished"
exit 0
