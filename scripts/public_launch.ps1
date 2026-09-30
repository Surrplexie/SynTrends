# Phase N — public launch helpers (ops).
#
#   .\scripts\public_launch.ps1 print-cutover
#   .\scripts\public_launch.ps1 check
#   .\scripts\public_launch.ps1 check-strict
#   .\scripts\public_launch.ps1 wake
#
# Does not set Fly secrets (would expose them in shell history). Prints the
# exact commands from ops/public_urls.json instead.

param(
    [Parameter(Position = 0)]
    [ValidateSet("print-cutover", "check", "check-strict", "wake", "urls")]
    [string]$Action = "check"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$UrlsFile = Join-Path $Root "ops\public_urls.json"
$Urls = Get-Content $UrlsFile -Raw | ConvertFrom-Json
$Primary = $Urls.public_testnet.primary
$Fallback = $Urls.public_testnet.fallback
$App = $Urls.fly_app
$Cors = $Urls.cors_origins_csv
$Webhook = $Urls.public_testnet.persona_webhook

function Show-Urls {
    Write-Host "marketing:     $($Urls.marketing.syntrends)"
    Write-Host "primary:       $Primary"
    Write-Host "fallback:      $Fallback"
    Write-Host "owners:        $($Urls.public_testnet.owners)"
    Write-Host "persona hook:  $Webhook"
    Write-Host "fly app:       $App"
}

switch ($Action) {
    "urls" { Show-Urls }

    "print-cutover" {
        Show-Urls
        Write-Host ""
        Write-Host "# 1) TLS / DNS"
        Write-Host "fly certs add testnet.syntrends.com -a $App"
        Write-Host "fly certs check testnet.syntrends.com -a $App"
        Write-Host ""
        Write-Host "# 2) CORS + Persona (fill secrets; do not commit)"
        Write-Host "fly secrets set CORS_ORIGINS=`"$Cors`" ``"
        Write-Host "  KYC_PROVIDER=persona ``"
        Write-Host "  PERSONA_API_KEY=... ``"
        Write-Host "  PERSONA_WEBHOOK_SECRET=... ``"
        Write-Host "  PERSONA_TEMPLATE_ID=... ``"
        Write-Host "  PERSONA_ENVIRONMENT=sandbox ``"
        Write-Host "  -a $App"
        Write-Host ""
        Write-Host "# 3) Persona dashboard webhook:"
        Write-Host $Webhook
        Write-Host ""
        Write-Host "# 4) Wake + verify"
        Write-Host ".\scripts\fly_testnet.ps1 start"
        Write-Host "`$env:SYNTRENDS_URL = `"$Primary`""
        Write-Host ".\scripts\ops_check.ps1"
        Write-Host "python scripts/launch_check.py --require-persona"
        Write-Host ""
        Write-Host "Full runbook: docs/PUBLIC_LAUNCH.md"
    }

    "wake" {
        & (Join-Path $PSScriptRoot "fly_testnet.ps1") start
        $env:SYNTRENDS_URL = $Primary
        & (Join-Path $PSScriptRoot "ops_check.ps1") -Url $Primary
    }

    "check" {
        $env:SYNTRENDS_URL = $Primary
        Push-Location $Root
        try {
            python scripts/launch_check.py --base-url $Primary --also-fallback
        } finally {
            Pop-Location
        }
    }

    "check-strict" {
        $env:SYNTRENDS_URL = $Primary
        Push-Location $Root
        try {
            python scripts/launch_check.py --base-url $Primary --require-persona --require-packages
        } finally {
            Pop-Location
        }
    }
}
