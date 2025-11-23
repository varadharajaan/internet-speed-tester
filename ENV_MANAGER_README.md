# Environment Manager - Quick Reference

> **📖 For the complete, detailed guide, see [ENV_MANAGER_GUIDE.md](ENV_MANAGER_GUIDE.md)**

This is a quick reference. For comprehensive documentation including:
- Detailed command explanations
- All environment type details
- Troubleshooting guide
- Complete examples and workflows

**Please refer to [ENV_MANAGER_GUIDE.md](ENV_MANAGER_GUIDE.md)**

---

## Getting Help

```powershell
# Python script help
python env_manager.py --help

# PowerShell wrapper help
.\env_wrapper.ps1 -Action help
Get-Help .\env_wrapper.ps1 -Detailed
```

---

## Quick Start

### 1. Verify Package Managers
```powershell
python env_manager.py --verify
```

### 2. Create Environment
```powershell
# Auto-activate with wrapper
.\env_wrapper.ps1

# Or direct
python env_manager.py
```

### 3. Switch Environments
```powershell
.\env_wrapper.ps1 -Action switch
```

### 4. Deactivate Environment
```powershell
.\env_wrapper.ps1 -Action deactivate
```

### 5. Delete Environments
```powershell
python env_manager.py --delete
```

---

## Supported Environment Types

1. **venv** - Python built-in virtual environments
2. **conda** - Conda package manager
3. **poetry** - Poetry dependency manager
4. **pipenv** - Pipenv package manager
5. **pdm** - PDM package manager
6. **hatch** - Hatch project manager
7. **pyenv** - Python version manager
8. **docker** - Docker (detection only)

---

## Command Summary

| Task | Command |
|------|---------|
| **Help** | `python env_manager.py --help` |
| **Verify tools** | `python env_manager.py --verify` |
| **Create env** | `.\env_wrapper.ps1` |
| **Switch env** | `.\env_wrapper.ps1 -Action switch` |
| **Deactivate** | `.\env_wrapper.ps1 -Action deactivate` |
| **Delete env** | `python env_manager.py --delete` |
| **Scan project** | `python env_manager.py --scan project` |
| **Filter by type** | `python env_manager.py --type conda` |
| **JSON output** | `python env_manager.py --output json` |

---

## Why Use the Wrapper?

Python scripts run in **subprocesses** and cannot modify your PowerShell session's environment variables. The `env_wrapper.ps1` script automatically executes generated activation scripts in your current shell using dot-sourcing.

**Without wrapper:**
```powershell
python env_manager.py --switch
.\switch_env.ps1  # Manual step required
```

**With wrapper:**
```powershell
.\env_wrapper.ps1 -Action switch  # Automatic!
```

---

## Files Generated

| File | Purpose | Usage |
|------|---------|-------|
| `activate_poetry.ps1` | Activate Poetry env | `. .\activate_poetry.ps1` |
| `switch_env.ps1` | Switch environments | `. .\switch_env.ps1` |
| `deactivate_env.ps1` | Deactivate env | `. .\deactivate_env.ps1` |

**Note:** Use dot-sourcing (`. script.ps1`) not `& script.ps1`

---

## Common Issues

### "Environment not activated"
**Solution:** Use the wrapper or manually dot-source: `. .\activate_poetry.ps1`

### "Conda environment not found"
**Solution:** Check `conda info --envs` for actual names, use `conda activate base` for base

### "Permission denied when deleting"
**Solution:** Close programs using the environment, run as Administrator if needed

### "Package manager not detected"
**Solution:** Restart terminal after installation, check `--verify` output

---

## Complete Documentation

**For detailed information, please see:**
# **[ENV_MANAGER_GUIDE.md](ENV_MANAGER_GUIDE.md)**

Includes:
- ✅ Complete command reference with examples
- ✅ Detailed explanation of each environment type
- ✅ PowerShell wrapper deep dive
- ✅ Advanced usage patterns
- ✅ Comprehensive troubleshooting
- ✅ Multiple workflow examples
- ✅ Technical explanations of limitations

---

**Happy environment managing! 🎯**


## Table of Contents
1. [Overview](#overview)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Command Reference](#command-reference)
5. [PowerShell Wrapper](#powershell-wrapper)
6. [Environment Types](#environment-types)
7. [Advanced Usage](#advanced-usage)
8. [Understanding Limitations](#understanding-limitations)
9. [Troubleshooting](#troubleshooting)
10. [Complete Examples](#complete-examples)

## Overview
Complete Python environment lifecycle management tool with support for 8 environment types.

**Key Features:**
- ✅ **Verify** - Check which package managers are installed
- ✅ **Create** - Interactive wizard for 7 environment types
- ✅ **Switch** - Seamlessly switch between environments
- ✅ **Deactivate** - Deactivate current environment
- ✅ **Delete** - Remove environments with selection support
- ✅ **Scan** - Discover all project and global environments
- ✅ **Multiple Output Formats** - menu, table, tui, json

## Installation

### Prerequisites
- Python 3.7+ installed
- PowerShell (Windows) or Bash/Zsh (Unix)
- Git (optional, for cloning repository)

### Setup
```powershell
# 1. Navigate to your project directory
cd C:\path\to\your\project

# 2. Ensure env_manager.py and env_wrapper.ps1 are in the directory

# 3. (Optional) Make wrapper script executable
# No action needed on Windows PowerShell

# 4. Verify package managers
python env_manager.py --verify
```

## Quick Start

### Display Help
```powershell
# Python script help
python env_manager.py --help

# PowerShell wrapper help
Get-Help .\env_wrapper.ps1 -Detailed
# OR
.\env_wrapper.ps1 -Action help
```

## Command Reference

### Core Commands

#### 1. Verify Package Managers
Check which environment tools are installed and get installation instructions.

```powershell
python env_manager.py --verify
```

**Output:**
- ✅ Available package managers with versions
- ❌ Missing package managers with installation commands
- Platform-specific installation instructions (Windows/Unix)
- Exit code: 0 (all required available) or 1 (missing required tools)

**Example Output:**
```
======================================================================
Package Manager Verification Report
======================================================================

AVAILABLE (7/8):
  venv (built-in) - v3.13.5
  conda - v25.3.1
  poetry - v2.2.1
  pipenv - v2025.0.4
  pdm - v2.26.1
  hatch - v1.15.1
  pyenv - v3.1.1

MISSING (1/8):
  docker - Docker containerization
```

---

#### 2. Create Environment
Interactive wizard to create new environments.

```powershell
# Using Python directly
python env_manager.py

# Using wrapper (auto-activates)
.\env_wrapper.ps1
```

**Supported Creation Types:**
1. **venv** - Creates `.venv` in project directory
2. **conda** - Creates named conda environment
3. **poetry** - Initializes Poetry project with pyproject.toml
4. **pipenv** - Initializes Pipenv with Pipfile
5. **pdm** - Initializes PDM project
6. **hatch** - Initializes Hatch project
7. **pyenv** - Installs specific Python version

**Interactive Prompts:**
- Environment type selection (1-7)
- Environment name (where applicable)
- Python version (where applicable)
- Additional configuration options

**Generated Files:**
- Environment directory (venv, conda envs)
- Configuration files (pyproject.toml, Pipfile, etc.)
- Activation script (activate_poetry.ps1 for Poetry)

---

#### 3. Switch Environments
Switch from current active environment to another.

```powershell
# Using Python (generates switch_env.ps1)
python env_manager.py --switch
.\switch_env.ps1

# Using wrapper (auto-executes)
.\env_wrapper.ps1 -Action switch
```

**Process:**
1. Detects currently active environment (if any)
2. Scans for all available environments (local + global)
3. Displays numbered list of switchable environments
4. Generates `switch_env.ps1` with:
   - Deactivation command for current environment
   - Activation command for target environment
5. (Wrapper only) Auto-executes script in current shell

**Supported Environments:**
- venv, conda, poetry, pipenv, hatch, pyenv, pdm

---

#### 4. Deactivate Environment
Deactivate the currently active environment.

```powershell
# Using Python (generates deactivate_env.ps1)
python env_manager.py --deactivate
.\deactivate_env.ps1

# Using wrapper (auto-executes)
.\env_wrapper.ps1 -Action deactivate
```

**Behavior:**
- Detects active environment type (venv/poetry/pipenv vs conda)
- Generates appropriate deactivation command:
  - `deactivate` for venv-based environments
  - `conda deactivate` for conda environments
- Saves to `deactivate_env.ps1`
- (Wrapper only) Auto-executes in current shell

**Output:**
```
======================================================================
Environment Deactivator
======================================================================

Currently Active Environment:
  Type: venv/poetry/pipenv
  Name: aws-infra-setup-IEMvNy1b-py3.13
  Path: C:\...\virtualenvs\aws-infra-setup-IEMvNy1b-py3.13

======================================================================
Deactivation Script Generated
======================================================================

To deactivate the current environment, run:

    .\deactivate_env.ps1

Script saved to: C:\...\deactivate_env.ps1

Command: deactivate

======================================================================
```

---

#### 5. Delete Environments
Interactive deletion of local environments.

```powershell
python env_manager.py --delete
```

**Selection Syntax:**
- Single: `1` - Delete environment #1
- Multiple: `1,3,5` - Delete environments 1, 3, and 5
- Range: `1-3` - Delete environments 1, 2, and 3
- All: `all` - Delete all listed environments
- Quit: `q` - Cancel deletion

**Process:**
1. Scans for local environments only
2. Displays numbered list
3. Prompts for selection
4. Confirms each deletion
5. Handles errors (permissions, locked files)
6. Reports summary (deleted count, failed count)

**Safety Features:**
- Only deletes local/project environments (not global)
- Handles Windows permission errors with chmod fallback
- Provides tips for locked files
- Requires explicit confirmation

---
```powershell
# Interactive creation wizard
python env_manager.py

# Auto-activate after creation (using wrapper)
.\env_wrapper.ps1
```

### 3. Switch Environments
```powershell
# Manual - generates switch_env.ps1
python env_manager.py --switch

# Then run:
.\switch_env.ps1

# OR auto-execute with wrapper:
.\env_wrapper.ps1 -Action switch
```

### 4. Deactivate Current Environment
```powershell
# Manual - generates deactivate_env.ps1
python env_manager.py --deactivate

# Then run:
.\deactivate_env.ps1

# OR auto-execute with wrapper:
.\env_wrapper.ps1 -Action deactivate
```

### 5. Delete Environments
```powershell
python env_manager.py --delete

# Select environments to delete:
# - Single: 1
# - Multiple: 1,3,5
# - Range: 1-3
# - All: all
```

## Advanced Usage

### Scan Specific Environment Types
```powershell
# Only conda environments
python env_manager.py --type conda

# Only poetry environments
python env_manager.py --type poetry

# Multiple types
python env_manager.py --type conda --type poetry
```

### Scan Modes
```powershell
# Only project-local environments
python env_manager.py --scan project

# Only global environments
python env_manager.py --scan global

# Both (default)
python env_manager.py --scan all
```

### Output Formats
```powershell
# Menu format (default)
python env_manager.py --output menu

# Table format
python env_manager.py --output table

# JSON format
python env_manager.py --output json

# TUI format
python env_manager.py --output tui
```

## PowerShell Wrapper Script

The `env_wrapper.ps1` wrapper automatically executes generated scripts in your current shell:

```powershell
# Create and activate environment
.\env_wrapper.ps1

# Switch environments
.\env_wrapper.ps1 -Action switch

# Deactivate environment
.\env_wrapper.ps1 -Action deactivate
```

**Note:** The wrapper uses dot-sourcing (`. script.ps1`) to run commands in your current shell context, allowing environment variables to be modified.

## Environment Activation Limitations

### Why Scripts are Generated Instead of Direct Activation

Python scripts run in **subprocesses** and cannot modify your **parent PowerShell session's** environment variables. This is a fundamental operating system limitation.

**What happens when you run `python env_manager.py`:**
1. PowerShell spawns a Python subprocess
2. Python script creates/configures environment
3. Python subprocess exits
4. Any environment variable changes are **lost**
5. Your PowerShell session remains unchanged

**Solutions:**
1. **Generated Scripts** (Current approach): Script generates `activate_poetry.ps1`, `switch_env.ps1`, or `deactivate_env.ps1` that you run manually
2. **PowerShell Wrapper** (Recommended): Use `setup_poetry_env.ps1` which auto-executes generated scripts in current shell
3. **Manual Activation**: Copy the activation command from output

### Conda-Specific Notes

For conda environments to activate properly:
- Ensure conda is initialized in PowerShell (`conda init powershell`)
- Some conda environments in `conda info --envs` may not have names
- The tool attempts to detect base environments vs named environments
- If activation fails, activate manually: `conda activate <env-name>`

## Troubleshooting

### "Environment not activated after running script"
- Use the PowerShell wrapper: `.\setup_poetry_env.ps1 -Action switch`
- OR manually run the generated script: `.\switch_env.ps1`
- Check if conda is initialized: `conda init powershell` (restart shell after)

### "Conda environment not found"
- Run `conda info --envs` to see actual environment names
- Some paths don't have names - use `conda activate base` or create named env
- Environments in custom locations need to be activated by path

### "Permission denied when deleting environment"
- Close any applications using the environment
- Run PowerShell as Administrator
- Ensure no Python processes are running from that environment

### "Package manager not detected"
- Run `--verify` to check installation
- Restart PowerShell after installing new package managers
- Some tools (like pyenv-win) install to `%USERPROFILE%\.pyenv`

## Examples

### Complete Workflow
```powershell
# 1. Check what's installed
python env_manager.py --verify

# 2. Create a poetry environment
.\env_wrapper.ps1
# Select "2" for Poetry, answer prompts

# 3. Later, switch to conda
.\env_wrapper.ps1 -Action switch
# Select conda environment from list

# 4. Deactivate when done
.\env_wrapper.ps1 -Action deactivate

# 5. Clean up old environments
python env_manager.py --delete
# Enter: 1,3,5 to delete environments 1, 3, and 5
```

### View All Environments
```powershell
# JSON output with all environments
python env_manager.py --output json --scan all

# Table view of only local environments
python env_manager.py --output table --scan project
```

## Files Generated

| File | Purpose | When Created |
|------|---------|--------------|
| `activate_poetry.ps1` | Activate Poetry environment | After Poetry creation |
| `switch_env.ps1` | Switch environments | `--switch` command |
| `deactivate_env.ps1` | Deactivate current env | `--deactivate` command |

All scripts are generated in the project directory and can be safely deleted after use.

## Tips

1. **Use the wrapper** for best experience: `.\env_wrapper.ps1`
2. **Verify first** before creating: `python env_manager.py --verify`
3. **Filter by type** for cleaner output: `--type conda`
4. **Use JSON output** for programmatic access: `--output json`
5. **Restart shell** after installing package managers to update PATH

## Support Matrix

| Environment | Create | Switch | Deactivate | Delete | Verify |
|-------------|--------|--------|------------|--------|--------|
| venv        | ✅     | ✅     | ✅         | ✅     | ✅     |
| conda       | ✅     | ✅     | ✅         | ✅     | ✅     |
| poetry      | ✅     | ✅     | ✅         | ✅     | ✅     |
| pipenv      | ✅     | ✅     | ✅         | ✅     | ✅     |
| pdm         | ✅     | ⚠️     | ⚠️         | ✅     | ✅     |
| hatch       | ✅     | ✅     | ✅         | ✅     | ✅     |
| pyenv       | ✅     | ✅     | ✅         | ✅     | ✅     |
| docker      | ❌     | ❌     | ❌         | ❌     | ✅     |

⚠️ = Limited support (uses `pdm shell` instead of direct activation)
