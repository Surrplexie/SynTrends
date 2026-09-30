# Ops probe — health + ready + status summary (Phase L).
#
#   $env:SYNTRENDS_URL = "https://syntrends-testnet.fly.dev"
#   .\scripts\ops_check.ps1

param(
    [string]$Url = $(if ($env:SYNTRENDS_URL) { $env:SYNTRENDS_URL } else { "https://testnet.syntrends.com" })
)

$ErrorActionPreference = "Stop"
$Url = $Url.TrimEnd("/")
Write-Host "== Ops check $Url =="

try {
    $health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 25
    Write-Host "OK  /health  $($health | ConvertTo-Json -Compress)"
} catch {
    Write-Host "FAIL /health - $($_.Exception.Message)"
    exit 1
}

$readyCode = 0
try {
    $resp = Invoke-WebRequest -Uri "$Url/ready" -TimeoutSec 25 -UseBasicParsing
    $readyCode = [int]$resp.StatusCode
    Write-Host "OK  /ready  HTTP $readyCode"
} catch {
    if ($_.Exception.Response) {
        $readyCode = [int]$_.Exception.Response.StatusCode
    }
    Write-Host "FAIL /ready HTTP $readyCode"
}

try {
    $st = Invoke-RestMethod -Uri "$Url/status" -TimeoutSec 25
    $bh = $st.block_height
    Write-Host ("OK  /status env={0} network={1} block_height={2} agents={3} paused={4} ready={5} kyc={6} persistence_ok={7}" -f `
        $st.env, $st.network, $bh, $st.agents, $st.agents_paused, $st.ready, $st.kyc_provider, $st.persistence_ok)
} catch {
    Write-Host "FAIL /status - $($_.Exception.Message)"
    exit 1
}

if ($readyCode -ne 200) { exit 1 }
exit 0
