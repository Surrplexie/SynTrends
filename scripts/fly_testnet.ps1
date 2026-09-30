# Fly.io testnet helpers — always-on public beta (park is emergency-only).
#
#   .\scripts\fly_testnet.ps1 status
#   .\scripts\fly_testnet.ps1 ensure
#   .\scripts\fly_testnet.ps1 health
#   .\scripts\fly_testnet.ps1 certs
#   .\scripts\fly_testnet.ps1 init      # create app + postgres + first deploy
#   .\scripts\fly_testnet.ps1 deploy
#   .\scripts\fly_testnet.ps1 park confirm
#
# Requires: flyctl in PATH (https://fly.io/docs/flyctl/install/)

param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "park", "start", "ensure", "deploy", "health", "certs", "init", "help")]
    [string]$Command = "help",

    [Parameter(Position = 1)]
    [string]$Arg2 = "",

    [string]$App = "syntrends-testnet",
    [string]$Url = $(if ($env:SYNTRENDS_URL) { $env:SYNTRENDS_URL } else { "https://testnet.syntrends.com" }),
    [string]$FallbackUrl = "https://syntrends-testnet.fly.dev",
    [string]$Config = "deploy/fly.testnet.toml",
    [string]$CertHost = "testnet.syntrends.com"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot
$Url = $Url.TrimEnd("/")
$FallbackUrl = $FallbackUrl.TrimEnd("/")

function Require-Fly {
    if (-not (Get-Command fly -ErrorAction SilentlyContinue)) {
        Write-Error "fly CLI not found. Install: https://fly.io/docs/flyctl/install/"
    }
}

function Show-Help {
    @"
Fly testnet helpers ($App)

  health   curl primary /health + /status (fallback to fly.dev if DNS is dark)
  status   fly status + health
  ensure   scale count 1 (always-on); wait for health
  start    alias of ensure
  init     FIRST TIME: create Fly app + Postgres, CORS, deploy, seed
  certs    fly certs add/show for $CertHost (app must already exist)
  deploy   fly deploy (creates the Fly app if it is missing)
  park     EMERGENCY: scale to 0 - requires: park confirm

Login does not create $App. Run init once. testnet.syntrends.com DNS is after that.

Examples:
  .\scripts\fly_testnet.ps1 init
  .\scripts\fly_testnet.ps1 health
  python scripts/launch_check.py
"@
}

function Invoke-HealthAt {
    param([string]$Target, [switch]$Quiet)
    try {
        $null = Invoke-RestMethod -Uri "$Target/health" -TimeoutSec 30
        $status = Invoke-RestMethod -Uri "$Target/status" -TimeoutSec 30
        if (-not $Quiet) {
            Write-Host "OK  $Target  env=$($status.env) block_height=$($status.block_height) agents=$($status.agents) faucet=$($status.faucet_enabled)"
        }
        return 0
    } catch {
        if (-not $Quiet) {
            Write-Host "FAIL $Target - $($_.Exception.Message)" -ForegroundColor Yellow
        }
        return 1
    }
}

function Invoke-Health {
    param([switch]$Verbose)
    $code = Invoke-HealthAt -Target $Url
    if ($code -eq 0) { return 0 }
    if ($Url -ne $FallbackUrl) {
        Write-Host "Retrying fallback $FallbackUrl ..." -ForegroundColor DarkGray
        return (Invoke-HealthAt -Target $FallbackUrl)
    }
    Write-Host "Hint: run '.\scripts\fly_testnet.ps1 ensure' then check DNS/certs for $CertHost." -ForegroundColor DarkGray
    return 1
}

function Invoke-PortalProbe {
    param([string]$Target)
    try {
        $resp = Invoke-WebRequest -Uri "$Target/owners/" -TimeoutSec 30 -UseBasicParsing
        if ([int]$resp.StatusCode -eq 200) {
            Write-Host "OK  $Target/owners/  HTTP 200"
            return 0
        }
        Write-Host "FAIL $Target/owners/ HTTP $($resp.StatusCode)" -ForegroundColor Yellow
        return 1
    } catch {
        Write-Host "FAIL $Target/owners/ - $($_.Exception.Message)" -ForegroundColor Yellow
        return 1
    }
}

function Get-FlyOrgSlug {
    $raw = (fly orgs list --json 2>&1 | Out-String).Trim()
    if (-not $raw -or $raw.Length -lt 3) { return $null }
    try {
        $parsed = $raw | ConvertFrom-Json
        if ($parsed -is [System.Array] -and $parsed.Count -gt 0) {
            if ($parsed[0].Slug) { return [string]$parsed[0].Slug }
            if ($parsed[0].slug) { return [string]$parsed[0].slug }
        }
        if ($parsed.Slug) { return [string]$parsed.Slug }
        if ($parsed.slug) { return [string]$parsed.slug }
    } catch {
        return $null
    }
    return $null
}

function Test-FlyAppExists {
    $out = (fly apps list --json 2>&1 | Out-String)
    return ($out -match [regex]::Escape($App))
}

function Ensure-FlyApp {
    if (Test-FlyAppExists) {
        Write-Host "OK  Fly app $App already exists"
        return
    }
    $org = Get-FlyOrgSlug
    Write-Host "Creating Fly app $App (login does not create it)..."
    if ($org) {
        fly apps create $App -o $org -y
    } else {
        fly apps create $App -y
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "fly apps create failed. Run: fly orgs list   then: fly apps create $App -o YOUR_ORG -y"
    }
    Write-Host "OK  created $App"
}

function Get-CorsOrigins {
    $urlsPath = Join-Path $RepoRoot "ops\public_urls.json"
    if (Test-Path $urlsPath) {
        return (Get-Content $urlsPath -Raw | ConvertFrom-Json).cors_origins_csv
    }
    return "https://syntrends.com,https://www.syntrends.com,https://testnet.syntrends.com,https://syntrends-testnet.fly.dev"
}

function Invoke-Init {
    Require-Fly
    $ErrorActionPreference = "Continue"
    Ensure-FlyApp

    $dbApp = "$App-db"
    Write-Host ""
    $org = Get-FlyOrgSlug
    $orgArgs = @()
    if ($org) { $orgArgs = @("--org", $org) }
    Write-Host "Creating single-node Postgres $dbApp in iad (this bills until you destroy it)..."
    fly postgres create --name $dbApp --region iad --initial-cluster-size 1 --vm-size shared-cpu-1x --volume-size 1 --flex @orgArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Postgres create failed. Using sqlite inside the VM (lost on redeploy)." -ForegroundColor Yellow
        fly secrets set DATABASE_URL=sqlite:///app/data/testnet.db -a $App
    } else {
        fly postgres attach $dbApp -a $App
        if ($LASTEXITCODE -ne 0) {
            Write-Host "WARN  postgres attach failed - set DATABASE_URL manually" -ForegroundColor Yellow
        }
    }

    $cors = Get-CorsOrigins
    Write-Host "Setting CORS_ORIGINS..."
    fly secrets set ("CORS_ORIGINS={0}" -f $cors) -a $App

    if (-not (Test-Path $Config)) {
        Write-Error "Config not found: $Config"
    }
    Write-Host "Deploying..."
    fly deploy -c $Config -a $App
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN  deploy health wait failed. Check: fly status -a $App ; fly logs -a $App" -ForegroundColor Yellow
        Write-Host "Then: fly secrets set DATABASE_URL=sqlite:///app/data/testnet.db -a $App"
        Write-Host "      fly deploy -c $Config -a $App"
    } else {
        Write-Host "Seeding testnet (best-effort)..."
        fly ssh console -a $App -C "python -m demo.seed_testnet" 2>&1 | Out-Host
    }

    Write-Host ""
    Write-Host "App URL: https://$App.fly.dev"
    Write-Host "Do not run certs until this URL loads. Then Cloudflare DNS for testnet."
    $script:Url = $FallbackUrl
    Invoke-Health | Out-Null
}

function Invoke-Ensure {
    Require-Fly
    if (-not (Test-FlyAppExists)) {
        Write-Host "App $App does not exist yet. Create it with:" -ForegroundColor Yellow
        Write-Host "  .\scripts\fly_testnet.ps1 init"
        exit 1
    }
    Write-Host "Ensuring $App is running (scale count 1, always-on)..."
    fly scale count 1 -a $App --yes
    Write-Host "Waiting for /health..."
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Seconds 3
        if ((Invoke-Health) -eq 0) { exit 0 }
    } while ((Get-Date) -lt $deadline)
    Write-Host "Machine started but health check timed out. Try: .\scripts\fly_testnet.ps1 health" -ForegroundColor Yellow
    exit 1
}

switch ($Command) {
    "help" { Show-Help; exit 0 }
    "health" {
        $h = Invoke-Health
        $p = Invoke-PortalProbe -Target $Url
        if ($p -ne 0 -and $Url -ne $FallbackUrl) {
            $p = Invoke-PortalProbe -Target $FallbackUrl
        }
        if ($h -ne 0 -or $p -ne 0) { exit 1 }
        exit 0
    }
    "status" {
        Require-Fly
        fly status -a $App
        Write-Host ""
        exit (Invoke-Health)
    }
    "init" { Invoke-Init }
    "certs" {
        Require-Fly
        if (-not (Test-FlyAppExists)) {
            Write-Host "App $App does not exist. Run .\scripts\fly_testnet.ps1 init first." -ForegroundColor Yellow
            exit 1
        }
        Write-Host "Requesting certificate for $CertHost on $App ..."
        fly certs add $CertHost -a $App 2>&1 | Out-Host
        fly certs show $CertHost -a $App
        Write-Host ""
        Write-Host "Point DNS for $CertHost at this app (A/AAAA or CNAME from fly certs output),"
        Write-Host "then: fly certs check $CertHost -a $App"
        Write-Host "Until DNS is live, health falls back to $FallbackUrl"
    }
    "park" {
        Require-Fly
        if ($Arg2 -ne "confirm") {
            Write-Host "Park is emergency-only. Public beta default is always-on (min_machines_running=1)." -ForegroundColor Yellow
            Write-Host "To stop compute billing anyway: .\scripts\fly_testnet.ps1 park confirm"
            exit 2
        }
        Write-Host "Parking $App (scale count 0)..."
        fly scale count 0 -a $App --yes
        Write-Host "Parked. Restore with: .\scripts\fly_testnet.ps1 ensure"
    }
    "start" { Invoke-Ensure }
    "ensure" { Invoke-Ensure }
    "deploy" {
        Require-Fly
        if (-not (Test-Path $Config)) {
            Write-Error "Config not found: $Config"
        }
        Ensure-FlyApp
        fly deploy -c $Config -a $App
        Write-Host ""
        Write-Host 'Config keeps min_machines_running=1 / auto_stop=off. Do not park after deploy.'
        Invoke-Health | Out-Null
    }
}
