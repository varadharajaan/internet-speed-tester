# Trigger Monthly Aggregation Lambda
# This script manually invokes the Lambda function to create monthly aggregated data

# Get project root (parent of scripts folder)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot

Write-Host "🔄 Triggering monthly aggregation Lambda..." -ForegroundColor Cyan

# Create payload file
@{mode = "monthly"} | ConvertTo-Json | Out-File -FilePath payload-monthly.json -Encoding utf8

# Invoke Lambda with payload file
aws lambda invoke `
    --function-name vd-speedtest-daily-aggregator-prod `
    --payload file://payload-monthly.json `
    output/output-monthly.json

Write-Host ""
Write-Host "✅ Lambda invoked. Response saved to output/output-monthly.json" -ForegroundColor Green
Write-Host ""

# Display the response
if (Test-Path output/output-monthly.json) {
    Write-Host "📄 Lambda Response:" -ForegroundColor Yellow
    Get-Content output/output-monthly.json | ConvertFrom-Json | ConvertTo-Json -Depth 10
    
    Write-Host ""
    Write-Host "💡 Check CloudWatch Logs for details:" -ForegroundColor Cyan
    Write-Host "   aws logs tail /aws/lambda/vd-speedtest-daily-aggregator-prod --follow" -ForegroundColor Gray
}

Pop-Location
