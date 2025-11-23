# Trigger Weekly Aggregation Lambda
# This script manually invokes the Lambda function to create weekly aggregated data

Write-Host "Triggering weekly aggregation Lambda..." -ForegroundColor Cyan

# Create payload file
'{"mode":"weekly"}' | Out-File -FilePath payload-weekly.json -Encoding ascii -NoNewline

# Invoke Lambda with payload file
aws lambda invoke `
    --function-name vd-speedtest-daily-aggregator-prod `
    --payload file://payload-weekly.json `
    output-weekly.json

Write-Host ""
Write-Host "Lambda invoked. Response saved to output-weekly.json" -ForegroundColor Green
Write-Host ""

# Display the response
if (Test-Path output-weekly.json) {
    Write-Host "Lambda Response:" -ForegroundColor Yellow
    Get-Content output-weekly.json | ConvertFrom-Json | ConvertTo-Json -Depth 10
    
    Write-Host ""
    Write-Host "Check CloudWatch Logs for details:" -ForegroundColor Cyan
    Write-Host "   aws logs tail /aws/lambda/vd-speedtest-daily-aggregator-prod --follow" -ForegroundColor Gray
}
