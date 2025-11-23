# Wrapper to support both -- and - argument prefixes
# This script normalizes -- to - and calls the main script

$normalizedArgs = @()

foreach ($arg in $args) {
    if ($arg -is [string] -and $arg -match '^--([a-zA-Z].*)$') {
        # Convert --param to -param
        $normalizedArgs += "-$($matches[1])"
    } else {
        $normalizedArgs += $arg
    }
}

# Call the main script with normalized arguments
$mainScript = Join-Path $PSScriptRoot "env_manager.ps1"

# Use Invoke-Expression to properly handle the arguments
$cmd = "& '$mainScript'"
foreach ($arg in $normalizedArgs) {
    if ($arg -match '\s') {
        $cmd += " '$arg'"
    } else {
        $cmd += " $arg"
    }
}

Invoke-Expression $cmd
exit $LASTEXITCODE

