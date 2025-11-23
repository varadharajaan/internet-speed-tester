<#
.SYNOPSIS
    Universal Python environment management wrapper script.

.DESCRIPTION
    This PowerShell wrapper for env_manager.py automatically executes environment
    management commands in the current shell context, allowing proper activation,
    switching, and deactivation of Python environments.
    
    Supports: venv, conda, poetry, pipenv, pdm, hatch, pyenv, docker

.PARAMETER Action
    The action to perform:
    - create (default): Interactive environment creation wizard
    - switch: Switch from current environment to another
    - deactivate: Deactivate the currently active environment
    - help: Display this help message

.EXAMPLE
    .\env_wrapper.ps1
    Create a new environment interactively (venv, conda, poetry, etc.)

.EXAMPLE
    .\env_wrapper.ps1 -Action switch
    Switch from current environment to another one

.EXAMPLE
    .\env_wrapper.ps1 -Action deactivate
    Deactivate the currently active environment

.EXAMPLE
    .\env_wrapper.ps1 -Action help
    Display detailed help information

.NOTES
    This wrapper uses dot-sourcing to execute generated scripts in the current
    shell context, which allows environment variables to be properly modified.
    
    For more options, use: python env_manager.py --help
#>

param(
    [ValidateSet("create", "switch", "deactivate", "help")]
    [string]$Action = "create"
)

# Display help
if ($Action -eq "help") {
    Get-Help $MyInvocation.MyCommand.Path -Detailed
    Write-Host "`n" -NoNewline
    Write-Host "For advanced options, run: " -NoNewline -ForegroundColor Cyan
    Write-Host "python env_manager.py --help" -ForegroundColor Yellow
    exit 0
}

Write-Host "Running environment manager..." -ForegroundColor Cyan

# Run the Python script based on action
if ($Action -eq "switch") {
    python env_manager.py --switch
    
    # Check if switch script was created
    if (Test-Path ".\switch_env.ps1") {
        Write-Host "`nExecuting environment switch..." -ForegroundColor Green
        
        # Source the script to run in current shell context
        . ".\switch_env.ps1"
        
        # Verify switch
        if ($env:VIRTUAL_ENV) {
            Write-Host "SUCCESS: Virtual environment activated!" -ForegroundColor Green
            Write-Host "Virtual environment: $env:VIRTUAL_ENV" -ForegroundColor Cyan
        } elseif ($env:CONDA_DEFAULT_ENV) {
            Write-Host "SUCCESS: Conda environment activated!" -ForegroundColor Green
            Write-Host "Conda environment: $env:CONDA_DEFAULT_ENV" -ForegroundColor Cyan
        } else {
            Write-Host "WARNING: Switch script ran but environment may not be active" -ForegroundColor Yellow
        }
    } else {
        Write-Host "`nNo environment switch performed." -ForegroundColor Gray
    }
} elseif ($Action -eq "deactivate") {
    python env_manager.py --deactivate
    
    # Check if deactivate script was created
    if (Test-Path ".\deactivate_env.ps1") {
        Write-Host "`nExecuting environment deactivation..." -ForegroundColor Green
        
        # Source the script to run in current shell context
        . ".\deactivate_env.ps1"
        
        # Verify deactivation
        if (-not $env:VIRTUAL_ENV -and -not $env:CONDA_DEFAULT_ENV) {
            Write-Host "SUCCESS: Environment deactivated!" -ForegroundColor Green
        } else {
            Write-Host "WARNING: Deactivation script ran but environment may still be active" -ForegroundColor Yellow
            if ($env:VIRTUAL_ENV) {
                Write-Host "Virtual environment still active: $env:VIRTUAL_ENV" -ForegroundColor Yellow
            }
            if ($env:CONDA_DEFAULT_ENV) {
                Write-Host "Conda environment still active: $env:CONDA_DEFAULT_ENV" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "`nNo environment deactivation needed." -ForegroundColor Gray
    }
} else {
    # Default: create mode
    python env_manager.py
    
    # Check if a specific environment was just generated (marker file exists)
    $markerFile = Join-Path $PWD ".last_generated_env"
    $preferredScript = $null
    
    if (Test-Path $markerFile) {
        $preferredScript = Get-Content $markerFile -Raw
        $preferredScript = $preferredScript.Trim()
        Remove-Item $markerFile -ErrorAction SilentlyContinue
    }
    
    # Check which activation scripts exist
    $activationScripts = @(
        @{Name="Virtual Environment"; Script="activate_venv.ps1"; EnvVar="VIRTUAL_ENV"},
        @{Name="Conda"; Script="activate_conda.ps1"; EnvVar="CONDA_DEFAULT_ENV"},
        @{Name="Poetry"; Script="activate_poetry.ps1"; EnvVar="VIRTUAL_ENV"},
        @{Name="PDM"; Script="activate_pdm.ps1"; EnvVar="VIRTUAL_ENV"},
        @{Name="Pipenv"; Script="activate_pipenv.ps1"; EnvVar="VIRTUAL_ENV"},
        @{Name="Hatch"; Script="activate_hatch.ps1"; EnvVar="VIRTUAL_ENV"},
        @{Name="Pyenv"; Script="activate_pyenv.ps1"; EnvVar="PYENV_VERSION"}
    )
    
    # If we have a preferred script (just generated), activate it directly
    if ($preferredScript) {
        $selectedEnv = $activationScripts | Where-Object { $_.Script -eq $preferredScript } | Select-Object -First 1
        
        if ($selectedEnv) {
            $scriptPath = Join-Path $PWD $selectedEnv.Script
            
            if (Test-Path $scriptPath) {
                Write-Host "`nActivating $($selectedEnv.Name) environment..." -ForegroundColor Green
                . $scriptPath
                
                # Verify activation
                $envVarValue = Get-Item -Path "Env:$($selectedEnv.EnvVar)" -ErrorAction SilentlyContinue
                if ($envVarValue) {
                    Write-Host "SUCCESS: $($selectedEnv.Name) environment activated!" -ForegroundColor Green
                    Write-Host "Environment: $($envVarValue.Value)" -ForegroundColor Cyan
                } else {
                    Write-Host "WARNING: $($selectedEnv.Name) activation script ran but environment not verified" -ForegroundColor Yellow
                    Write-Host "Note: Some environments (pipenv, hatch) require interactive shells to activate properly" -ForegroundColor Gray
                }
            }
        }
        return
    }
    
    # Find all available activation scripts
    $availableScripts = @()
    foreach ($envConfig in $activationScripts) {
        $scriptPath = Join-Path $PWD $envConfig.Script
        if (Test-Path $scriptPath) {
            $availableScripts += $envConfig
        }
    }
    
    # If multiple scripts exist, ask which one to activate
    if ($availableScripts.Count -gt 1) {
        Write-Host "`nMultiple activation scripts found:" -ForegroundColor Cyan
        for ($i = 0; $i -lt $availableScripts.Count; $i++) {
            Write-Host "  $($i + 1). $($availableScripts[$i].Name) ($($availableScripts[$i].Script))" -ForegroundColor Gray
        }
        Write-Host "  0. Skip activation" -ForegroundColor Gray
        
        $choice = Read-Host "`nWhich environment to activate? [1-$($availableScripts.Count), 0 to skip]"
        
        if ($choice -match '^\d+$' -and [int]$choice -ge 1 -and [int]$choice -le $availableScripts.Count) {
            $selectedEnv = $availableScripts[[int]$choice - 1]
            $scriptPath = Join-Path $PWD $selectedEnv.Script
            
            Write-Host "`nActivating $($selectedEnv.Name) environment..." -ForegroundColor Green
            . $scriptPath
            
            # Verify activation
            $envVarValue = Get-Item -Path "Env:$($selectedEnv.EnvVar)" -ErrorAction SilentlyContinue
            if ($envVarValue) {
                Write-Host "SUCCESS: $($selectedEnv.Name) environment activated!" -ForegroundColor Green
                Write-Host "Environment: $($envVarValue.Value)" -ForegroundColor Cyan
            } else {
                Write-Host "WARNING: $($selectedEnv.Name) activation script ran but environment not verified" -ForegroundColor Yellow
                Write-Host "Note: Some environments (pipenv, hatch) require interactive shells to activate properly" -ForegroundColor Gray
            }
        } else {
            Write-Host "`nSkipping activation." -ForegroundColor Gray
        }
    } elseif ($availableScripts.Count -eq 1) {
        # Only one script - auto-activate it
        $envConfig = $availableScripts[0]
        $scriptPath = Join-Path $PWD $envConfig.Script
        
        Write-Host "`nActivating $($envConfig.Name) environment..." -ForegroundColor Green
        . $scriptPath
        
        # Verify activation
        $envVarValue = Get-Item -Path "Env:$($envConfig.EnvVar)" -ErrorAction SilentlyContinue
        if ($envVarValue) {
            Write-Host "SUCCESS: $($envConfig.Name) environment activated!" -ForegroundColor Green
            Write-Host "Environment: $($envVarValue.Value)" -ForegroundColor Cyan
        } else {
            Write-Host "WARNING: $($envConfig.Name) activation script ran but environment not verified" -ForegroundColor Yellow
            Write-Host "Note: Some environments (pipenv, hatch) require interactive shells to activate properly" -ForegroundColor Gray
        }
    } else {
        Write-Host "`nNo activation script found. Create an environment first." -ForegroundColor Yellow
    }
}
