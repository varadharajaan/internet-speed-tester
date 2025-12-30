# -------------------------------------------------------------
# Reset-AggregatorWarning.ps1
# Forces vd-speedtest-aggregator-warnings-prod alarm to OK
# -------------------------------------------------------------

# Get project root (parent of scripts folder)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot

Write-Host "Invoking vd-speedtest-daily-aggregator-prod Lambda..."
aws lambda invoke --function-name "vd-speedtest-daily-aggregator-prod" "output.json" | Out-Null
Write-Host "Lambda invoked successfully."

Start-Sleep -Seconds 5

Write-Host "Publishing zero data point to vd-speed-test/Logs -> AggregatorWarnings..."
aws cloudwatch put-metric-data `
  --namespace "vd-speed-test/Logs" `
  --metric-name "AggregatorWarnings" `
  --value 0 `
  --dimensions "FunctionName=vd-speedtest-daily-aggregator-prod" `
  --region "ap-south-1"
Write-Host "Zero metric published."

Start-Sleep -Seconds 5

# Optional: temporarily set the alarm to OK for testing
Write-Host "Manually setting alarm state to OK..."
aws cloudwatch set-alarm-state `
  --alarm-name "vd-speedtest-aggregator-warnings-prod" `
  --state-value "OK" `
  --state-reason "Manual reset after duplicate warning cleanup" `
  --region "ap-south-1"
Write-Host "Alarm state set to OK."

Start-Sleep -Seconds 3
Write-Host "`n✅ Alarm vd-speedtest-aggregator-warnings-prod should now show as OK in CloudWatch."

Pop-Location