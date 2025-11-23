# Auto-generated activation script
# Generated: 2025-11-23 17:48:27
# Target: aws-infra-setup (conda)

Write-Host "Activating environment: aws-infra-setup" -ForegroundColor Cyan

# First deactivate any active environment
if ($env:CONDA_PREFIX) {
    Write-Host "Deactivating conda environment..." -ForegroundColor Yellow
    conda deactivate
} elseif ($env:VIRTUAL_ENV) {
    Write-Host "Deactivating virtual environment..." -ForegroundColor Yellow
    deactivate
}

# Activate new environment
conda activate "C:\Users\varad\miniconda3\envs\aws-infra-setup"

Write-Host "Environment activated: aws-infra-setup" -ForegroundColor Green
Write-Host "Type: conda" -ForegroundColor Cyan
Write-Host "Location: C:\Users\varad\miniconda3\envs\aws-infra-setup" -ForegroundColor Cyan
