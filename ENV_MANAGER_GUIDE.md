# Environment Manager - Complete Guide

## Table of Contents
1. [Overview](#overview)
2. [Installation](#installation)
3. [Getting Help](#getting-help)
4. [Command Reference](#command-reference)
5. [Environment Types](#environment-types)
6. [PowerShell Wrapper](#powershell-wrapper)
7. [Advanced Usage](#advanced-usage)
8. [Understanding Limitations](#understanding-limitations)
9. [Troubleshooting](#troubleshooting)
10. [Complete Examples](#complete-examples)

---

## Overview

**env_manager.py** is a complete Python environment lifecycle management tool with support for 8 environment types.

**Key Capabilities:**
- ✅ **Verify** - Check which package managers are installed with installation instructions
- ✅ **Create** - Interactive wizard for creating 7 environment types
- ✅ **Switch** - Seamlessly switch between active environments
- ✅ **Deactivate** - Deactivate current environment safely
- ✅ **Delete** - Remove environments with flexible selection (single, multiple, range, all)
- ✅ **Scan** - Discover all project-local and system-wide environments
- ✅ **Multiple Formats** - Output as menu, table, TUI, or JSON

**Supported Environment Types:**
1. **venv** - Python built-in virtual environments
2. **conda** - Conda package manager environments
3. **poetry** - Poetry dependency manager
4. **pipenv** - Pipenv virtual environments
5. **pdm** - PDM package manager
6. **hatch** - Hatch project manager
7. **pyenv** - Python version manager
8. **docker** - Docker containers (detection only)

---

## Installation

### Prerequisites
- **Python 3.7+** installed
- **PowerShell** (Windows) or Bash/Zsh (Unix)
- **Git** (optional, for repository cloning)

### Setup Steps
```powershell
# 1. Download or clone the repository
git clone <repository-url>
cd <project-directory>

# 2. Verify the files exist
ls env_manager.py
ls env_wrapper.ps1

# 3. Check installed package managers
python env_manager.py --verify

# 4. Ready to use!
```

No additional dependencies required - uses only Python standard library.

---

## Getting Help

### Python Script Help
```powershell
python env_manager.py --help
```

**Output includes:**
- Full command syntax
- All available flags and options
- Usage examples
- Supported environment types
- Notes about subprocess limitations

### PowerShell Wrapper Help
```powershell
# Short help
.\env_wrapper.ps1 -Action help

# Detailed help with examples
Get-Help .\env_wrapper.ps1 -Detailed

# Full help with parameter details
Get-Help .\env_wrapper.ps1 -Full
```

---

## Command Reference

### 1. Verify Package Managers (`--verify`)

**Purpose:** Check which environment management tools are installed and get installation instructions.

**Usage:**
```powershell
python env_manager.py --verify
```

**Output:**
- ✅ **Available** package managers with version numbers
- ❌ **Missing** package managers with platform-specific installation commands
- **Exit Code:** 0 (all required available) or 1 (missing required tools)

**Example Output:**
```
======================================================================
Package Manager Verification Report
======================================================================

AVAILABLE (7/8):
  ✅ venv (built-in) - Python 3.13.5
  ✅ conda - conda 25.3.1
  ✅ poetry - Poetry (version 2.2.1)
  ✅ pipenv - pipenv, version 2025.0.4
  ✅ pdm - PDM, version 2.26.1
  ✅ hatch - Hatch, version 1.15.1
  ✅ pyenv - pyenv 3.1.1

MISSING (1/8):
  ❌ docker - Docker containerization

======================================================================
Installation Instructions for Missing Tools
======================================================================

  docker:
    Download from: https://www.docker.com/products/docker-desktop

======================================================================
```

---

### 2. Create Environment (Interactive)

**Purpose:** Interactive wizard to create new environments.

**Usage:**
```powershell
# Using Python directly
python env_manager.py

# Using wrapper (automatically activates after creation)
.\env_wrapper.ps1
```

**Process:**
1. Lists all available environment types (1-7)
2. Prompts for selection
3. Requests environment-specific details (name, version, etc.)
4. Creates environment and configuration files
5. (Poetry only) Generates activation script
6. Re-scans and displays created environment

**Creation Options:**
```
Select environment type:
1. venv      - Python built-in virtual environment
2. conda     - Conda environment
3. poetry    - Poetry dependency manager
4. pipenv    - Pipenv virtual environment
5. pdm       - PDM package manager
6. hatch     - Hatch project manager
7. pyenv     - Install specific Python version
```

**Generated Files:**
| Environment | Files Created |
|-------------|---------------|
| venv | `.venv/` directory |
| conda | Environment in `$CONDA_PREFIX/envs/<name>` |
| poetry | `pyproject.toml`, `poetry.lock`, `activate_poetry.ps1` |
| pipenv | `Pipfile`, `Pipfile.lock` |
| pdm | `pyproject.toml`, `pdm.lock` |
| hatch | Full project structure with `pyproject.toml` |
| pyenv | Python version in `~/.pyenv/versions/` |

---

### 3. Switch Environments (`--switch`)

**Purpose:** Switch from current active environment to another.

**Usage:**
```powershell
# Manual (generates script)
python env_manager.py --switch
.\switch_env.ps1

# Wrapper (auto-executes)
.\env_wrapper.ps1 -Action switch
```

**Process:**
1. Detects currently active environment (if any)
2. Scans for all available environments (local + global)
3. Displays numbered list
4. Prompts for selection (1-N or 'q' to quit)
5. Generates `switch_env.ps1` containing:
   - Deactivation command for current environment
   - Activation command for target environment
6. (Wrapper) Auto-executes script in current shell

**Example Session:**
```
======================================================================
Environment Switcher
======================================================================

Currently Active Environment:
  Type: venv/poetry/pipenv
  Name: aws-infra-setup-IEMvNy1b-py3.13
  Path: C:\Users\...\virtualenvs\aws-infra-setup-IEMvNy1b-py3.13

======================================================================
Available Environments to Switch To:
======================================================================
1. miniconda3          Type: conda
   Location: C:\Users\varad\miniconda3
2. aws-infra-setup     Type: conda
   Location: C:\Users\varad\miniconda3\envs\aws-infra-setup
3. .venv               Type: venv
   Location: C:\...\project\.venv

Select environment to activate [1-3] or 'q' to quit: 2

======================================================================
Environment Switch Script Generated
======================================================================

To switch environments, run:

    .\switch_env.ps1

Commands in script:
  deactivate
  conda activate "aws-infra-setup"
```

---

### 4. Deactivate Environment (`--deactivate`)

**Purpose:** Deactivate the currently active environment.

**Usage:**
```powershell
# Manual (generates script)
python env_manager.py --deactivate
.\deactivate_env.ps1

# Wrapper (auto-executes)
.\env_wrapper.ps1 -Action deactivate
```

**Behavior:**
- Detects environment type (venv/poetry/pipenv vs conda)
- Generates appropriate command:
  - `deactivate` for venv-based environments
  - `conda deactivate` for conda environments
- Saves to `deactivate_env.ps1`
- (Wrapper) Auto-executes in current shell
- Displays error if no environment is active

**Example Output:**
```
======================================================================
Environment Deactivator
======================================================================

Currently Active Environment:
  Type: conda
  Name: aws-infra-setup
  Path: C:\Users\varad\miniconda3\envs\aws-infra-setup

======================================================================
Deactivation Script Generated
======================================================================

To deactivate the current environment, run:

    .\deactivate_env.ps1

Command: conda deactivate

======================================================================
```

---

### 5. Delete Environments (`--delete`)

**Purpose:** Interactive deletion of local/project environments.

**Usage:**
```powershell
python env_manager.py --delete
```

**Selection Syntax:**
```
Single:     1           Delete environment #1
Multiple:   1,3,5       Delete environments 1, 3, and 5
Range:      1-3         Delete environments 1, 2, and 3
All:        all         Delete all listed environments
Quit:       q           Cancel deletion
```

**Process:**
1. Scans for **local environments only** (not global)
2. Displays numbered list
3. Prompts for selection
4. Validates input
5. Attempts deletion for each selected environment
6. Handles errors (permissions, locked files)
7. Reports summary (deleted count, failed count)

**Safety Features:**
- ✅ Only scans local/project environments (protects global environments)
- ✅ Handles Windows permission errors with chmod fallback
- ✅ Provides helpful error messages and tips
- ✅ Non-destructive for global conda environments and system Python

**Example Session:**
```
======================================================================
Environment Deleter
======================================================================

Local Environments:
  1. .venv (venv) - C:\project\.venv
  2. .conda (conda) - C:\project\.conda

Select environments to delete [1-2, ranges (1-2), 'all', or 'q' to quit]: 1

Deleting environment at C:\project\.venv...
SUCCESS: Deleted C:\project\.venv

======================================================================
Deletion Summary: 1 deleted, 0 failed
======================================================================
```

---

### 6. Scan Environments (Default)

**Purpose:** Discover and display all environments.

**Usage:**
```powershell
# Scan all environments (default)
python env_manager.py

# Scan only project-local
python env_manager.py --scan project

# Scan only global/system-wide
python env_manager.py --scan global

# Filter by type
python env_manager.py --type conda --type poetry

# Output as JSON
python env_manager.py --output json
```

**Scan Modes:**
| Mode | Flag | Description |
|------|------|-------------|
| All | `--scan all` (default) | Both project and global environments |
| Project | `--scan project` | Only local/project environments |
| Global | `--scan global` | Only system-wide environments |

**Output Formats:**
| Format | Flag | Description |
|--------|------|-------------|
| Menu | `--output menu` (default) | Interactive menu with commands |
| Table | `--output table` | Tabular ASCII format |
| TUI | `--output tui` | Grouped text UI |
| JSON | `--output json` | Machine-readable JSON |

**Type Filtering:**
```powershell
# Only conda
python env_manager.py --type conda

# Multiple types
python env_manager.py --type conda --type poetry --type venv
```

---

## Environment Types

### 1. venv (Python Built-in)

**Description:** Python's standard library virtual environment module.

**Pros:**
- ✅ No installation required (built into Python)
- ✅ Lightweight and fast
- ✅ Standard and well-documented
- ✅ Works everywhere Python is installed

**Cons:**
- ❌ Python packages only (no system dependencies)
- ❌ No built-in dependency resolution

**Creation:**
```powershell
python env_manager.py
# Select: 1. venv
```

**Details:**
- **Location:** `<project>/.venv/`
- **Command:** `python -m venv .venv`
- **Activation (Windows):** `.\.venv\Scripts\Activate.ps1`
- **Activation (Unix):** `source .venv/bin/activate`
- **Best For:** Simple projects, learning, quick prototypes

---

### 2. conda

**Description:** Cross-platform package and environment manager.

**Pros:**
- ✅ Manages Python AND non-Python dependencies
- ✅ Excellent for data science (numpy, scipy, etc.)
- ✅ Multiple Python versions per environment
- ✅ Binary package distribution (faster installs)

**Cons:**
- ❌ Larger installation size
- ❌ Can be slower than pip

**Creation:**
```powershell
python env_manager.py
# Select: 2. conda
# Enter environment name
# Optionally specify Python version
```

**Details:**
- **Location:** `$CONDA_PREFIX/envs/<name>`
- **Command:** `conda create -n <name> python=<version>`
- **Activation:** `conda activate <name>`
- **Deactivation:** `conda deactivate`
- **Best For:** Data science, scientific computing, complex dependencies

**Installation:**
```powershell
# Download Miniconda (recommended)
https://docs.conda.io/en/latest/miniconda.html

# Or Anaconda (full distribution)
https://www.anaconda.com/products/distribution

# Initialize shell (after install)
conda init powershell

# Restart terminal
```

**Special Notes:**
- Base environment: `conda activate base`
- Named environments: `conda activate <env-name>`
- Tool detects base vs named environments automatically

---

### 3. poetry

**Description:** Modern Python dependency management and packaging tool.

**Pros:**
- ✅ Deterministic dependency resolution
- ✅ Lockfile for reproducible builds
- ✅ Built-in package publishing
- ✅ Modern pyproject.toml configuration

**Cons:**
- ❌ Additional tool to learn
- ❌ Can be opinionated about project structure

**Creation:**
```powershell
.\env_wrapper.ps1
# Select: 3. poetry
# Answer prompts for pyproject.toml initialization
```

**Details:**
- **Location:** `%APPDATA%\pypoetry\Cache\virtualenvs\<project>-<hash>-py<version>`
- **Commands:** 
  - `poetry init` (creates pyproject.toml)
  - `poetry install --no-root` (installs dependencies)
- **Files Created:** `pyproject.toml`, `poetry.lock`, `activate_poetry.ps1`
- **Activation (Poetry 2.0+):** `poetry env activate` (not `poetry shell`)
- **Run Commands:** `poetry run python script.py`
- **Best For:** Library development, reproducible dependencies, publishing packages

**Installation:**
```powershell
# Windows PowerShell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

# Verify
poetry --version
```

**Special Behavior:**
- Detects existing `pyproject.toml`
- Uses `--no-root` flag for script projects (no package mode)
- Poetry 2.0+ removed `poetry shell` command
- Tool generates `activate_poetry.ps1` for convenience

---

### 4. pipenv

**Description:** Python.org official dependency manager (combines pip + virtualenv).

**Pros:**
- ✅ Automatic virtualenv management
- ✅ Deterministic builds with Pipfile.lock
- ✅ Security vulnerability checking
- ✅ Endorsed by python.org

**Cons:**
- ❌ Can be slow on large projects
- ❌ Some edge case dependency resolution issues

**Creation:**
```powershell
python env_manager.py
# Select: 4. pipenv
# Optionally specify Python version
```

**Details:**
- **Location:** `%USERPROFILE%\.virtualenvs\<project>-<hash>`
- **Command:** `pipenv --python <version>`
- **Files Created:** `Pipfile`, `Pipfile.lock`
- **Activation:** `pipenv shell`
- **Run Commands:** `pipenv run python script.py`
- **Best For:** Application development, security-conscious projects

**Installation:**
```powershell
pip install pipenv
```

---

### 5. pdm

**Description:** Modern Python package manager with PEP 582 support.

**Pros:**
- ✅ Fast dependency resolution
- ✅ PEP 582 support (__pypackages__)
- ✅ Cross-platform lockfiles
- ✅ Built-in build backend

**Cons:**
- ❌ Newer tool (less community adoption)
- ❌ PEP 582 is provisional

**Creation:**
```powershell
python env_manager.py
# Select: 5. pdm
```

**Details:**
- **Location:** `<project>/__pypackages__/` or virtualenv
- **Command:** `pdm init`
- **Files Created:** `pyproject.toml`, `pdm.lock`
- **Activation:** Not required (uses __pypackages__ or `pdm run`)
- **Run Commands:** `pdm run python script.py`
- **Best For:** Modern workflows, PEP 582 enthusiasts

**Installation:**
```powershell
pip install pdm
```

---

### 6. hatch

**Description:** Modern, extensible Python project manager.

**Pros:**
- ✅ Built-in versioning
- ✅ Standardized project structure
- ✅ Multiple environment support
- ✅ Integrated testing

**Cons:**
- ❌ More opinionated about structure
- ❌ Learning curve for advanced features

**Creation:**
```powershell
python env_manager.py
# Select: 6. hatch
# Enter project name
```

**Details:**
- **Location:** User data directory (managed by hatch)
- **Command:** `hatch new <name>`
- **Files Created:** Full project structure with pyproject.toml
- **Activation:** Automatic (or `hatch shell`)
- **Run Commands:** `hatch run python script.py`
- **Best For:** New projects, standardized workflows, testing

**Installation:**
```powershell
pip install hatch
```

---

### 7. pyenv

**Description:** Python version management tool.

**Pros:**
- ✅ Install multiple Python versions
- ✅ Switch Python versions easily
- ✅ Per-project Python versions
- ✅ No need to compile Python manually

**Cons:**
- ❌ Windows support via pyenv-win (separate project)
- ❌ Doesn't manage packages (only Python versions)

**Creation:**
```powershell
python env_manager.py
# Select: 7. pyenv
# Enter Python version (e.g., 3.11.5)
```

**Details:**
- **Location (Windows):** `%USERPROFILE%\.pyenv\pyenv-win\versions\<version>`
- **Command:** `pyenv install <version>`
- **Purpose:** Install specific Python interpreter versions
- **Best For:** Testing across Python versions, legacy compatibility

**Installation (Windows):**
```powershell
# Via Chocolatey
choco install pyenv-win

# Via pip
pip install pyenv-win --target $HOME\.pyenv

# Manually add to PATH if needed
$env:Path += ";$env:USERPROFILE\.pyenv\pyenv-win\bin"
```

**Usage:**
```powershell
# List installed versions
pyenv versions

# List available versions
pyenv install --list

# Install version
pyenv install 3.11.5

# Set global version
pyenv global 3.11.5

# Set local version (creates .python-version)
pyenv local 3.11.5
```

---

### 8. docker

**Description:** Containerization platform (detection only).

**Detection Only:** This tool detects Docker but doesn't create Docker environments.

**Purpose:** Verifies Docker is available for containerized workflows.

---

## PowerShell Wrapper

### Overview

The **`env_wrapper.ps1`** script solves the fundamental limitation where Python subprocesses cannot modify the parent shell's environment variables.

### The Problem

When you run `python env_manager.py`:
1. PowerShell spawns a **Python subprocess**
2. Python creates/configures environment
3. Python subprocess **exits**
4. All environment variable changes are **lost**
5. Your PowerShell session **remains unchanged**

### The Solution

The wrapper script:
1. Runs `env_manager.py` with appropriate flags
2. Detects generated scripts (`activate_poetry.ps1`, `switch_env.ps1`, `deactivate_env.ps1`)
3. **Dot-sources** scripts using `. script.ps1` syntax (runs in current shell)
4. Verifies success by checking `$env:VIRTUAL_ENV` or `$env:CONDA_DEFAULT_ENV`
5. Reports status with color-coded messages

### Usage

```powershell
# Display help
.\env_wrapper.ps1 -Action help
Get-Help .\env_wrapper.ps1 -Detailed

# Create and auto-activate
.\env_wrapper.ps1

# Switch (auto-execute)
.\env_wrapper.ps1 -Action switch

# Deactivate (auto-execute)
.\env_wrapper.ps1 -Action deactivate
```

### Parameters

| Parameter | Type | Values | Default | Description |
|-----------|------|--------|---------|-------------|
| `-Action` | String | `create`, `switch`, `deactivate`, `help` | `create` | Action to perform |

### Dot-Sourcing Explained

```powershell
# WRONG: Runs in subprocess (vars lost)
& ".\activate_poetry.ps1"

# CORRECT: Runs in current shell (vars persist)
. ".\activate_poetry.ps1"
```

The `.` (dot) operator executes the script **in the current scope**, allowing environment variables to be modified in your active PowerShell session.

### Example Output

```powershell
PS> .\env_wrapper.ps1 -Action switch

Running environment manager...
[...environment selection...]

Executing environment switch...
SUCCESS: Conda environment activated!
Conda environment: aws-infra-setup
```

---

## Advanced Usage

### Combining Flags

```powershell
# JSON output of only conda environments in project
python env_manager.py --scan project --type conda --output json

# Table view of all poetry and pipenv environments
python env_manager.py --type poetry --type pipenv --output table

# Verify and log everything
python env_manager.py --verify --log-level DEBUG
```

### Custom Project Directory

```powershell
# Scan different project
python env_manager.py --project C:\path\to\project

# Switch in different project
python env_manager.py --project C:\other\project --switch

# Delete from specific project
python env_manager.py --project C:\old\project --delete
```

### Logging Levels

```powershell
# Debug mode (verbose)
python env_manager.py --log-level DEBUG

# Info mode (detailed)
python env_manager.py --log-level INFO

# Warning mode (default)
python env_manager.py --log-level WARNING

# Error only
python env_manager.py --log-level ERROR
```

### JSON Output for Automation

```powershell
# Get all environments as JSON
python env_manager.py --output json > environments.json

# Filter and parse with PowerShell
$envs = python env_manager.py --type conda --output json | ConvertFrom-Json

# Use in scripts
foreach ($env in $envs.environments) {
    Write-Host "Found: $($env.name) at $($env.location)"
}
```

---

## Understanding Limitations

### Why Can't Python Auto-Activate?

**Fundamental OS Limitation:** Processes cannot modify parent process environment variables.

**What Happens:**
```
PowerShell (Parent)
    |
    └─> Python Subprocess (env_manager.py)
            |
            └─> Creates environment ✅
            └─> Tries to activate ❌ (only affects subprocess)
            └─> Exits
    |
PowerShell (unchanged)
```

**Solutions:**
1. **Manual Execution:** Run generated scripts yourself (`.\activate_poetry.ps1`)
2. **Wrapper Script:** Use `env_wrapper.ps1` (recommended)
3. **Direct Commands:** Copy activation command from output

### Conda Environment Names

Some conda environments don't have names in `conda info --envs`:
```
# conda environments:
#
                       C:\ProgramData\miniconda3
base                   C:\Users\user\miniconda3
aws-env                C:\Users\user\miniconda3\envs\aws-env
                       C:\custom-location\.conda
```

**Tool Behavior:**
- Detects base environments automatically
- Uses environment name from `envs/` folder
- Falls back to `conda activate base` for unnamed base installations

---

## Troubleshooting

### "Environment not activated after running script"

**Symptoms:** Script runs but `$env:VIRTUAL_ENV` is empty.

**Solution:**
```powershell
# Use the wrapper (recommended)
.\env_wrapper.ps1 -Action switch

# OR manually run generated script
.\switch_env.ps1

# OR dot-source the script
. .\activate_poetry.ps1
```

**Explanation:** The `&` operator runs scripts in a subprocess. Use `.` (dot-sourcing) or the wrapper.

---

### "Conda environment not found"

**Symptoms:** `EnvironmentNameNotFound: Could not find conda environment: <name>`

**Diagnosis:**
```powershell
# Check actual environment names
conda info --envs

# Check environment exists
conda env list
```

**Solutions:**
1. Use the actual environment name shown in `conda info --envs`
2. For base environments, use `conda activate base`
3. For custom locations, create a named environment instead
4. Re-run `python env_manager.py --switch` and select correct environment

---

### "Permission denied when deleting environment"

**Symptoms:** `ERROR: Failed to delete <path>: Permission denied`

**Causes:**
- Files are in use by another process
- Windows file locks
- Insufficient permissions

**Solutions:**
```powershell
# 1. Close all programs using the environment
# 2. Deactivate if currently active
conda deactivate
# or
deactivate

# 3. Run as Administrator
Start-Process powershell -Verb RunAs

# 4. Use the tool's built-in error handling (it tries chmod)
python env_manager.py --delete

# 5. Manual deletion
Remove-Item -Recurse -Force .\.venv
```

---

### "Package manager not detected"

**Symptoms:** `--verify` shows a tool as missing even though it's installed.

**Causes:**
- Tool not in PATH
- Terminal not restarted after installation
- pyenv-win in non-standard location

**Solutions:**
```powershell
# 1. Restart PowerShell terminal
exit
# Open new terminal

# 2. Check PATH manually
where.exe poetry
where.exe conda

# 3. For pyenv-win, tool checks fallback location
# If still not found, add to PATH:
$env:Path += ";$env:USERPROFILE\.pyenv\pyenv-win\bin"

# 4. Re-verify
python env_manager.py --verify
```

---

### "Poetry installation fails"

**Symptoms:** `ERROR: Poetry install failed`

**Causes:**
- Missing pyproject.toml
- Invalid pyproject.toml syntax
- Package mode without setup.py/package structure

**Solutions:**
```powershell
# Tool automatically:
# 1. Skips poetry init if pyproject.toml exists
# 2. Uses --no-root flag for script projects

# Manual fixes:
# Check pyproject.toml syntax
poetry check

# Install manually with --no-root
poetry install --no-root

# Recreate environment
rm pyproject.toml poetry.lock
python env_manager.py  # Select Poetry again
```

---

## Complete Examples

### Example 1: New Project Setup

```powershell
# Step 1: Check what's installed
python env_manager.py --verify

# Step 2: Create project directory
mkdir MyProject
cd MyProject

# Step 3: Create Poetry environment
.\env_wrapper.ps1
# Select: 3 (Poetry)
# Answer prompts

# Step 4: Verify activation
echo $env:VIRTUAL_ENV
# Output: C:\Users\...\virtualenvs\MyProject-...-py3.13

# Step 5: Install packages
poetry add requests pandas

# Step 6: Start coding!
```

---

### Example 2: Switching Between Environments

```powershell
# Currently in Poetry environment
echo $env:VIRTUAL_ENV
# Output: C:\...\virtualenvs\project-py3.13

# Switch to conda
.\env_wrapper.ps1 -Action switch
# Select: 2 (conda environment)

# Verify switch
echo $env:CONDA_DEFAULT_ENV
# Output: aws-infra-setup

# Switch back to Poetry
.\env_wrapper.ps1 -Action switch
# Select: 1 (poetry environment)
```

---

### Example 3: Cleaning Up Old Environments

```powershell
# Step 1: See what exists
python env_manager.py --scan project --output table

# Step 2: Delete old environments
python env_manager.py --delete
# Enter: 1,3,5  (delete environments 1, 3, and 5)

# Step 3: Verify deletion
python env_manager.py --scan project
# Should show fewer environments

# Step 4: If stuck files, try as admin
Start-Process powershell -Verb RunAs
cd C:\path\to\project
python env_manager.py --delete
```

---

### Example 4: Automation with JSON

```powershell
# Get all conda environments as JSON
$condaEnvs = python env_manager.py --type conda --output json | ConvertFrom-Json

# Process each environment
foreach ($env in $condaEnvs.environments) {
    if ($env.type -eq "conda") {
        Write-Host "Conda env: $($env.name) at $($env.location)"
    }
}

# Save to file
python env_manager.py --output json > all_environments.json

# Parse in other tools
cat all_environments.json | jq '.environments[] | select(.type=="poetry")'
```

---

### Example 5: Multi-Project Workflow

```powershell
# Project A - Use Poetry
cd C:\Projects\WebApp
.\env_wrapper.ps1  # Create Poetry environment
poetry add flask sqlalchemy

# Project B - Use Conda
cd C:\Projects\DataScience
.\env_wrapper.ps1  # Create Conda environment
# Select conda, install data science packages
conda install numpy pandas matplotlib

# Project C - Use venv
cd C:\Projects\SimpleScript
python env_manager.py  # Create venv
# Select venv
.\.venv\Scripts\Activate.ps1
pip install requests

# Switch between projects
cd C:\Projects\WebApp
.\env_wrapper.ps1 -Action switch  # Select WebApp Poetry env

cd C:\Projects\DataScience
.\env_wrapper.ps1 -Action switch  # Select DataScience conda env
```

---

## Summary

### Quick Reference Card

```powershell
# Help
python env_manager.py --help
.\env_wrapper.ps1 -Action help

# Verify installations
python env_manager.py --verify

# Create environment
.\env_wrapper.ps1

# Switch environments
.\env_wrapper.ps1 -Action switch

# Deactivate
.\env_wrapper.ps1 -Action deactivate

# Delete old environments
python env_manager.py --delete

# Scan and filter
python env_manager.py --type conda --output json

# Custom project
python env_manager.py --project C:\other\path
```

### File Reference

| File | Purpose | Usage |
|------|---------|-------|
| `env_manager.py` | Main Python script | `python env_manager.py [flags]` |
| `env_wrapper.ps1` | PowerShell wrapper | `.\env_wrapper.ps1 [-Action <action>]` |
| `activate_poetry.ps1` | Poetry activation (generated) | `. .\activate_poetry.ps1` |
| `switch_env.ps1` | Environment switch (generated) | `. .\switch_env.ps1` |
| `deactivate_env.ps1` | Deactivation (generated) | `. .\deactivate_env.ps1` |
| `ENV_MANAGER_GUIDE.md` | This documentation | Read for detailed help |

### Support Matrix

| Feature | venv | conda | poetry | pipenv | pdm | hatch | pyenv | docker |
|---------|------|-------|--------|--------|-----|-------|-------|--------|
| Create | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Activate | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ❌ |
| Switch | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ❌ |
| Deactivate | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ❌ |
| Delete | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Scan | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Verify | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

⚠️ = Limited support (pdm uses `pdm run` instead of direct activation)

---

**Questions or Issues?**
- Check `--help` output: `python env_manager.py --help`
- Review this guide's Troubleshooting section
- Verify package managers are installed: `python env_manager.py --verify`

**Happy environment managing! 🎯**
