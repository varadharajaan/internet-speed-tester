$basePath = Join-Path $env:LOCALAPPDATA "Programs"
$agentLine = "-javaagent:C:\temp\sniarbtej.jar=id=sniarbtej,user=Varadhaajan,exp=2098-10-24,force=true"

# Detect only folders containing JetBrains products
$jetbrainsFolders = Get-ChildItem -Path $basePath -Directory |
    Where-Object { $_.Name -match "(pycharm|intellij|datagrip|dataspell|goland|rider|rubymine|phpstorm|webstorm|clion|appcode|jetbrains)" }

foreach ($folder in $jetbrainsFolders) {
    $binPath = Join-Path $folder.FullName "bin"
    if (Test-Path $binPath) {
        $vmOptionsFiles = Get-ChildItem -Path $binPath -Filter "*.exe.vmoptions" -File -ErrorAction SilentlyContinue
        foreach ($file in $vmOptionsFiles) {
            Write-Host "Processing $($file.FullName)..."
            if (-not (Test-Path $file.FullName)) {
                Write-Warning "File not found: $($file.FullName)"
                continue
            }

            $lines = Get-Content -Path $file.FullName
            $found = $false

            for ($i = 0; $i -lt $lines.Count; $i++) {
                if ($lines[$i] -match "sniarbtej\.jar") {
                    $lines[$i] = $agentLine
                    $found = $true
                    break
                }
            }

            if (-not $found) {
                Add-Content -Path $file.FullName -Value $agentLine
                Write-Host "Appended agent line to $($file.FullName)"
            } else {
                Set-Content -Path $file.FullName -Value $lines
                Write-Host "Replaced old agent line in $($file.FullName)"
            }
        }
    }
}
