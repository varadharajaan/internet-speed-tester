<#
.SYNOPSIS
    Python Environment Manager - Complete environment lifecycle management for PowerShell

.DESCRIPTION
    A comprehensive PowerShell tool for managing Python environments across multiple tools.
    
    Quick Start:
    .\env_manager.ps1              # Interactive menu (default)
    .\env_manager.ps1 -Verify      # Check installed package managers
    .\env_manager.ps1 -Create      # Create new environment
    .\env_manager.ps1 -Delete      # Delete environment (current project)
    .\env_manager.ps1 -Delete -Force  # Delete from any project
    .\env_manager.ps1 -Switch      # Switch environments
    .\env_manager.ps1 -Help        # Show full help
    
    Supported Environment Types:
    - venv (built-in Python virtual environments)
    - conda (Anaconda/Miniconda environments)
    - poetry (Poetry dependency management)
    - pipenv (Pipenv package manager)
    - pdm (PDM package manager)
    - hatch (Hatch project manager)
    - pyenv (Python version manager)
    - docker (Dockerfile-based environments)
    
    Key Features:
    - Scan and list all Python environments (project-local and global)
    - Create new environments interactively
    - Switch between environments (generates activation scripts)
    - Delete environments safely (with Force option for cross-project cleanup)
    - Verify package manager availability
    - Supports both PowerShell (-flag) and Linux-style (--flag) arguments

.PARAMETER Project
    Project directory to scan (default: current directory)
    Example: -Project "C:\MyProject"

.PARAMETER Output
    Output format: menu (default), table, or json
    - menu: Interactive menu with environment details
    - table: Simple table view
    - json: JSON output for scripting

.PARAMETER Type
    Filter by environment types (comma-separated)
    Example: -Type conda,poetry

.PARAMETER OnlyProject
    Only scan project-local environments (skip global/system environments)

.PARAMETER Scan
    Which environments to scan: project, global, or all (default)
    - project: Only environments in current project folder
    - global: Only system-wide environments
    - all: Both project and global environments

.PARAMETER Verify
    Check which package managers are installed on your system
    Shows version info and installation status

.PARAMETER Install
    Show installation commands for ALL package managers
    (Use -Verify to show only missing ones)

.PARAMETER Delete
    Delete environments interactively with safety checks
    Default: Only deletes environments in current project
    Use with -Force to delete from any project folder

.PARAMETER SwitchEnv
    Switch between environments (alias: -Switch)
    Generates an activate_env.ps1 script you can source

.PARAMETER Deactivate
    Deactivate current active environment
    Generates a deactivate_env.ps1 script

.PARAMETER Create
    Create a new environment interactively
    Supports venv, conda, and poetry creation

.PARAMETER Force
    Used with -Delete to allow deleting local environments from ANY project folder
    Safety: Still blocks deletion of global system environments

.PARAMETER Help
    Show this detailed help message

.EXAMPLE
    .\env_manager.ps1
    
    # Interactive menu - default behavior
    # Scans all environments and shows interactive selection

.EXAMPLE
    .\env_manager.ps1 -Verify
    .\env_manager.ps1 --verify
    
    # Check package manager installation status
    # Shows which tools are installed and their versions

.EXAMPLE
    .\env_manager.ps1 -Install
    
    # Show installation commands for ALL package managers
    # Useful for setting up a new development machine

.EXAMPLE
    .\env_manager.ps1 -Create
    
    # Create new environment interactively
    # Walks you through venv, conda, or poetry setup

.EXAMPLE
    .\env_manager.ps1 -Delete
    
    # Delete environment (current project only)
    # Safe mode - only shows environments in current folder

.EXAMPLE
    .\env_manager.ps1 -Delete -Force
    .\env_manager.ps1 --delete --force
    
    # Delete local environments from ANY project folder
    # Still protects global system environments (miniconda3, etc.)

.EXAMPLE
    .\env_manager.ps1 -Switch
    
    # Switch to different environment
    # Creates activate_env.ps1 script to source

.EXAMPLE
    .\env_manager.ps1 -Deactivate
    
    # Deactivate current environment
    # Creates deactivate_env.ps1 script

.EXAMPLE
    .\env_manager.ps1 -Type conda -Output table
    
    # List only conda environments in table format

.EXAMPLE
    .\env_manager.ps1 -Scan project -OnlyProject -Output json
    
    # Get JSON output of only project-local environments
    # Useful for CI/CD pipelines

.NOTES
    Author: Converted from Python env_manager.py
    Version: 2.0
    
    Argument Styles:
    - PowerShell style: .\env_manager.ps1 -Delete -Force
    - Linux/Bash style: .\env_manager.ps1 --delete --force
    Both styles work! The script auto-converts -- to - internally.
    
    Safety Features:
    - Delete operations require confirmation (type 'DELETE')
    - Without -Force: Only current project environments can be deleted
    - With -Force: Any local project environment can be deleted
    - Global/system environments are always protected
    
    Generated Scripts:
    - activate_env.ps1: Created by -Switch command
    - deactivate_env.ps1: Created by -Deactivate command
    Source these scripts with: . .\activate_env.ps1

.LINK
    https://github.com/varadharajaan/internet-speed-tester
#>

[CmdletBinding()]
param(
    [Alias('p')]
    [string]$Project = ".",
    
    [Alias('o')]
    [ValidateSet("menu", "table", "json")]
    [string]$Output = "menu",
    
    [Alias('t')]
    [string[]]$Type = @(),
    
    [switch]$OnlyProject,
    
    [ValidateSet("project", "global", "all")]
    [string]$Scan = "all",
    
    [switch]$Verify,
    
    [switch]$Install,
    
    [switch]$Delete,
    
    [Alias('Switch')]
    [switch]$SwitchEnv,
    
    [switch]$Deactivate,
    
    [switch]$Create,
    
    [switch]$Force,
    
    [Alias('?', 'h')]
    [switch]$Help
)

# Quick check: If user tries to use -- arguments, auto-convert and re-run
$allArgs = @($PSBoundParameters.Keys) + @($args)
$hasDoubleDash = $false

foreach ($arg in $allArgs) {
    if ($arg -is [string] -and $arg -match '^--') {
        $hasDoubleDash = $true
        break
    }
}

# Also check the actual invocation line
if (-not $hasDoubleDash -and $MyInvocation.Line -match '\s--') {
    $hasDoubleDash = $true
}

if ($hasDoubleDash) {
    Write-Host "`nConverting double-dash arguments to single-dash...`n" -ForegroundColor Cyan
    
    # Get the original command line and convert -- to -
    $commandLine = $MyInvocation.Line
    $convertedLine = $commandLine -replace '\s--([a-zA-Z][\w-]*)', ' -$1'
    
    # Re-invoke with converted arguments
    Invoke-Expression $convertedLine
    exit $LASTEXITCODE
}

#region Helper Functions

function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO", "WARNING", "ERROR", "DEBUG", "SUCCESS")]
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "ERROR"   { "Red" }
        "WARNING" { "Yellow" }
        "SUCCESS" { "Green" }
        "DEBUG"   { "Gray" }
        default   { "White" }
    }
    
    if ($VerbosePreference -eq "Continue" -or $Level -ne "DEBUG") {
        Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
    }
}

function Test-CommandExists {
    param([string]$Command)
    
    $cmd = Get-Command $Command -ErrorAction SilentlyContinue
    if ($cmd) {
        return $true
    }
    
    # Also check for .ps1 script version (e.g., pyenv.ps1)
    $cmdPs1 = Get-Command "$Command.ps1" -ErrorAction SilentlyContinue
    return $null -ne $cmdPs1
}

function Invoke-CommandSafe {
    param(
        [string[]]$Command,
        [string]$WorkingDirectory = $null
    )
    
    try {
        # Check if command exists as .ps1 script (e.g., pyenv.ps1)
        $cmdObj = Get-Command $Command[0] -ErrorAction SilentlyContinue
        if (-not $cmdObj) {
            $cmdObj = Get-Command "$($Command[0]).ps1" -ErrorAction SilentlyContinue
        }
        
        if (-not $cmdObj) {
            return @{
                ExitCode = -1
                StdOut = ""
                StdErr = "Command not found"
            }
        }
        
        # If it's a PowerShell script, run it with PowerShell
        if ($cmdObj.CommandType -eq 'ExternalScript' -and $cmdObj.Source -like '*.ps1') {
            $arguments = if ($Command.Length -gt 1) { $Command[1..($Command.Length - 1)] } else { @() }
            
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = "powershell.exe"
            $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$($cmdObj.Source)`" $($arguments -join ' ')"
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError = $true
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow = $true
            
            if ($WorkingDirectory) {
                $psi.WorkingDirectory = $WorkingDirectory
            }
            
            $process = New-Object System.Diagnostics.Process
            $process.StartInfo = $psi
            $process.Start() | Out-Null
            
            $stdout = $process.StandardOutput.ReadToEnd()
            $stderr = $process.StandardError.ReadToEnd()
            $process.WaitForExit()
            
            return @{
                ExitCode = $process.ExitCode
                StdOut = $stdout.Trim()
                StdErr = $stderr.Trim()
            }
        }
        
        # Regular command execution
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Command[0]
        if ($Command.Length -gt 1) {
            $psi.Arguments = $Command[1..($Command.Length - 1)] -join " "
        }
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        
        if ($WorkingDirectory) {
            $psi.WorkingDirectory = $WorkingDirectory
        }
        
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.Start() | Out-Null
        
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        
        return @{
            ExitCode = $process.ExitCode
            StdOut = $stdout.Trim()
            StdErr = $stderr.Trim()
        }
    } catch {
        return @{
            ExitCode = -1
            StdOut = ""
            StdErr = $_.Exception.Message
        }
    }
}

#endregion

#region Environment Class

class PythonEnvironment {
    [int]$Id
    [string]$Name
    [string]$Type
    [string]$Location
    [bool]$IsActive
    [string]$ActivationScript
    [string]$Scope
    [hashtable]$Meta
    
    PythonEnvironment([string]$name, [string]$type, [string]$location) {
        $this.Name = $name
        $this.Type = $type.ToLower()
        if ($location) {
            $resolvedPath = (Resolve-Path $location -ErrorAction SilentlyContinue).Path
            $this.Location = if ($resolvedPath) { $resolvedPath } else { $location }
        } else {
            $this.Location = $null
        }
        $this.IsActive = $false
        $this.ActivationScript = $null
        $this.Scope = "unknown"
        $this.Meta = @{}
    }
    
    [hashtable] ToHashtable() {
        return @{
            id = $this.Id
            name = $this.Name
            type = $this.Type
            location = $this.Location
            is_active = $this.IsActive
            activation_script = $this.ActivationScript
            scope = $this.Scope
            meta = $this.Meta
        }
    }
}

#endregion

#region Environment Scanner

class EnvironmentScanner {
    [string]$ProjectDir
    [string[]]$TypeFilters
    [bool]$OnlyProject
    
    EnvironmentScanner([string]$projectDir, [string[]]$typeFilters, [bool]$onlyProject) {
        $resolvedPath = (Resolve-Path $projectDir -ErrorAction SilentlyContinue).Path
        $this.ProjectDir = if ($resolvedPath) { $resolvedPath } else { $projectDir }
        
        # Convert type filters to lowercase, handling both arrays and single values
        if ($typeFilters -and $typeFilters.Count -gt 0) {
            $this.TypeFilters = @($typeFilters | ForEach-Object { $_.ToLower() })
        } else {
            $this.TypeFilters = @()
        }
        
        $this.OnlyProject = $onlyProject
    }
    
    # Helper method to set activation script and scope for an environment
    [void] SetEnvironmentMetadata([PythonEnvironment]$env, [string]$scope) {
        $env.Scope = $scope
        $env.Meta['scope'] = $scope
        
        # Set activation script based on type
        switch ($env.Type) {
            "conda" {
                $env.ActivationScript = "conda activate `"$($env.Location)`""
            }
            { $_ -in @("venv", "poetry", "pipenv", "hatch", "pdm") } {
                $activatePs1 = Join-Path $env.Location "Scripts\Activate.ps1"
                if (Test-Path $activatePs1) {
                    $env.ActivationScript = ". `"$activatePs1`""
                }
            }
            "pyenv" {
                $env.ActivationScript = "# Pyenv: set via PYENV_VERSION or pyenv shell $($env.Name)"
            }
            default {
                $env.ActivationScript = $null
            }
        }
    }
    
    [array] ScanAll() {
        $environments = @()
        
        # Project environments
        $environments += $this.DetectProjectVenvs()
        $environments += $this.DetectProjectConda()
        $environments += $this.DetectPoetry()
        $environments += $this.DetectPipenv()
        $environments += $this.DetectPdm()
        $environments += $this.DetectHatch()
        $environments += $this.DetectDocker()
        
        # Global environments (unless OnlyProject is set)
        if (-not $this.OnlyProject) {
            $environments += $this.DetectGlobalConda()
            $environments += $this.DetectPyenv()
            
            # Detect global Python but exclude those in other environments
            $globalPythons = $this.DetectGlobalPython()
            $envLocations = $environments | ForEach-Object { $_.Location } | Where-Object { $_ }
            
            foreach ($py in $globalPythons) {
                $isPartOfEnv = $false
                $pyLocation = $py.Location
                $pyExecutable = $py.Meta['executable']
                
                foreach ($envLoc in $envLocations) {
                    if ($pyLocation -eq $envLoc -or $pyLocation.StartsWith("$envLoc\") -or 
                        ($pyExecutable -and $pyExecutable.StartsWith("$envLoc\"))) {
                        $isPartOfEnv = $true
                        break
                    }
                }
                
                if (-not $isPartOfEnv) {
                    $environments += $py
                }
            }
        }
        
        $environments = $this.Deduplicate($environments)
        $environments = $this.FilterTypes($environments)
        $this.MarkActive($environments)
        
        return $environments
    }
    
    [array] ScanOnlyProject() {
        $environments = @()
        
        $environments += $this.DetectProjectVenvs()
        $environments += $this.DetectProjectConda()
        $environments += $this.DetectPoetry()
        $environments += $this.DetectPipenv()
        $environments += $this.DetectPdm()
        $environments += $this.DetectHatch()
        $environments += $this.DetectDocker()
        
        $environments = $this.Deduplicate($environments)
        $environments = $this.FilterTypes($environments)
        $this.MarkActive($environments)
        
        return $environments
    }
    
    [array] ScanOnlyGlobal() {
        $environments = @()
        
        $environments += $this.DetectGlobalConda()
        $environments += $this.DetectPyenv()
        $environments += $this.DetectGlobalPython()
        
        $environments = $this.Deduplicate($environments)
        $environments = $this.FilterTypes($environments)
        $this.MarkActive($environments)
        
        return $environments
    }
    
    # Project environment detectors
    
    [array] DetectProjectVenvs() {
        $environments = @()
        
        if (-not (Test-Path $this.ProjectDir)) {
            return $environments
        }
        
        Get-ChildItem -Path $this.ProjectDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $activateScript = Join-Path $_.FullName "Scripts\activate"
            if (Test-Path $activateScript) {
                $env = [PythonEnvironment]::new($_.Name, "venv", $_.FullName)
                $environments += $env
            }
        }
        
        return $environments
    }
    
    [array] DetectProjectConda() {
        $environments = @()
        
        $paths = @(
            (Join-Path $this.ProjectDir ".conda"),
            (Join-Path $this.ProjectDir "env"),
            (Join-Path $this.ProjectDir "envs")
        )
        
        foreach ($path in $paths) {
            if (Test-Path (Join-Path $path "conda-meta")) {
                $env = [PythonEnvironment]::new((Split-Path $path -Leaf), "conda", $path)
                $this.SetEnvironmentMetadata($env, 'local')
                $environments += $env
            }
            
            if ($path.EndsWith("envs") -and (Test-Path $path)) {
                Get-ChildItem -Path $path -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    if (Test-Path (Join-Path $_.FullName "conda-meta")) {
                        $env = [PythonEnvironment]::new($_.Name, "conda", $_.FullName)
                        $this.SetEnvironmentMetadata($env, 'local')
                        $environments += $env
                    }
                }
            }
        }
        
        return $environments
    }
    
    [array] DetectPoetry() {
        $environments = @()
        
        $result = Invoke-CommandSafe -Command @("poetry", "env", "list", "--full-path") -WorkingDirectory $this.ProjectDir
        if ($result.ExitCode -eq 0 -and $result.StdOut) {
            $result.StdOut -split "`n" | ForEach-Object {
                $parts = $_ -split '\s+'
                $path = $parts[-1]
                if (Test-Path $path) {
                    $env = [PythonEnvironment]::new((Split-Path $path -Leaf), "poetry", $path)
                    $this.SetEnvironmentMetadata($env, 'local')
                    $environments += $env
                }
            }
        }
        
        # Check for local .venv
        $venvPath = Join-Path $this.ProjectDir ".venv"
        $pyprojectPath = Join-Path $this.ProjectDir "pyproject.toml"
        if ((Test-Path $venvPath) -and (Test-Path $pyprojectPath)) {
            $env = [PythonEnvironment]::new(".venv", "poetry", $venvPath)
            $environments += $env
        }
        
        return $environments
    }
    
    [array] DetectPipenv() {
        $environments = @()
        
        $pipfilePath = Join-Path $this.ProjectDir "Pipfile"
        if (Test-Path $pipfilePath) {
            $result = Invoke-CommandSafe -Command @("pipenv", "--venv") -WorkingDirectory $this.ProjectDir
            if ($result.ExitCode -eq 0 -and $result.StdOut -and (Test-Path $result.StdOut)) {
                $env = [PythonEnvironment]::new((Split-Path $result.StdOut -Leaf), "pipenv", $result.StdOut)
                $environments += $env
            }
        }
        
        return $environments
    }
    
    [array] DetectPdm() {
        $environments = @()
        
        $pdmDir = Join-Path $this.ProjectDir "__pypackages__"
        if (Test-Path $pdmDir) {
            $env = [PythonEnvironment]::new("__pypackages__", "pdm", $pdmDir)
            $environments += $env
        }
        
        return $environments
    }
    
    [array] DetectHatch() {
        $environments = @()
        
        $result = Invoke-CommandSafe -Command @("hatch", "env", "show") -WorkingDirectory $this.ProjectDir
        if ($result.ExitCode -eq 0 -and $result.StdOut) {
            $result.StdOut -split "`n" | ForEach-Object {
                if ($_ -match '^(.+?):\s*(.+)$') {
                    $name = $matches[1].Trim()
                    $path = $matches[2].Trim()
                    if (Test-Path $path) {
                        $env = [PythonEnvironment]::new($name, "hatch", $path)
                        $environments += $env
                    }
                }
            }
        }
        
        return $environments
    }
    
    [array] DetectDocker() {
        $environments = @()
        
        $dockerfilePath = Join-Path $this.ProjectDir "Dockerfile"
        if (Test-Path $dockerfilePath) {
            $content = Get-Content $dockerfilePath -Raw
            if ($content -match '(?i)from\s+.*python') {
                $env = [PythonEnvironment]::new("Dockerfile", "docker", $dockerfilePath)
                $environments += $env
            }
        }
        
        return $environments
    }
    
    # Global environment detectors
    
    [array] DetectGlobalConda() {
        $environments = @()
        
        $result = Invoke-CommandSafe -Command @("conda", "env", "list", "--json")
        if ($result.ExitCode -eq 0 -and $result.StdOut) {
            try {
                $data = $result.StdOut | ConvertFrom-Json
                foreach ($path in $data.envs) {
                    $env = [PythonEnvironment]::new((Split-Path $path -Leaf), "conda", $path)
                    
                    # Determine scope: local if in a project folder, global if in conda installation
                    $scope = 'global'
                    $isInCondaInstall = $path -match '\\miniconda3($|\\)' -or $path -match '\\anaconda3($|\\)'
                    $looksLikeProjectEnv = $path -match '\\.conda$' -or $path -match '\\env$' -or $path -match '\\venv$'
                    
                    if (-not $isInCondaInstall -and $looksLikeProjectEnv) {
                        $scope = 'local'
                    }
                    
                    $this.SetEnvironmentMetadata($env, $scope)
                    $environments += $env
                }
            } catch {
                Write-Log "Failed to parse conda env list JSON" -Level WARNING
            }
        }
        
        return $environments
    }
    
    [array] DetectPyenv() {
        $environments = @()
        
        $result = Invoke-CommandSafe -Command @("pyenv", "root")
        if ($result.ExitCode -eq 0 -and $result.StdOut) {
            $versionsDir = Join-Path $result.StdOut "versions"
            if (Test-Path $versionsDir) {
                Get-ChildItem -Path $versionsDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                    $env = [PythonEnvironment]::new($_.Name, "pyenv", $_.FullName)
                    $this.SetEnvironmentMetadata($env, 'global')
                    $environments += $env
                }
            }
        }
        
        return $environments
    }
    
    [array] DetectGlobalPython() {
        $environments = @()
        $seen = @{}
        
        # Current Python
        $currentPython = (Get-Command python -ErrorAction SilentlyContinue).Source
        if ($currentPython) {
            $currentPython = (Resolve-Path $currentPython).Path
            $env = [PythonEnvironment]::new("current-python", "global-python", (Split-Path $currentPython))
            $env.Meta['executable'] = $currentPython
            $this.SetEnvironmentMetadata($env, 'global')
            $environments += $env
            $seen[$currentPython] = $true
        }
        
        # Other Python commands
        foreach ($cmd in @("python", "python3", "py")) {
            $pythonPath = (Get-Command $cmd -ErrorAction SilentlyContinue).Source
            if ($pythonPath) {
                $pythonPath = (Resolve-Path $pythonPath).Path
                if (-not $seen.ContainsKey($pythonPath)) {
                    $env = [PythonEnvironment]::new($cmd, "global-python", (Split-Path $pythonPath))
                    $env.Meta['executable'] = $pythonPath
                    $this.SetEnvironmentMetadata($env, 'global')
                    $environments += $env
                    $seen[$pythonPath] = $true
                }
            }
        }
        
        return $environments
    }
    
    # Utility methods
    
    [array] Deduplicate([array]$environments) {
        $unique = @{}
        foreach ($env in $environments) {
            $key = "$($env.Type)|$($env.Location)"
            if (-not $unique.ContainsKey($key)) {
                $unique[$key] = $env
            }
        }
        return $unique.Values
    }
    
    [array] FilterTypes([array]$environments) {
        if ($this.TypeFilters.Count -eq 0) {
            return $environments
        }
        return $environments | Where-Object { $this.TypeFilters -contains $_.Type }
    }
    
    [void] MarkActive([array]$environments) {
        $venvPath = $env:VIRTUAL_ENV
        $condaPath = $env:CONDA_PREFIX
        $activePaths = @()
        
        if ($venvPath) { $activePaths += (Resolve-Path $venvPath -ErrorAction SilentlyContinue).Path }
        if ($condaPath) { $activePaths += (Resolve-Path $condaPath -ErrorAction SilentlyContinue).Path }
        
        $currentPython = (Get-Command python -ErrorAction SilentlyContinue).Source
        $currentDir = if ($currentPython) { Split-Path (Resolve-Path $currentPython).Path } else { $null }
        
        foreach ($env in $environments) {
            if ($activePaths -contains $env.Location) {
                $env.IsActive = $true
            } elseif ($env.Type -eq "global-python" -and $env.Meta['executable'] -eq $currentPython) {
                $env.IsActive = $true
            } elseif ($env.Location -and $currentDir -and $currentDir.StartsWith($env.Location)) {
                $env.IsActive = $true
            }
        }
    }
}

#endregion

#region Environment Creator

class EnvironmentCreator {
    [string]$ProjectDir
    
    EnvironmentCreator([string]$projectDir) {
        $resolvedPath = (Resolve-Path $projectDir -ErrorAction SilentlyContinue).Path
        $this.ProjectDir = if ($resolvedPath) { $resolvedPath } else { $projectDir }
    }
    
    [bool] CreateVenv([string]$name) {
        $venvPath = Join-Path $this.ProjectDir $name
        
        if (Test-Path $venvPath) {
            Write-Log "Directory '$name' already exists" -Level ERROR
            return $false
        }
        
        try {
            Write-Log "Creating venv '$name' at $venvPath" -Level INFO
            $result = Invoke-CommandSafe -Command @("python", "-m", "venv", $venvPath)
            
            if ($result.ExitCode -ne 0) {
                Write-Log "Failed to create venv: $($result.StdErr)" -Level ERROR
                return $false
            }
            
            Write-Log "Successfully created venv '$name'" -Level SUCCESS
            
            # Generate activation script
            $activateScript = Join-Path $this.ProjectDir "activate_venv.ps1"
            $activationCmd = Join-Path $venvPath "Scripts\Activate.ps1"
            
            "& `"$activationCmd`"" | Out-File -FilePath $activateScript -Encoding UTF8
            
            $border = "=" * 70
            Write-Host "`n$border"
            Write-Host "SUCCESS: Virtual environment created!" -ForegroundColor Green
            Write-Host "Location: $venvPath"
            Write-Host "`nTo activate in current shell, run:"
            Write-Host "  & `"$activationCmd`"" -ForegroundColor Cyan
            Write-Host "`nOr use the wrapper:"
            Write-Host "  .\env_wrapper.ps1" -ForegroundColor Cyan
            Write-Host "$border`n"
            
            return $true
        } catch {
            Write-Log "Failed to create venv: $_" -Level ERROR
            return $false
        }
    }
    
    [bool] CreateConda([string]$name, [string]$pythonVersion, [bool]$local) {
        try {
            if ($local) {
                $condaPath = Join-Path $this.ProjectDir ".conda"
                $cmd = @("conda", "create", "-p", $condaPath, "-y")
                
                if ($pythonVersion) {
                    $cmd += "python=$pythonVersion"
                } else {
                    $cmd += "python"
                }
                
                Write-Log "Creating local conda environment at '$condaPath'" -Level INFO
                $result = Invoke-CommandSafe -Command $cmd
                
                if ($result.ExitCode -ne 0) {
                    Write-Log "Failed to create conda environment: $($result.StdErr)" -Level ERROR
                    return $false
                }
                
                Write-Log "Successfully created local conda environment" -Level SUCCESS
                
                $activationCmd = "conda activate `"$condaPath`""
                $activateScript = Join-Path $this.ProjectDir "activate_conda.ps1"
                $activationCmd | Out-File -FilePath $activateScript -Encoding UTF8
                
                $border = "=" * 70
                Write-Host "`n$border"
                Write-Host "SUCCESS: Local Conda environment created!" -ForegroundColor Green
                Write-Host "Location: $condaPath"
                Write-Host "`nTo activate in current shell, run:"
                Write-Host "  $activationCmd" -ForegroundColor Cyan
                Write-Host "`nOr:"
                Write-Host "  conda activate ./.conda" -ForegroundColor Cyan
                Write-Host "$border`n"
                
            } else {
                $cmd = @("conda", "create", "-n", $name, "-y")
                
                if ($pythonVersion) {
                    $cmd += "python=$pythonVersion"
                } else {
                    $cmd += "python"
                }
                
                Write-Log "Creating global conda environment '$name'" -Level INFO
                $result = Invoke-CommandSafe -Command $cmd
                
                if ($result.ExitCode -ne 0) {
                    Write-Log "Failed to create conda environment: $($result.StdErr)" -Level ERROR
                    return $false
                }
                
                Write-Log "Successfully created global conda environment '$name'" -Level SUCCESS
                
                $activationCmd = "conda activate `"$name`""
                $activateScript = Join-Path $this.ProjectDir "activate_conda.ps1"
                $activationCmd | Out-File -FilePath $activateScript -Encoding UTF8
                
                $border = "=" * 70
                Write-Host "`n$border"
                Write-Host "SUCCESS: Conda environment created!" -ForegroundColor Green
                Write-Host "Name: $name"
                Write-Host "`nTo activate in current shell, run:"
                Write-Host "  $activationCmd" -ForegroundColor Cyan
                Write-Host "$border`n"
            }
            
            return $true
        } catch {
            Write-Log "Failed to create conda environment: $_" -Level ERROR
            return $false
        }
    }
    
    [bool] CreatePoetry() {
        try {
            $pyprojectPath = Join-Path $this.ProjectDir "pyproject.toml"
            
            if (Test-Path $pyprojectPath) {
                Write-Log "pyproject.toml already exists, running poetry install" -Level INFO
            } else {
                # Check for broken .venv
                $venvPath = Join-Path $this.ProjectDir ".venv"
                if (Test-Path $venvPath) {
                    Write-Log "Found existing .venv, removing it" -Level WARNING
                    Remove-Item -Path $venvPath -Recurse -Force
                }
                
                Write-Log "Initializing Poetry project" -Level INFO
                $result = Invoke-CommandSafe -Command @("poetry", "init", "-n") -WorkingDirectory $this.ProjectDir
                
                if ($result.ExitCode -ne 0) {
                    Write-Log "Failed to initialize Poetry: $($result.StdErr)" -Level ERROR
                    return $false
                }
            }
            
            Write-Log "Installing dependencies" -Level INFO
            $result = Invoke-CommandSafe -Command @("poetry", "install", "--no-root") -WorkingDirectory $this.ProjectDir
            
            if ($result.ExitCode -ne 0) {
                Write-Log "Failed to install dependencies: $($result.StdErr)" -Level ERROR
                return $false
            }
            
            Write-Log "Successfully initialized Poetry project" -Level SUCCESS
            
            $border = "=" * 70
            Write-Host "`n$border"
            Write-Host "SUCCESS: Poetry environment created!" -ForegroundColor Green
            Write-Host "`nTo activate in current shell, run:"
            Write-Host "  poetry shell" -ForegroundColor Cyan
            Write-Host "`nOr use commands with:"
            Write-Host "  poetry run <command>" -ForegroundColor Cyan
            Write-Host "$border`n"
            
            return $true
        } catch {
            Write-Log "Failed to create Poetry environment: $_" -Level ERROR
            return $false
        }
    }
    
    [bool] InteractiveCreate() {
        Write-Host "`n$('=' * 60)"
        Write-Host "Environment Creation Wizard" -ForegroundColor Cyan
        Write-Host "$('=' * 60)"
        
        Write-Host "`nAvailable environment types:"
        Write-Host "  1. venv (Python virtual environment)"
        Write-Host "  2. conda (Conda environment)"
        Write-Host "  3. poetry (Poetry dependency manager)"
        Write-Host "  4. pipenv (Pipenv package manager)"
        Write-Host "  5. pdm (PDM package manager)"
        Write-Host "  6. hatch (Hatch project manager)"
        Write-Host "  0. Cancel"
        
        $choice = Read-Host "`nSelect environment type [1-6, 0 to cancel]"
        
        if ($choice -eq "0" -or [string]::IsNullOrWhiteSpace($choice)) {
            Write-Log "Environment creation cancelled" -Level INFO
            return $false
        }
        
        switch ($choice) {
            "1" {
                $name = Read-Host "Enter venv name (default: venv)"
                if ([string]::IsNullOrWhiteSpace($name)) { $name = "venv" }
                return $this.CreateVenv($name)
            }
            "2" {
                if (-not (Test-CommandExists "conda")) {
                    Write-Log "Conda is not installed or not in PATH" -Level ERROR
                    return $false
                }
                
                Write-Host "`nConda environment location:"
                Write-Host "  1. Local (create .conda folder in current project)"
                Write-Host "  2. Global (create named environment in conda's envs folder)"
                $locChoice = Read-Host "Select location [1-2]"
                
                if ($locChoice -eq "1") {
                    $pythonVer = Read-Host "Enter Python version (e.g., 3.11, or press Enter for default)"
                    return $this.CreateConda("", $pythonVer, $true)
                } elseif ($locChoice -eq "2") {
                    $name = Read-Host "Enter conda environment name"
                    if ([string]::IsNullOrWhiteSpace($name)) {
                        Write-Log "Environment name is required" -Level ERROR
                        return $false
                    }
                    $pythonVer = Read-Host "Enter Python version (e.g., 3.11, or press Enter for default)"
                    return $this.CreateConda($name, $pythonVer, $false)
                } else {
                    Write-Log "Invalid selection" -Level ERROR
                    return $false
                }
            }
            "3" {
                if (-not (Test-CommandExists "poetry")) {
                    Write-Log "Poetry is not installed or not in PATH" -Level ERROR
                    return $false
                }
                
                $confirm = Read-Host "Initialize Poetry in current directory? [y/N]"
                if ($confirm -eq "y") {
                    return $this.CreatePoetry()
                } else {
                    Write-Log "Poetry initialization cancelled" -Level INFO
                    return $false
                }
            }
            default {
                Write-Log "Environment type not yet implemented in PowerShell version" -Level WARNING
                Write-Host "This environment type will be added in a future update." -ForegroundColor Yellow
                Write-Host "For now, please use the Python version for this type." -ForegroundColor Yellow
                return $false
            }
        }
        
        return $false
    }
}

#endregion

#region Environment Verifier

function Test-PackageManagers {
    param(
        [bool]$ShowAll = $false
    )
    
    $packageManagers = @{
        'venv' = @{
            Command = @('python', '-m', 'venv', '--help')
            Description = 'Python venv (built-in)'
            Required = $true
        }
        'conda' = @{
            Command = @('conda', '--version')
            Description = 'Conda package manager'
            Required = $false
        }
        'poetry' = @{
            Command = @('poetry', '--version')
            Description = 'Poetry dependency manager'
            Required = $false
        }
        'pipenv' = @{
            Command = @('pipenv', '--version')
            Description = 'Pipenv package manager'
            Required = $false
        }
        'pdm' = @{
            Command = @('pdm', '--version')
            Description = 'PDM package manager'
            Required = $false
        }
        'hatch' = @{
            Command = @('hatch', '--version')
            Description = 'Hatch project manager'
            Required = $false
        }
        'pyenv' = @{
            Command = @('pyenv', '--version')
            Description = 'Pyenv version manager'
            Required = $false
        }
        'docker' = @{
            Command = @('docker', '--version')
            Description = 'Docker containerization'
            Required = $false
        }
    }
    
    Write-Host "`n$('=' * 70)"
    Write-Host "Environment Package Manager Verification" -ForegroundColor Cyan
    Write-Host "$('=' * 70)"
    Write-Host "`nSystem: Windows $([System.Environment]::OSVersion.Version)"
    Write-Host "PowerShell: $($PSVersionTable.PSVersion)"
    
    $pythonVersion = (Invoke-CommandSafe -Command @('python', '--version')).StdOut
    Write-Host "Python: $pythonVersion"
    
    Write-Host "`n$('-' * 70)"
    Write-Host ("{0,-20} {1,-12} {2,-38}" -f 'Package Manager', 'Status', 'Version/Info')
    Write-Host "$('-' * 70)"
    
    $availableCount = 0
    $missingRequired = @()
    
    foreach ($name in $packageManagers.Keys | Sort-Object) {
        $pm = $packageManagers[$name]
        $result = Invoke-CommandSafe -Command $pm.Command
        
        $available = $result.ExitCode -eq 0
        
        # Special handling for venv - show Python version instead of help text
        if ($name -eq 'venv' -and $available) {
            $cleanPythonVersion = $pythonVersion -replace '^Python\s+', ''
            $version = "Python $cleanPythonVersion (built-in)"
        } elseif ($available) {
            $version = ($result.StdOut + $result.StdErr).Trim() -split "`n" | Select-Object -First 1
        } else {
            $version = "Not found"
        }
        
        $status = if ($available) { 
            "AVAILABLE"
            $availableCount++
        } elseif ($pm.Required) { 
            $missingRequired += $name
            "MISSING*"
        } else { 
            "NOT FOUND" 
        }
        
        $color = if ($available) { "Green" } elseif ($pm.Required) { "Red" } else { "Yellow" }
        
        Write-Host ("{0,-20} {1,-12} {2,-38}" -f $name, $status, $version.Substring(0, [Math]::Min(38, $version.Length))) -ForegroundColor $color
    }
    
    Write-Host "$('-' * 70)"
    Write-Host "`nSummary: $availableCount/$($packageManagers.Count) package managers available"
    
    if ($missingRequired.Count -gt 0) {
        Write-Host "`nWARNING: Required package managers missing: $($missingRequired -join ', ')" -ForegroundColor Red
        Write-Host "* Required package managers must be installed" -ForegroundColor Red
    }
    
    # Show installation instructions
    $missing = @()
    foreach ($name in $packageManagers.Keys) {
        $result = Invoke-CommandSafe -Command $packageManagers[$name].Command
        if ($result.ExitCode -ne 0) {
            $missing += $name
        }
    }
    
    Write-Host "`n$('-' * 70)"
    if ($ShowAll) {
        Write-Host "Installation Commands for All Package Managers" -ForegroundColor Cyan
        Write-Host "(Showing all tools regardless of installation status)" -ForegroundColor Gray
    } elseif ($missing.Count -gt 0) {
        Write-Host "Installation Commands for Missing Package Managers" -ForegroundColor Cyan
    } else {
        Write-Host "All Package Managers Installed!" -ForegroundColor Green
        return $availableCount, $missingRequired.Count
    }
    Write-Host "$('-' * 70)"
    
    $installGuide = @{
        'venv' = @{
            cmd = 'python -m pip install --upgrade pip'
            note = 'venv is built-in with Python 3.3+. If not working, reinstall Python.'
            status = 'Built-in'
        }
        'conda' = @{
            cmd = 'Invoke-WebRequest -Uri "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" -OutFile "$env:TEMP\Miniconda3-latest-Windows-x86_64.exe"; Start-Process -FilePath "$env:TEMP\Miniconda3-latest-Windows-x86_64.exe" -Wait'
            note = 'After installation, restart your terminal and run: conda init powershell'
            status = 'Installer'
        }
        'poetry' = @{
            cmd = '(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -'
            note = 'After installation, add to PATH: $env:APPDATA\Python\Scripts'
            status = 'Script Install'
        }
        'pipenv' = @{
            cmd = 'pip install --user pipenv'
            note = 'Ensure Python Scripts directory is in PATH'
            status = 'pip'
        }
        'pdm' = @{
            cmd = '(Invoke-WebRequest -Uri https://pdm-project.org/install-pdm.py -UseBasicParsing).Content | python -'
            note = 'After installation, restart terminal or run: pdm --version'
            status = 'Script Install'
        }
        'hatch' = @{
            cmd = 'pip install --user hatch'
            note = 'Ensure Python Scripts directory is in PATH'
            status = 'pip'
        }
        'pyenv' = @{
            cmd = 'Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" -OutFile "$env:TEMP\install-pyenv-win.ps1"; & "$env:TEMP\install-pyenv-win.ps1"'
            note = 'After installation, restart terminal. Add to PATH: $env:USERPROFILE\.pyenv\pyenv-win\bin and $env:USERPROFILE\.pyenv\pyenv-win\shims'
            status = 'Script Install'
        }
        'docker' = @{
            cmd = 'Start-Process "https://www.docker.com/products/docker-desktop"'
            note = 'Download and install Docker Desktop from the opened webpage. Requires WSL2 on Windows.'
            status = 'Manual'
        }
    }
    
    # Show installation for missing tools OR all tools if requested
    $toolsToShow = if ($ShowAll -or $missing.Count -eq 0) { 
        $packageManagers.Keys | Sort-Object 
    } else { 
        $missing 
    }
    
    foreach ($tool in $toolsToShow) {
        if ($installGuide.ContainsKey($tool)) {
            $isInstalled = $missing -notcontains $tool
            $statusColor = if ($isInstalled) { "Green" } else { "Yellow" }
            $statusText = if ($isInstalled) { "INSTALLED" } else { "Not Found" }
            
            Write-Host "`n[$tool] - $statusText" -ForegroundColor $statusColor
            Write-Host "  Install Method: $($installGuide[$tool].status)" -ForegroundColor Cyan
            Write-Host "  Command:" -ForegroundColor Cyan
            Write-Host "    $($installGuide[$tool].cmd)" -ForegroundColor White
            Write-Host "  Note:" -ForegroundColor Cyan
            Write-Host "    $($installGuide[$tool].note)" -ForegroundColor Gray
            Write-Host ""
        }
    }
    
    Write-Host "$('-' * 70)"
    Write-Host "`nQuick Install (Common Tools):" -ForegroundColor Cyan
    Write-Host "  # Install Poetry, Pipenv, PDM, Hatch via pip:"
    Write-Host "  pip install --user poetry pipenv pdm hatch" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "`n$('=' * 70)`n"
    
    return $availableCount, $missingRequired.Count
}

#endregion

#region Environment Presenter

function Show-EnvironmentMenu {
    param(
        [array]$Environments,
        [string]$ProjectDir
    )
    
    if ($Environments.Count -eq 0) {
        Write-Log "No environments found in project" -Level WARNING
        
        $choice = Read-Host "`nWould you like to create a new environment? [y/N]"
        if ($choice -eq "y") {
            $creator = [EnvironmentCreator]::new($ProjectDir)
            $success = $creator.InteractiveCreate()
            
            if ($success) {
                Write-Host "`nRe-scanning for environments..." -ForegroundColor Cyan
                # Re-scan would happen here
            }
        }
        return
    }
    
    # Assign IDs
    for ($i = 0; $i -lt $Environments.Count; $i++) {
        $Environments[$i].Id = $i + 1
    }
    
    Write-Host "`nDetected environments:"
    Write-Host "----------------------"
    
    # Group by type
    $grouped = $Environments | Group-Object -Property Type
    
    foreach ($group in $grouped) {
        Write-Host "`n[$($group.Name)]" -ForegroundColor Cyan
        foreach ($env in $group.Group) {
            $active = if ($env.IsActive) { "yes" } else { "no " }
            $activeColor = if ($env.IsActive) { "Green" } else { "Gray" }
            Write-Host ("  {0,3}. " -f $env.Id) -NoNewline
            Write-Host ("active={0} " -f $active) -ForegroundColor $activeColor -NoNewline
            Write-Host ("{0} - {1}" -f $env.Name, $env.Location)
        }
    }
    
    Write-Host "`nOptions:"
    Write-Host "  - Enter environment number to show activation commands"
    Write-Host "  - Enter 'c' or 'create' to create a new environment"
    Write-Host "  - Press Enter to skip"
    
    $selection = Read-Host "`nYour choice"
    
    if ([string]::IsNullOrWhiteSpace($selection)) {
        return
    }
    
    if ($selection -eq 'c' -or $selection -eq 'create') {
        $creator = [EnvironmentCreator]::new($ProjectDir)
        $creator.InteractiveCreate()
        return
    }
    
    try {
        $num = [int]$selection
        $env = $Environments | Where-Object { $_.Id -eq $num } | Select-Object -First 1
        
        if ($null -eq $env) {
            Write-Host "Invalid selection." -ForegroundColor Red
            return
        }
        
        Write-Host "`nActivation commands for: $($env.Name) ($($env.Type))" -ForegroundColor Cyan
        
        switch ($env.Type) {
            "conda" {
                Write-Host "PowerShell: conda activate `"$($env.Location)`"" -ForegroundColor Green
            }
            { $_ -in @("venv", "poetry", "pipenv", "hatch", "pyenv") } {
                $activatePs1 = Join-Path $env.Location "Scripts\Activate.ps1"
                Write-Host "PowerShell: & `"$activatePs1`"" -ForegroundColor Green
            }
            default {
                Write-Host "No direct activation command available for this type." -ForegroundColor Yellow
            }
        }
        
        Write-Host ""
        
    } catch {
        Write-Host "Invalid selection." -ForegroundColor Red
    }
}

class EnvironmentDeleter {
    [string]$ProjectDir
    
    EnvironmentDeleter([string]$projectDir) {
        $this.ProjectDir = $projectDir
    }
    
    [bool] DeleteVenv([PythonEnvironment]$env) {
        Write-Log "Deleting venv environment: $($env.Location)" -Level INFO
        
        try {
            if (Test-Path $env.Location) {
                Remove-Item -Path $env.Location -Recurse -Force -ErrorAction Stop
                Write-Log "Successfully deleted: $($env.Location)" -Level SUCCESS
                return $true
            } else {
                Write-Log "Path does not exist: $($env.Location)" -Level WARNING
                return $false
            }
        } catch {
            Write-Log "Failed to delete environment: $_" -Level ERROR
            
            # Try using cmd for stubborn directories
            try {
                Write-Log "Attempting deletion with cmd /c rmdir..." -Level DEBUG
                cmd /c "rmdir /s /q `"$($env.Location)`""
                
                if (-not (Test-Path $env.Location)) {
                    Write-Log "Successfully deleted using cmd" -Level SUCCESS
                    return $true
                }
            } catch {
                Write-Log "CMD deletion also failed: $_" -Level ERROR
            }
            
            return $false
        }
    }
    
    [bool] DeleteCondaEnv([PythonEnvironment]$env) {
        Write-Log "Deleting conda environment: $($env.Name) at $($env.Location)" -Level INFO
        
        try {
            # Use --prefix to delete by path instead of name (handles duplicate names)
            $result = Invoke-CommandSafe -Command "conda" -Arguments @("env", "remove", "-p", $env.Location, "-y")
            
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Successfully deleted conda environment: $($env.Name)" -Level SUCCESS
                
                # Also remove the directory if it still exists
                if (Test-Path $env.Location) {
                    Write-Log "Removing remaining directory: $($env.Location)" -Level DEBUG
                    try {
                        Remove-Item -Path $env.Location -Recurse -Force -ErrorAction Stop
                    } catch {
                        Write-Log "Warning: Directory may still exist: $_" -Level WARNING
                    }
                }
                
                return $true
            } else {
                Write-Log "conda env remove failed, trying direct directory deletion" -Level WARNING
                # Fallback to directory deletion
                return $this.DeleteVenv($env)
            }
        } catch {
            Write-Log "Error deleting conda environment: $_" -Level ERROR
            return $false
        }
    }
    
    [bool] DeletePoetryEnv([PythonEnvironment]$env) {
        Write-Log "Deleting poetry environment at: $($env.Location)" -Level INFO
        
        # Poetry environments are just directories, delete like venv
        return $this.DeleteVenv($env)
    }
    
    [bool] DeletePipenvEnv([PythonEnvironment]$env) {
        Write-Log "Deleting pipenv environment: $($env.Name)" -Level INFO
        
        try {
            # Change to project directory if available
            $originalLocation = Get-Location
            
            if (Test-Path $this.ProjectDir) {
                Set-Location $this.ProjectDir
            }
            
            $result = Invoke-CommandSafe -Command "pipenv" -Arguments @("--rm")
            
            Set-Location $originalLocation
            
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Successfully deleted pipenv environment" -Level SUCCESS
                return $true
            } else {
                Write-Log "Failed to delete pipenv environment" -Level ERROR
                return $false
            }
        } catch {
            Write-Log "Error deleting pipenv environment: $_" -Level ERROR
            return $false
        }
    }
    
    [bool] DeletePdmEnv([PythonEnvironment]$env) {
        Write-Log "Deleting PDM environment at: $($env.Location)" -Level INFO
        
        # PDM environments are directories, delete like venv
        return $this.DeleteVenv($env)
    }
    
    [bool] DeleteEnvironment([PythonEnvironment]$env) {
        switch ($env.Type) {
            "venv"   { return $this.DeleteVenv($env) }
            "conda"  { return $this.DeleteCondaEnv($env) }
            "poetry" { return $this.DeletePoetryEnv($env) }
            "pipenv" { return $this.DeletePipenvEnv($env) }
            "pdm"    { return $this.DeletePdmEnv($env) }
            "hatch"  { return $this.DeleteVenv($env) }
            default {
                Write-Log "Cannot delete environment of type: $($env.Type)" -Level ERROR
            }
        }
        return $false
    }
    
    [bool] InteractiveDelete([array]$environments, [bool]$allowAnyLocal = $false) {
        # Filter to only local/project environments (safety constraint)
        # Allow deletion based on Force flag:
        # - Without Force: Only envs in current project directory
        # - With Force: Any env with Scope="local" (any project folder)
        $localEnvs = if ($allowAnyLocal) {
            $environments | Where-Object { $_.Scope -eq "local" }
        } else {
            $environments | Where-Object {
                $_.Scope -eq "local" -and $_.Location.StartsWith($this.ProjectDir)
            }
        }
        
        if ($localEnvs.Count -eq 0) {
            Write-Host "`nNo local/project environments found to delete." -ForegroundColor Yellow
            if ($allowAnyLocal) {
                Write-Host "No local environments found across any projects." -ForegroundColor Yellow
            } else {
                Write-Host "For safety, only environments in the current project can be deleted." -ForegroundColor Yellow
                Write-Host "Use -Force flag to delete local environments from other project folders." -ForegroundColor Yellow
            }
            return $false
        }
        
        Write-Host "`n=== DELETE ENVIRONMENT ===" -ForegroundColor Red
        Write-Host "WARNING: This will permanently delete the selected environment!" -ForegroundColor Red
        Write-Host ""
        
        # Show table of deletable environments
        for ($i = 0; $i -lt $localEnvs.Count; $i++) {
            $localEnvs[$i].Id = $i + 1
        }
        
        $header = "{0,-4} {1,-15} {2,-20} {3}" -f 'ID', 'Type', 'Name', 'Location'
        Write-Host $header
        Write-Host ("-" * 100)
        
        foreach ($env in $localEnvs) {
            $line = "{0,-4} {1,-15} {2,-20} {3}" -f $env.Id, $env.Type, $env.Name, $env.Location
            Write-Host $line
        }
        
        Write-Host ""
        $selection = Read-Host "Enter environment ID to delete (or 'q' to cancel)"
        
        if ($selection -eq 'q') {
            Write-Host "Cancelled." -ForegroundColor Yellow
            return $false
        }
        
        try {
            $id = [int]$selection
            $env = $localEnvs | Where-Object { $_.Id -eq $id } | Select-Object -First 1
            
            if (-not $env) {
                Write-Host "Invalid ID: $id" -ForegroundColor Red
                return $false
            }
            
            Write-Host ""
            Write-Host "You are about to delete:" -ForegroundColor Red
            Write-Host "  Type: $($env.Type)" -ForegroundColor Yellow
            Write-Host "  Name: $($env.Name)" -ForegroundColor Yellow
            Write-Host "  Location: $($env.Location)" -ForegroundColor Yellow
            Write-Host ""
            
            $confirm = Read-Host "Type 'DELETE' to confirm"
            
            if ($confirm -ne 'DELETE') {
                Write-Host "Deletion cancelled." -ForegroundColor Yellow
                return $false
            }
            
            Write-Host ""
            return $this.DeleteEnvironment($env)
            
        } catch {
            Write-Host "Invalid input: $_" -ForegroundColor Red
            return $false
        }
    }
}

class EnvironmentSwitcher {
    [string]$ProjectDir
    
    EnvironmentSwitcher([string]$projectDir) {
        $this.ProjectDir = $projectDir
    }
    
    [PythonEnvironment] GetActiveEnvironment([array]$environments) {
        return $environments | Where-Object { $_.IsActive } | Select-Object -First 1
    }
    
    [bool] GenerateDeactivationScript() {
        $activeEnv = $null
        
        # Check for active conda environment
        if ($env:CONDA_PREFIX) {
            Write-Log "Active conda environment detected: $env:CONDA_PREFIX" -Level INFO
            $activeEnv = @{
                Type = "conda"
                Location = $env:CONDA_PREFIX
                Name = $env:CONDA_DEFAULT_ENV
            }
        }
        # Check for active venv/poetry/etc
        elseif ($env:VIRTUAL_ENV) {
            Write-Log "Active virtual environment detected: $env:VIRTUAL_ENV" -Level INFO
            $activeEnv = @{
                Type = "venv"
                Location = $env:VIRTUAL_ENV
                Name = Split-Path $env:VIRTUAL_ENV -Leaf
            }
        }
        else {
            Write-Host "No active Python environment detected." -ForegroundColor Yellow
            return $false
        }
        
        # Generate deactivation script
        $scriptPath = Join-Path $this.ProjectDir "deactivate_env.ps1"
        
        $scriptContent = @"
# Auto-generated deactivation script
# Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

Write-Host "Deactivating environment: $($activeEnv.Name)" -ForegroundColor Cyan

"@
        
        if ($activeEnv.Type -eq "conda") {
            $scriptContent += @"
# Deactivate conda environment
if (Get-Command conda -ErrorAction SilentlyContinue) {
    conda deactivate
    Write-Host "Conda environment deactivated." -ForegroundColor Green
} else {
    Write-Host "WARNING: conda command not found" -ForegroundColor Yellow
}
"@
        } else {
            $scriptContent += @"
# Deactivate virtual environment
if (Get-Command deactivate -ErrorAction SilentlyContinue) {
    deactivate
    Write-Host "Virtual environment deactivated." -ForegroundColor Green
} else {
    Write-Host "WARNING: deactivate command not found" -ForegroundColor Yellow
}
"@
        }
        
        try {
            Set-Content -Path $scriptPath -Value $scriptContent -Force
            Write-Host "`nDeactivation script generated: $scriptPath" -ForegroundColor Green
            Write-Host "Run it with: . $scriptPath" -ForegroundColor Cyan
            Write-Host "Or source it with: & $scriptPath" -ForegroundColor Cyan
            return $true
        } catch {
            Write-Log "Failed to generate deactivation script: $_" -Level ERROR
            return $false
        }
    }
    
    [bool] InteractiveSwitch([array]$environments) {
        if ($environments.Count -eq 0) {
            Write-Host "`nNo environments found to switch to." -ForegroundColor Yellow
            return $false
        }
        
        Write-Host "`n=== SWITCH ENVIRONMENT ===" -ForegroundColor Cyan
        
        $activeEnv = $this.GetActiveEnvironment($environments)
        if ($activeEnv) {
            Write-Host "Currently active: $($activeEnv.Name) ($($activeEnv.Type))" -ForegroundColor Green
            Write-Host ""
        }
        
        # Show table of available environments
        for ($i = 0; $i -lt $environments.Count; $i++) {
            $environments[$i].Id = $i + 1
        }
        
        $header = "{0,-4} {1,-15} {2,-7} {3,-20} {4}" -f 'ID', 'Type', 'Active', 'Name', 'Location'
        Write-Host $header
        Write-Host ("-" * 100)
        
        foreach ($env in $environments) {
            $active = if ($env.IsActive) { "yes" } else { "no" }
            $line = "{0,-4} {1,-15} {2,-7} {3,-20} {4}" -f $env.Id, $env.Type, $active, $env.Name, $env.Location
            
            if ($env.IsActive) {
                Write-Host $line -ForegroundColor Green
            } else {
                Write-Host $line
            }
        }
        
        Write-Host ""
        $selection = Read-Host "Enter environment ID to switch to (or 'q' to cancel)"
        
        if ($selection -eq 'q') {
            Write-Host "Cancelled." -ForegroundColor Yellow
            return $false
        }
        
        try {
            $id = [int]$selection
            $env = $environments | Where-Object { $_.Id -eq $id } | Select-Object -First 1
            
            if (-not $env) {
                Write-Host "Invalid ID: $id" -ForegroundColor Red
                return $false
            }
            
            if ($env.IsActive) {
                Write-Host "`nEnvironment '$($env.Name)' is already active." -ForegroundColor Yellow
                return $false
            }
            
            # Generate activation script
            $scriptPath = Join-Path $this.ProjectDir "activate_env.ps1"
            $activationScript = $env.ActivationScript
            
            if (-not $activationScript) {
                Write-Host "No activation script available for this environment." -ForegroundColor Red
                return $false
            }
            
            $scriptContent = @"
# Auto-generated activation script
# Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
# Target: $($env.Name) ($($env.Type))

Write-Host "Activating environment: $($env.Name)" -ForegroundColor Cyan

# First deactivate any active environment
if (`$env:CONDA_PREFIX) {
    Write-Host "Deactivating conda environment..." -ForegroundColor Yellow
    conda deactivate
} elseif (`$env:VIRTUAL_ENV) {
    Write-Host "Deactivating virtual environment..." -ForegroundColor Yellow
    deactivate
}

# Activate new environment
$activationScript

Write-Host "Environment activated: $($env.Name)" -ForegroundColor Green
Write-Host "Type: $($env.Type)" -ForegroundColor Cyan
Write-Host "Location: $($env.Location)" -ForegroundColor Cyan
"@
            
            Set-Content -Path $scriptPath -Value $scriptContent -Force
            
            Write-Host "`nActivation script generated: $scriptPath" -ForegroundColor Green
            Write-Host "Run it with: . $scriptPath" -ForegroundColor Cyan
            Write-Host "Or source it with: & $scriptPath" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "Note: Script-based activation will work in the current session." -ForegroundColor Yellow
            
            return $true
            
        } catch {
            Write-Host "Invalid input: $_" -ForegroundColor Red
            return $false
        }
    }
}

function Show-EnvironmentTable {
    param([array]$Environments)
    
    if ($Environments.Count -eq 0) {
        Write-Host "WARNING: No environments found." -ForegroundColor Yellow
        return
    }
    
    for ($i = 0; $i -lt $Environments.Count; $i++) {
        $Environments[$i].Id = $i + 1
    }
    
    Write-Host "`nDetected environments:"
    Write-Host "----------------------"
    
    $header = "{0,-4} {1,-15} {2,-7} {3,-20} {4}" -f 'ID', 'Type', 'Active', 'Name', 'Location'
    Write-Host $header
    Write-Host ("-" * 100)
    
    foreach ($env in $Environments) {
        $active = if ($env.IsActive) { "yes" } else { "no" }
        $line = "{0,-4} {1,-15} {2,-7} {3,-20} {4}" -f $env.Id, $env.Type, $active, $env.Name, $env.Location
        
        if ($env.IsActive) {
            Write-Host $line -ForegroundColor Green
        } else {
            Write-Host $line
        }
    }
    
    Write-Host ""
}

function Show-EnvironmentJson {
    param([array]$Environments)
    
    $jsonArray = $Environments | ForEach-Object { $_.ToHashtable() }
    $json = $jsonArray | ConvertTo-Json -Depth 10
    Write-Host $json
}

#endregion

#region Main Execution

# Note: Double dash (--) arguments are converted to single dash (-) via preprocessing at script start

# Handle -Help flag
if ($Help) {
    Get-Help $PSCommandPath -Detailed
    exit 0
}

# Ensure project directory exists
if (-not (Test-Path $Project)) {
    Write-Log "Project directory '$Project' does not exist" -Level WARNING
    
    if (-not $Verify) {
        $createDir = Read-Host "Would you like to create it? [y/N]"
        if ($createDir -eq "y") {
            try {
                New-Item -ItemType Directory -Path $Project -Force | Out-Null
                Write-Log "Created directory: $((Resolve-Path $Project).Path)" -Level SUCCESS
            } catch {
                Write-Log "Failed to create directory: $_" -Level ERROR
                exit 1
            }
        } else {
            Write-Log "Exiting" -Level INFO
            exit 0
        }
    }
}

# Handle -Verify or -Install (both - and -- work automatically in PowerShell)
if ($Verify -or $Install) {
    $showAll = $Install  # -Install shows all, -Verify shows only missing
    Test-PackageManagers -ShowAll:$showAll | Out-Null
    exit 0
}

# Handle --Create
if ($Create) {
    $creator = [EnvironmentCreator]::new($Project)
    $success = $creator.InteractiveCreate()
    exit $(if ($success) { 0 } else { 1 })
}

# Scan environments (needed for Delete, Switch, Deactivate, and display modes)
Write-Log "Scanning environments in: $Project" -Level DEBUG

# Convert switch parameter to bool for EnvironmentScanner constructor
$scanner = [EnvironmentScanner]::new($Project, $Type, [bool]$OnlyProject)

# Use switch expression for scanning (avoid conflict with -Switch parameter)
switch ($Scan) {
    "project" { 
        $environments = $scanner.ScanOnlyProject()
    }
    "global" { 
        $environments = $scanner.ScanOnlyGlobal()
    }
    default { 
        $environments = $scanner.ScanAll()
    }
}

Write-Log "Found $($environments.Count) environments" -Level DEBUG

# Handle --Delete
if ($Delete.IsPresent) {
    $deleter = [EnvironmentDeleter]::new($Project)
    $success = $deleter.InteractiveDelete($environments, $Force.IsPresent)
    exit $(if ($success) { 0 } else { 1 })
}

# Handle --Switch
if ($SwitchEnv.IsPresent) {
    $switcher = [EnvironmentSwitcher]::new($Project)
    $success = $switcher.InteractiveSwitch($environments)
    exit $(if ($success) { 0 } else { 1 })
}

# Handle --Deactivate
if ($Deactivate.IsPresent) {
    $switcher = [EnvironmentSwitcher]::new($Project)
    $success = $switcher.GenerateDeactivationScript()
    exit $(if ($success) { 0 } else { 1 })
}

# Display results
switch ($Output) {
    "menu" {
        Show-EnvironmentMenu -Environments $environments -ProjectDir $Project
        Write-Host "`nJSON output:" -ForegroundColor Cyan
        Show-EnvironmentJson -Environments $environments
    }
    "table" {
        Show-EnvironmentTable -Environments $environments
        Write-Host "`nJSON output:" -ForegroundColor Cyan
        Show-EnvironmentJson -Environments $environments
    }
    "json" {
        Show-EnvironmentJson -Environments $environments
    }
}

#endregion
