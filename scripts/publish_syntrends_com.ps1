# Stage (and optionally deploy) the syntrends.com join door — static Pages only.
# Do NOT point apex DNS at Fly. testnet.syntrends.com stays on syntrends-testnet.
#
#   .\scripts\publish_syntrends_com.ps1
#   .\scripts\publish_syntrends_com.ps1 -Deploy
#
# -Deploy needs: npx wrangler, CLOUDFLARE_API_TOKEN (and usually CLOUDFLARE_ACCOUNT_ID)

param(
    [switch]$Deploy,
    [string]$Project = "syntrends",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot "dist\syntrends-com"
}

if (Test-Path $OutDir) {
    Remove-Item $OutDir -Recurse -Force
}
New-Item $OutDir -ItemType Directory | Out-Null
Copy-Item (Join-Path $RepoRoot "web\syntrends\*") $OutDir
$sharedOut = Join-Path $OutDir "shared"
New-Item $sharedOut -ItemType Directory | Out-Null
Copy-Item (Join-Path $RepoRoot "web\shared\style.css") $sharedOut
Copy-Item (Join-Path $RepoRoot "web\shared\portal-link.js") $sharedOut

@"
/join  /join.html  301
"@ | Set-Content -Path (Join-Path $OutDir "_redirects") -Encoding ascii

Write-Host "Staged $OutDir"
Write-Host "  index.html join.html + legal + shared/ (no API, no owners, no explorer)"
Write-Host ""
Write-Host "Cloudflare (keep testnet A/AAAA on Fly, grey cloud):"
Write-Host "  1. dash.cloudflare.com -> Workers & Pages -> Create -> Pages -> Direct Upload"
Write-Host "     project name: $Project"
Write-Host "     upload THIS folder: $OutDir"
Write-Host "  2. Custom domains -> syntrends.com  and  www.syntrends.com"
Write-Host "     Cloudflare will create proxied CNAME flattening for @ and www."
Write-Host "  3. DNS: do not add apex records that target fly.dev or syntrends-testnet."
Write-Host "  4. Incognito: https://syntrends.com -> Start connecting -> Owner portal"
Write-Host "     must land on https://testnet.syntrends.com/owners/"
Write-Host ""
Write-Host "Until apex DNS exists, join already works at:"
Write-Host "  https://testnet.syntrends.com/join.html"

if (-not $Deploy) {
    exit 0
}

if (-not $env:CLOUDFLARE_API_TOKEN) {
    Write-Error "Set CLOUDFLARE_API_TOKEN then re-run with -Deploy, or Direct Upload the staged folder."
}

npx --yes wrangler pages deploy $OutDir --project-name $Project
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Deployed. Attach custom domain syntrends.com in the Pages project if not already."
