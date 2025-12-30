# Helper script to invoke Lambda functions without base64 warnings

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("hourly", "daily", "weekly", "monthly", "yearly")]
    [string]$Mode
)

# Get project root (parent of scripts folder)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot

$payloadFile = "payload-$Mode.json"
"{`"mode`":`"$Mode`"}" | Out-File -Encoding ASCII -NoNewline $payloadFile

Write-Host "Invoking Lambda with mode: $Mode"
aws lambda invoke `
    --function-name vd-speedtest-daily-aggregator-prod `
    --cli-binary-format raw-in-base64-out `
    --payload "file://$payloadFile" `
    --region ap-south-1 `
    output/response-$Mode.json | Out-Null

if (Test-Path output/response-$Mode.json) {
    Write-Host "`n=== Response ==="
    $response = Get-Content output/response-$Mode.json | ConvertFrom-Json
    if ($response.body) {
        $body = $response.body | ConvertFrom-Json
        $body | ConvertTo-Json -Depth 10
    } else {
        $response | ConvertTo-Json -Depth 10
    }
}

Remove-Item $payloadFile -ErrorAction SilentlyContinue
Pop-Location
