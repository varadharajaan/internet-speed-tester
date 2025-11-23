import os
import sys
import json
import argparse
import subprocess
import platform
import shutil
import logging
from typing import List, Dict, Optional, Any


class Environment:
    """
    Represents a Python-related environment: venv, conda, poetry, pipenv,
    pyenv, pdm, hatch, docker, global-python.
    """

    def __init__(self, name: str, env_type: str, location: Optional[str], meta: Optional[Dict[str, Any]] = None):
        self.name = name
        self.type = env_type.lower()
        self.location = os.path.abspath(location) if location else None
        self.meta = meta or {}
        self.is_active: bool = False
        self.id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "is_active": self.is_active,
            "meta": self.meta,
        }


class ActivationCommandBuilder:
    """
    Builds activation commands for a given environment.
    """

    @staticmethod
    def build(env: Environment) -> Dict[str, str]:
        system = platform.system()
        cmds: Dict[str, str] = {}

        if env.type in ("venv", "poetry", "pipenv", "hatch", "pyenv", "conda"):
            path = env.location or ""

            if env.type == "conda":
                cmds["bash/zsh"] = f'conda activate "{path}"'
                cmds["cmd.exe"] = f'conda activate "{path}"'
                cmds["powershell"] = f'conda activate "{path}"'

            else:
                if system == "Windows":
                    scripts = os.path.join(path, "Scripts")
                    cmds["cmd.exe"] = os.path.join(scripts, "activate.bat")
                    cmds["powershell"] = os.path.join(scripts, "Activate.ps1")
                    cmds["bash/zsh"] = f'source "{os.path.join(scripts, "activate")}"'
                elif env.type == "poetry":
                    # Poetry 2.0+ uses different activation
                    cmds["generic"] = "poetry env activate"
                    cmds["run"] = "poetry run <command>"
                else:
                    bin_dir = os.path.join(path, "bin")
                    cmds["bash/zsh"] = f'source "{os.path.join(bin_dir, "activate")}"'
                    cmds["fish"] = f'source "{os.path.join(bin_dir, "activate.fish")}"'

        elif env.type == "pdm":
            cmds["generic"] = "pdm run <command>"

        elif env.type == "docker":
            cmds["generic"] = "docker build -t image . && docker run -it image"

        elif env.type == "global-python":
            exe = env.meta.get("executable", "python")
            cmds["generic"] = exe

        return cmds


class EnvironmentScanner:
    """
    Scans local and global environment types.
    Now supports:
    - only_project (bool)
    - type_filters (list[str])
    """

    def __init__(self, project_dir: str, logger: logging.Logger, only_project: bool, type_filters: List[str]):
        self.project_dir = os.path.abspath(project_dir)
        self.logger = logger
        self.only_project = only_project
        self.type_filters = [t.lower() for t in type_filters] if type_filters else []

    # ----- Utility -----

    def _run(self, cmd: List[str], cwd: Optional[str] = None) -> Optional[str]:
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                cwd=cwd
            )
            if result.returncode != 0:
                return None
            return result.stdout.strip()
        except Exception:
            return None

    def _include_type(self, env_type: str) -> bool:
        if not self.type_filters:
            return True
        return env_type.lower() in self.type_filters

     # -------------------------
    # Project-only scanning
    # -------------------------
    def scan_only_project(self) -> List[Environment]:
        envs: List[Environment] = []

        envs.extend(self._detect_project_venvs())
        envs.extend(self._detect_project_conda())
        envs.extend(self._detect_poetry())
        envs.extend(self._detect_pipenv())
        envs.extend(self._detect_pdm())
        envs.extend(self._detect_hatch())
        envs.extend(self._detect_docker())

        envs = self._dedupe(envs)
        envs = self._filter_types(envs)
        self._mark_active(envs)
        return envs

    # -------------------------
    # Global-only scanning
    # -------------------------
    def scan_only_global(self) -> List[Environment]:
        envs: List[Environment] = []

        envs.extend(self._detect_global_conda())
        envs.extend(self._detect_pyenv())
        envs.extend(self._detect_global_python())

        envs = self._dedupe(envs)
        envs = self._filter_types(envs)
        self._mark_active(envs)
        return envs

    # -------------------------
    # Combined scan (default behavior)
    # -------------------------
    def scan_all_v2(self) -> List[Environment]:
        envs: List[Environment] = []

        # always scan project
        envs.extend(self._detect_project_venvs())
        envs.extend(self._detect_project_conda())
        envs.extend(self._detect_poetry())
        envs.extend(self._detect_pipenv())
        envs.extend(self._detect_pdm())
        envs.extend(self._detect_hatch())
        envs.extend(self._detect_docker())

        # optionally scan global
        if not self.only_project:
            envs.extend(self._detect_global_conda())
            envs.extend(self._detect_pyenv())
            envs.extend(self._detect_global_python())

        envs = self._dedupe(envs)
        envs = self._filter_types(envs)
        self._mark_active(envs)
        return envs
    
    # ----- Scanning -----
    def scan_all(self) -> List[Environment]:
        envs: List[Environment] = []

        # Always scan project envs
        envs.extend(self._detect_project_venvs())
        envs.extend(self._detect_project_conda())
        envs.extend(self._detect_poetry())
        envs.extend(self._detect_pipenv())
        envs.extend(self._detect_pdm())
        envs.extend(self._detect_hatch())
        envs.extend(self._detect_docker())

        # Global scans disabled if only_project=True
        if not self.only_project:
            envs.extend(self._detect_global_conda())
            envs.extend(self._detect_pyenv())
            
            # Detect global Python but exclude those that belong to other environments
            global_pythons = self._detect_global_python()
            env_locations = {os.path.normpath(e.location) for e in envs}
            
            # Filter out Python executables that are inside already-detected environments
            filtered_pythons = []
            for py_env in global_pythons:
                py_location = os.path.normpath(py_env.location)
                py_executable = os.path.normpath(py_env.meta.get("executable", ""))
                
                # DEBUG
                # print(f"DEBUG: Checking Python '{py_env.name}' at {py_location}")
                # print(f"DEBUG: Executable: {py_executable}")
                
                # Check if this Python location or executable is inside any detected environment
                is_part_of_env = False
                for env_loc in env_locations:
                    # Check if Python location is inside or same as environment location
                    if py_location == env_loc or py_location.startswith(env_loc + os.sep):
                        # print(f"DEBUG:   MATCH with {env_loc} (location)")
                        is_part_of_env = True
                        break
                    # Check if executable is inside environment location
                    if py_executable and (py_executable.startswith(env_loc + os.sep)):
                        # print(f"DEBUG:   MATCH with {env_loc} (executable)")
                        is_part_of_env = True
                        break
                
                if not is_part_of_env:
                    # print(f"DEBUG:   KEEP - not part of any environment")
                    filtered_pythons.append(py_env)
                # else:
                    # print(f"DEBUG:   FILTER OUT - part of environment")
            
            envs.extend(filtered_pythons)

        envs = self._dedupe(envs)
        envs = self._filter_types(envs)
        self._mark_active(envs)
        return envs

    # ---- Local Project Env Detectors ----

    def _detect_project_venvs(self) -> List[Environment]:
        envs = []
        try:
            for entry in os.listdir(self.project_dir):
                full = os.path.join(self.project_dir, entry)
                if not os.path.isdir(full) or entry.startswith("."):
                    continue
                if platform.system() == "Windows":
                    if os.path.exists(os.path.join(full, "Scripts", "activate")):
                        envs.append(Environment(entry, "venv", full))
                else:
                    if os.path.exists(os.path.join(full, "bin", "activate")):
                        envs.append(Environment(entry, "venv", full))
        except Exception:
            pass
        return envs

    def _detect_project_conda(self) -> List[Environment]:
        envs = []
        paths = [
            os.path.join(self.project_dir, ".conda"),
            os.path.join(self.project_dir, "env"),
            os.path.join(self.project_dir, "envs"),
        ]
        for p in paths:
            if os.path.isdir(p) and os.path.isdir(os.path.join(p, "conda-meta")):
                envs.append(Environment(os.path.basename(p), "conda", p, {"scope": "local"}))
            if p.endswith("envs") and os.path.isdir(p):
                for sub in os.listdir(p):
                    subp = os.path.join(p, sub)
                    if os.path.isdir(subp) and os.path.isdir(os.path.join(subp, "conda-meta")):
                        envs.append(Environment(sub, "conda", subp, {"scope": "local"}))
        return envs

    def _detect_poetry(self) -> List[Environment]:
        envs = []
        out = self._run(["poetry", "env", "list", "--full-path"], cwd=self.project_dir)
        if out:
            for line in out.splitlines():
                parts = line.split()
                path = parts[-1]
                if os.path.isdir(path):
                    envs.append(Environment(os.path.basename(path), "poetry", path))
        # local .venv
        venv_path = os.path.join(self.project_dir, ".venv")
        if os.path.isdir(venv_path) and os.path.exists(os.path.join(self.project_dir, "pyproject.toml")):
            envs.append(Environment(".venv", "poetry", venv_path))
        return envs

    def _detect_pipenv(self) -> List[Environment]:
        envs = []
        if os.path.exists(os.path.join(self.project_dir, "Pipfile")):
            out = self._run(["pipenv", "--venv"], cwd=self.project_dir)
            if out and os.path.isdir(out.strip()):
                envs.append(Environment(os.path.basename(out.strip()), "pipenv", out.strip()))
        return envs

    def _detect_pdm(self) -> List[Environment]:
        pdm_dir = os.path.join(self.project_dir, "__pypackages__")
        if os.path.isdir(pdm_dir):
            return [Environment("__pypackages__", "pdm", pdm_dir)]
        return []

    def _detect_hatch(self) -> List[Environment]:
        envs = []
        out = self._run(["hatch", "env", "show"], cwd=self.project_dir)
        if out:
            for line in out.splitlines():
                if ":" in line:
                    name, path = [x.strip() for x in line.split(":", 1)]
                    if os.path.isdir(path):
                        envs.append(Environment(name, "hatch", path))
        return envs

    def _detect_docker(self) -> List[Environment]:
        dockerfile = os.path.join(self.project_dir, "Dockerfile")
        if not os.path.exists(dockerfile):
            return []
        try:
            with open(dockerfile) as f:
                content = f.read()
        except:
            return []
        python_base = any("from" in l.lower() and "python" in l.lower() for l in content.splitlines())
        if python_base:
            return [Environment("Dockerfile", "docker", dockerfile)]
        return []

    # ---- Global Env Detectors ----

    def _detect_global_conda(self) -> List[Environment]:
        envs = []
        out = self._run(["conda", "env", "list", "--json"])
        if not out:
            return []
        try:
            data = json.loads(out)
        except:
            return []
        for p in data.get("envs", []):
            envs.append(Environment(os.path.basename(p), "conda", p, {"scope": "global"}))
        return envs

    def _detect_pyenv(self) -> List[Environment]:
        envs = []
        root = self._run(["pyenv", "root"])
        if not root:
            return []
        versions = os.path.join(root, "versions")
        if not os.path.isdir(versions):
            return []
        for entry in os.listdir(versions):
            full = os.path.join(versions, entry)
            if os.path.isdir(full):
                envs.append(Environment(entry, "pyenv", full))
        return envs

    def _detect_global_python(self) -> List[Environment]:
        envs = []
        seen = set()
        # current python
        cur = os.path.abspath(sys.executable)
        envs.append(Environment("current-python", "global-python", os.path.dirname(cur), {"executable": cur}))
        seen.add(cur)
        for cmd in ["python", "python3", "py"]:
            p = shutil.which(cmd)
            if p:
                p = os.path.abspath(p)
                if p not in seen:
                    seen.add(p)
                    envs.append(Environment(cmd, "global-python", os.path.dirname(p), {"executable": p}))
        return envs

    # ---- Utils ----

    def _dedupe(self, envs: List[Environment]) -> List[Environment]:
        out = {}
        for e in envs:
            key = (e.type, e.location)
            out[key] = e
        return list(out.values())

    def _filter_types(self, envs: List[Environment]) -> List[Environment]:
        if not self.type_filters:
            return envs
        return [e for e in envs if e.type in self.type_filters]

    def _mark_active(self, envs: List[Environment]) -> None:
        venv = os.environ.get("VIRTUAL_ENV")
        conda = os.environ.get("CONDA_PREFIX")
        active_paths = set()
        if venv:
            active_paths.add(os.path.abspath(venv))
        if conda:
            active_paths.add(os.path.abspath(conda))

        current_py = os.path.abspath(sys.executable)
        current_dir = os.path.dirname(current_py)

        for e in envs:
            if e.location in active_paths:
                e.is_active = True
            elif e.type == "global-python" and e.meta.get("executable") == current_py:
                e.is_active = True
            elif e.location and current_dir.startswith(e.location):
                e.is_active = True


class EnvironmentCreator:
    """Handles creation of new environments."""
    
    def __init__(self, project_dir: str, logger: logging.Logger):
        self.project_dir = os.path.abspath(project_dir)
        self.logger = logger
    
    def create_venv(self, name: str) -> bool:
        """Create a venv environment."""
        venv_path = os.path.join(self.project_dir, name)
        if os.path.exists(venv_path):
            self.logger.error(f"Directory '{name}' already exists.")
            print(f"ERROR: Directory '{name}' already exists.")
            return False
        
        try:
            self.logger.info(f"Creating venv '{name}' at {venv_path}")
            print(f"Creating venv '{name}' at {venv_path}...")
            subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)
            self.logger.info(f"Successfully created venv '{name}'")
            
            # Generate activation script
            activate_script = os.path.join(self.project_dir, "activate_venv.ps1")
            if platform.system() == "Windows":
                activation_cmd = os.path.join(venv_path, 'Scripts', 'Activate.ps1')
            else:
                activation_cmd = f"source {os.path.join(venv_path, 'bin', 'activate')}"
            
            with open(activate_script, 'w') as f:
                f.write(activation_cmd)
            
            # Display success message with border
            border = "=" * 70
            print(f"\n{border}")
            print("SUCCESS: Virtual environment created!")
            print(f"Location: {venv_path}")
            print(f"\nActivation script generated: {activate_script}")
            print(f"\nTo activate, run:")
            print(f"  .\\env_wrapper.ps1")
            print(f"\nOr manually:")
            print(f"  .\\activate_venv.ps1")
            print(f"{border}\n")
            
            self.logger.info(f"Activation script saved to {activate_script}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create venv: {e}")
            print(f"ERROR: Failed to create venv: {e}")
            return False
    
    def create_conda(self, name: str, python_version: str = None, local: bool = False) -> bool:
        """Create a conda environment (local or global)."""
        try:
            if local:
                # Create local .conda environment in project directory
                conda_path = os.path.join(self.project_dir, ".conda")
                cmd = ["conda", "create", "-p", conda_path, "-y"]
                if python_version:
                    cmd.append(f"python={python_version}")
                else:
                    cmd.append("python")
                
                self.logger.info(f"Creating local conda environment at '{conda_path}'")
                print(f"Creating local conda environment at '{conda_path}'...")
                subprocess.run(cmd, check=True)
                self.logger.info(f"Successfully created local conda environment")
                print(f"SUCCESS: Created local conda environment")
                
                # Generate activation script
                activation_cmd = f'conda activate "{conda_path}"'
                alt_activation_cmd = f'conda activate ./.conda'
                
                # Save activation script
                activate_script = os.path.join(self.project_dir, "activate_conda.ps1")
                with open(activate_script, 'w') as f:
                    f.write(f"# Activate local conda environment\n")
                    f.write(activation_cmd)
                
                print(f"\n{'='*70}")
                print(f"Local Conda Environment Created Successfully!")
                print(f"{'='*70}")
                print(f"\nNOTE: Due to PowerShell limitations, activation cannot be done")
                print(f"      automatically from within this script.")
                print(f"\nTo activate the environment in your current shell, run:")
                print(f"\n    .\\activate_conda.ps1")
                print(f"\nOr use the shorter command:")
                print(f"\n    {alt_activation_cmd}")
                print(f"\n{'='*70}\n")
                
                self.logger.info(f"Activation script saved to {activate_script}")
            else:
                # Create global named environment
                cmd = ["conda", "create", "-n", name, "-y"]
                if python_version:
                    cmd.append(f"python={python_version}")
                else:
                    cmd.append("python")
                
                self.logger.info(f"Creating global conda environment '{name}'")
                print(f"Creating global conda environment '{name}'...")
                subprocess.run(cmd, check=True)
                self.logger.info(f"Successfully created global conda environment '{name}'")
                print(f"SUCCESS: Created global conda environment '{name}'")
                
                # Generate activation script
                activation_cmd = f'conda activate "{name}"'
                
                # Save activation script
                activate_script = os.path.join(self.project_dir, "activate_conda.ps1")
                with open(activate_script, 'w') as f:
                    f.write(f"# Activate conda environment: {name}\n")
                    f.write(activation_cmd)
                
                print(f"\n{'='*70}")
                print(f"Conda Environment Created Successfully!")
                print(f"{'='*70}")
                print(f"\nNOTE: Due to PowerShell limitations, activation cannot be done")
                print(f"      automatically from within this script.")
                print(f"\nTo activate the environment in your current shell, run:")
                print(f"\n    .\\activate_conda.ps1")
                print(f"\nOr use the command:")
                print(f"\n    {activation_cmd}")
                print(f"\n{'='*70}\n")
                
                self.logger.info(f"Activation script saved to {activate_script}")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to create conda environment: {e}")
            print(f"ERROR: Failed to create conda environment: {e}")
            return False
    
    def create_poetry(self) -> bool:
        """Initialize a poetry project."""
        try:
            pyproject_path = os.path.join(self.project_dir, "pyproject.toml")
            
            # Check if pyproject.toml already exists
            if os.path.exists(pyproject_path):
                self.logger.info(f"pyproject.toml already exists, skipping init")
                print(f"INFO: pyproject.toml already exists, running poetry install...")
                self.logger.info(f"Running poetry install for existing project at {self.project_dir}")
            else:
                # Check if .venv exists but is broken, and clean it up
                venv_path = os.path.join(self.project_dir, ".venv")
                if os.path.exists(venv_path):
                    self.logger.warning(f"Found existing .venv directory, removing it")
                    print(f"WARNING: Found existing broken .venv directory, cleaning up...")
                    try:
                        import shutil
                        shutil.rmtree(venv_path)
                    except Exception as e:
                        self.logger.error(f"Failed to remove .venv: {e}")
                        print(f"ERROR: Failed to remove .venv directory. Please delete it manually: {venv_path}")
                        return False
                
                self.logger.info(f"Initializing Poetry project at {self.project_dir}")
                print(f"Initializing Poetry project at {self.project_dir}...")
                subprocess.run(["poetry", "init", "-n"], cwd=self.project_dir, check=True)
            
            # Install dependencies
            print(f"Installing dependencies...")
            subprocess.run(["poetry", "install", "--no-root"], cwd=self.project_dir, check=True)
            self.logger.info("Successfully initialized Poetry project")
            print(f"SUCCESS: Initialized Poetry project")
            
            # Get activation command
            print(f"\nPreparing activation command...")
            try:
                result = subprocess.run(
                    ["poetry", "env", "activate"],
                    cwd=self.project_dir,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0 and result.stdout:
                    activation_cmd = result.stdout.strip()
                    
                    # Save activation script
                    temp_script = os.path.join(self.project_dir, "activate_poetry.ps1")
                    with open(temp_script, 'w') as f:
                        f.write(activation_cmd)
                    
                    print(f"\n{'='*70}")
                    print(f"Poetry environment created successfully!")
                    print(f"{'='*70}")
                    print(f"\nNOTE: Due to PowerShell limitations, activation cannot be done")
                    print(f"      automatically from within this script.")
                    print(f"\nTo activate the environment in your current shell, run:")
                    print(f"\n    .\\activate_poetry.ps1")
                    print(f"\nOr copy and paste this command:")
                    print(f"\n    {activation_cmd}")
                    print(f"\n{'='*70}\n")
                    
                    self.logger.info(f"Activation script saved to {temp_script}")
                else:
                    print(f"\nTo activate, run: poetry shell")
            except Exception as e:
                self.logger.warning(f"Could not generate activation command: {e}")
                print(f"\nTo activate, run: poetry shell")
            
            print(f"Alternatively, run commands with: poetry run <command>")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Poetry: {e}")
            print(f"ERROR: Failed to initialize Poetry: {e}")
            return False
    
    def create_pipenv(self) -> bool:
        """Initialize a pipenv project."""
        try:
            self.logger.info(f"Initializing Pipenv project at {self.project_dir}")
            print(f"Initializing Pipenv project at {self.project_dir}...")
            result = subprocess.run(["pipenv", "install"], cwd=self.project_dir, check=True, capture_output=True, text=True)
            
            # Get venv location
            venv_result = subprocess.run(
                ["pipenv", "--venv"],
                capture_output=True,
                text=True,
                cwd=self.project_dir
            )
            venv_location = venv_result.stdout.strip() if venv_result.returncode == 0 else "Pipenv environment"
            
            self.logger.info("Successfully initialized Pipenv project")
            
            # Generate activation script
            activate_script = os.path.join(self.project_dir, "activate_pipenv.ps1")
            script_content = "pipenv shell\n"
            
            with open(activate_script, 'w') as f:
                f.write(script_content)
            
            # Display success message with border
            border = "=" * 70
            print(f"\n{border}")
            print("SUCCESS: Pipenv environment created!")
            print(f"Location: {venv_location}")
            print(f"\nActivation script generated: {activate_script}")
            print(f"\nTo activate, run:")
            print(f"  .\\env_wrapper.ps1")
            print(f"\nOr manually:")
            print(f"  .\\activate_pipenv.ps1")
            print(f"{border}\n")
            
            self.logger.info(f"Activation script saved to {activate_script}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Pipenv: {e}")
            print(f"ERROR: Failed to initialize Pipenv: {e}")
            return False
    
    def create_pdm(self) -> bool:
        """Initialize a PDM project."""
        try:
            self.logger.info(f"Initializing PDM project at {self.project_dir}")
            print(f"Initializing PDM project at {self.project_dir}...")
            subprocess.run(["pdm", "init", "-n"], cwd=self.project_dir, check=True)
            subprocess.run(["pdm", "install"], cwd=self.project_dir, check=True)
            
            # Get venv location (PDM uses .venv by default)
            venv_path = os.path.join(self.project_dir, ".venv")
            
            self.logger.info("Successfully initialized PDM project")
            
            # Generate activation script
            activate_script = os.path.join(self.project_dir, "activate_pdm.ps1")
            if platform.system() == "Windows":
                script_content = os.path.join(venv_path, 'Scripts', 'Activate.ps1')
            else:
                script_content = f"source {os.path.join(venv_path, 'bin', 'activate')}"
            
            with open(activate_script, 'w') as f:
                f.write(script_content)
            
            # Display success message with border
            border = "=" * 70
            print(f"\n{border}")
            print("SUCCESS: PDM environment created!")
            print(f"Location: {venv_path}")
            print(f"\nActivation script generated: {activate_script}")
            print(f"\nTo activate, run:")
            print(f"  .\\env_wrapper.ps1")
            print(f"\nOr manually:")
            print(f"  .\\activate_pdm.ps1")
            print(f"\nNote: You can also use 'pdm run <command>' without activation")
            print(f"{border}\n")
            
            self.logger.info(f"Activation script saved to {activate_script}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize PDM: {e}")
            print(f"ERROR: Failed to initialize PDM: {e}")
            return False
    
    def create_hatch(self) -> bool:
        """Initialize a Hatch project."""
        try:
            self.logger.info(f"Initializing Hatch project at {self.project_dir}")
            print(f"Initializing Hatch project at {self.project_dir}...")
            subprocess.run(["hatch", "new", "--init"], cwd=self.project_dir, check=True)
            
            # Get environment location
            env_result = subprocess.run(
                ["hatch", "env", "find", "default"],
                capture_output=True,
                text=True,
                cwd=self.project_dir
            )
            env_location = env_result.stdout.strip() if env_result.returncode == 0 else "Hatch environment"
            
            self.logger.info("Successfully initialized Hatch project")
            
            # Generate activation script
            activate_script = os.path.join(self.project_dir, "activate_hatch.ps1")
            script_content = "hatch shell\n"
            
            with open(activate_script, 'w') as f:
                f.write(script_content)
            
            # Display success message with border
            border = "=" * 70
            print(f"\n{border}")
            print("SUCCESS: Hatch environment created!")
            print(f"Location: {env_location}")
            print(f"\nActivation script generated: {activate_script}")
            print(f"\nTo activate, run:")
            print(f"  .\\env_wrapper.ps1")
            print(f"\nOr manually:")
            print(f"  .\\activate_hatch.ps1")
            print(f"\nNote: You can also use 'hatch run <command>' without activation")
            print(f"{border}\n")
            
            self.logger.info(f"Activation script saved to {activate_script}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Hatch: {e}")
            print(f"ERROR: Failed to initialize Hatch: {e}")
            return False
    
    def create_pyenv_python(self, version: str) -> bool:
        """Install a Python version with pyenv."""
        try:
            self.logger.info(f"Installing Python {version} with pyenv")
            print(f"Installing Python {version} with pyenv...")
            subprocess.run(["pyenv", "install", version], check=True)
            
            # Set local version automatically
            subprocess.run(
                ["pyenv", "local", version],
                cwd=self.project_dir,
                check=False
            )
            
            self.logger.info(f"Successfully installed Python {version}")
            
            # Generate activation script
            activate_script = os.path.join(self.project_dir, "activate_pyenv.ps1")
            script_content = f"pyenv shell {version}\n"
            
            with open(activate_script, 'w') as f:
                f.write(script_content)
            
            # Display success message with border
            border = "=" * 70
            print(f"\n{border}")
            print(f"SUCCESS: Python {version} installed via pyenv!")
            print(f"Local version set to: {version}")
            print(f"\nActivation script generated: {activate_script}")
            print(f"\nTo activate, run:")
            print(f"  .\\env_wrapper.ps1")
            print(f"\nOr manually:")
            print(f"  .\\activate_pyenv.ps1")
            print(f"\nNote: A .python-version file has been created in this directory")
            print(f"{border}\n")
            
            self.logger.info(f"Activation script saved to {activate_script}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to install Python {version}: {e}")
            print(f"ERROR: Failed to install Python {version}: {e}")
            return False
    
    def interactive_create(self) -> bool:
        """Interactive environment creation wizard."""
        print("\n" + "="*60)
        print("Environment Creation Wizard")
        print("="*60)
        
        print("\nAvailable environment types:")
        print("  1. venv (Python virtual environment)")
        print("  2. conda (Conda environment)")
        print("  3. poetry (Poetry dependency manager)")
        print("  4. pipenv (Pipenv package manager)")
        print("  5. pdm (PDM package manager)")
        print("  6. hatch (Hatch project manager)")
        print("  7. pyenv (Install Python version)")
        print("  0. Cancel")
        
        choice = input("\nSelect environment type [1-7, 0 to cancel]: ").strip()
        
        if choice == "0" or not choice:
            self.logger.info("Environment creation cancelled by user")
            print("Cancelled.")
            return False
        
        if choice == "1":  # venv
            name = input("Enter venv name (default: venv): ").strip() or "venv"
            return self.create_venv(name)
        
        elif choice == "2":  # conda
            if not shutil.which("conda"):
                self.logger.warning("Conda is not installed or not in PATH")
                print("ERROR: Conda is not installed or not in PATH.")
                return False
            
            # Ask for local vs global
            print("\nConda environment location:")
            print("  1. Local (create .conda folder in current project)")
            print("  2. Global (create named environment in conda's envs folder)")
            location_choice = input("Select location [1-2]: ").strip()
            
            if location_choice == "1":
                # Local .conda environment
                python_ver = input("Enter Python version (e.g., 3.11, or press Enter for default): ").strip()
                return self.create_conda(name="", python_version=python_ver if python_ver else None, local=True)
            
            elif location_choice == "2":
                # Global named environment
                name = input("Enter conda environment name: ").strip()
                if not name:
                    self.logger.warning("Environment name is required but not provided")
                    print("ERROR: Environment name is required.")
                    return False
                
                python_ver = input("Enter Python version (e.g., 3.11, or press Enter for default): ").strip()
                return self.create_conda(name, python_ver if python_ver else None, local=False)
            
            else:
                print("ERROR: Invalid selection. Choose 1 or 2.")
                return False
        
        elif choice == "3":  # poetry
            if not shutil.which("poetry"):
                self.logger.warning("Poetry is not installed or not in PATH")
                print("ERROR: Poetry is not installed or not in PATH.")
                return False
            
            confirm = input("Initialize Poetry in current directory? [y/N]: ").strip().lower()
            if confirm == "y":
                return self.create_poetry()
            else:
                self.logger.info("Poetry initialization cancelled by user")
                print("Cancelled.")
                return False
        
        elif choice == "4":  # pipenv
            if not shutil.which("pipenv"):
                self.logger.warning("Pipenv is not installed or not in PATH")
                print("ERROR: Pipenv is not installed or not in PATH.")
                return False
            
            confirm = input("Initialize Pipenv in current directory? [y/N]: ").strip().lower()
            if confirm == "y":
                return self.create_pipenv()
            else:
                self.logger.info("Pipenv initialization cancelled by user")
                print("Cancelled.")
                return False
        
        elif choice == "5":  # pdm
            if not shutil.which("pdm"):
                self.logger.warning("PDM is not installed or not in PATH")
                print("ERROR: PDM is not installed or not in PATH.")
                return False
            
            confirm = input("Initialize PDM in current directory? [y/N]: ").strip().lower()
            if confirm == "y":
                return self.create_pdm()
            else:
                self.logger.info("PDM initialization cancelled by user")
                print("Cancelled.")
                return False
        
        elif choice == "6":  # hatch
            if not shutil.which("hatch"):
                self.logger.warning("Hatch is not installed or not in PATH")
                print("ERROR: Hatch is not installed or not in PATH.")
                return False
            
            confirm = input("Initialize Hatch in current directory? [y/N]: ").strip().lower()
            if confirm == "y":
                return self.create_hatch()
            else:
                self.logger.info("Hatch initialization cancelled by user")
                print("Cancelled.")
                return False
        
        elif choice == "7":  # pyenv
            if not shutil.which("pyenv"):
                self.logger.warning("Pyenv is not installed or not in PATH")
                print("ERROR: Pyenv is not installed or not in PATH.")
                return False
            
            version = input("Enter Python version to install (e.g., 3.11.5): ").strip()
            if not version:
                self.logger.warning("Python version is required but not provided")
                print("ERROR: Python version is required.")
                return False
            
            return self.create_pyenv_python(version)
        
        else:
            self.logger.warning(f"Invalid environment type choice: {choice}")
            print("ERROR: Invalid choice.")
            return False


class EnvironmentPresenter:
    def __init__(self, envs: List[Environment], project_dir: str = ".", logger: logging.Logger = None):
        self.envs = envs
        self.project_dir = project_dir
        self.logger = logger or logging.getLogger("env_manager")

    def assign_ids(self):
        for i, e in enumerate(self.envs, 1):
            e.id = i

    def show_menu(self):
        if not self.envs:
            self.logger.info("No environments found in project")
            print("WARNING: No environments found.")
            print("\nWould you like to create a new environment?")
            choice = input("[y/N]: ").strip().lower()
            if choice == "y":
                creator = EnvironmentCreator(self.project_dir, self.logger)
                success = creator.interactive_create()
                
                # Re-scan after creation to show the new environment
                if success:
                    print("\nRe-scanning for environments...")
                    scanner = EnvironmentScanner(
                        project_dir=self.project_dir,
                        logger=self.logger,
                        only_project=False,  # Scan both local AND global to find conda envs
                        type_filters=[]
                    )
                    new_envs = scanner.scan_all()
                    if new_envs:
                        self.envs = new_envs
                        self.assign_ids()
                        print("\nDetected environments after creation:")
                        print("----------------------")
                        groups = self._group()
                        for t, items in groups.items():
                            print(f"[{t}]")
                            for e in items:
                                act = "yes" if e.is_active else "no"
                                print(f"  {e.id:3d}. active={act:3s} {e.name} - {e.location}")
                            print()
                    else:
                        print("\nINFO: Environment created but not yet detected.")
                        print("      Run the script again to see all environments.")
            return

        self.assign_ids()
        print()
        print("Detected environments:")
        print("----------------------")

        groups = self._group()
        for t, items in groups.items():
            print(f"[{t}]")
            for e in items:
                act = "yes" if e.is_active else "no"
                print(f"  {e.id:3d}. active={act:3s} {e.name} - {e.location}")
            print()

        print("Options:")
        print("  - Enter environment number to show activation commands")
        print("  - Enter 'c' or 'create' to create a new environment")
        print("  - Press Enter to skip")
        
        sel = input("\nYour choice: ").strip().lower()
        if not sel:
            return
        
        # Check if user wants to create new environment
        if sel in ['c', 'create']:
            print()
            creator = EnvironmentCreator(self.project_dir, self.logger)
            success = creator.interactive_create()
            
            # Re-scan after creation to show the new environment
            if success:
                print("\nRe-scanning for environments...")
                scanner = EnvironmentScanner(
                    project_dir=self.project_dir,
                    logger=self.logger,
                    only_project=False,  # Scan both local AND global to find conda envs
                    type_filters=[]
                )
                new_envs = scanner.scan_all()
                if new_envs:
                    self.envs = new_envs
                    self.assign_ids()
                    print("\nUpdated environment list:")
                    print("----------------------")
                    groups = self._group()
                    for t, items in groups.items():
                        print(f"[{t}]")
                        for e in items:
                            act = "yes" if e.is_active else "no"
                            print(f"  {e.id:3d}. active={act:3s} {e.name} - {e.location}")
                        print()
                else:
                    print("\nINFO: Environment created but not yet detected.")
                    print("      Run the script again to see all environments.")
            return
        
        # Try to parse as environment number
        try:
            num = int(sel)
        except:
            print("Invalid selection.")
            return
        e = next((x for x in self.envs if x.id == num), None)
        if not e:
            print("Invalid selection.")
            return

        cmds = ActivationCommandBuilder.build(e)
        print()
        print(f"Activation commands for: {e.name} ({e.type})")
        for shell, cmd in cmds.items():
            print(f"{shell}: {cmd}")
        print()
        
        # Ask if user wants to generate activation script
        generate = input("Generate activation script for this environment? [Y/n]: ").strip().lower()
        if generate in ['', 'y', 'yes']:
            # Determine script name based on environment type
            script_mapping = {
                'venv': 'activate_venv.ps1',
                'conda': 'activate_conda.ps1',
                'poetry': 'activate_poetry.ps1',
                'pipenv': 'activate_pipenv.ps1',
                'pdm': 'activate_pdm.ps1',
                'hatch': 'activate_hatch.ps1',
                'pyenv': 'activate_pyenv.ps1'
            }
            
            script_name = script_mapping.get(e.type, f'activate_{e.type}.ps1')
            script_path = os.path.join(self.project_dir, script_name)
            
            # Get the PowerShell activation command
            activation_cmd = cmds.get('powershell', cmds.get('cmd.exe', ''))
            
            if activation_cmd:
                with open(script_path, 'w') as f:
                    f.write(activation_cmd + '\n')
                
                # Create a marker file to tell wrapper which script to activate
                marker_path = os.path.join(self.project_dir, '.last_generated_env')
                with open(marker_path, 'w') as f:
                    f.write(script_name)
                
                print(f"\nSUCCESS: Activation script generated!")
                print(f"Location: {script_path}")
                print(f"\nTo activate, run:")
                print(f"  .\\env_wrapper.ps1")
                print(f"\nOr manually:")
                print(f"  .\\{script_name}")
            else:
                print("\nWARNING: Could not generate activation script for this environment type.")
        print()

    def show_table(self):
        if not self.envs:
            self.logger.info("No environments found in project")
            print("WARNING: No environments found.")
            print("\nWould you like to create a new environment?")
            choice = input("[y/N]: ").strip().lower()
            if choice == "y":
                creator = EnvironmentCreator(self.project_dir, self.logger)
                success = creator.interactive_create()
                
                # Re-scan after creation
                if success:
                    print("\nRe-scanning for environments...")
                    scanner = EnvironmentScanner(
                        project_dir=self.project_dir,
                        logger=self.logger,
                        only_project=True,
                        type_filters=[]
                    )
                    new_envs = scanner.scan_only_project()
                    if new_envs:
                        self.envs = new_envs
                        self.assign_ids()
                        print("\nDetected environments after creation:")
                        print("----------------------")
                        header = f"{'ID':<4} {'Type':<15} {'Active':<7} {'Name':<20} Location"
                        print(header)
                        print("-" * len(header))
                        for e in self.envs:
                            act = "yes" if e.is_active else "no"
                            print(f"{e.id:<4} {e.type:<15} {act:<7} {e.name:<20} {e.location}")
                        print()
            return
        self.assign_ids()
        print()
        print("Detected environments:")
        print("----------------------")
        header = f"{'ID':<4} {'Type':<15} {'Active':<7} {'Name':<20} Location"
        print(header)
        print("-" * len(header))
        for e in self.envs:
            act = "yes" if e.is_active else "no"
            print(f"{e.id:<4} {e.type:<15} {act:<7} {e.name:<20} {e.location}")
        print()

    def show_json(self):
        print(json.dumps([e.to_dict() for e in self.envs], indent=2))

    def show_tui(self):
        try:
            from prompt_toolkit import prompt
            from prompt_toolkit.completion import WordCompleter
        except ImportError:
            print("prompt_toolkit not installed. Falling back to menu.")
            return self.show_menu()

        if not self.envs:
            self.logger.info("No environments found in project")
            print("WARNING: No environments found.")
            print("\nWould you like to create a new environment?")
            choice = input("[y/N]: ").strip().lower()
            if choice == "y":
                creator = EnvironmentCreator(self.project_dir, self.logger)
                creator.interactive_create()
            return

        self.assign_ids()
        labels = [f"{e.name} ({e.type})" for e in self.envs]
        mapping = {labels[i]: self.envs[i] for i in range(len(self.envs))}
        completer = WordCompleter(labels)

        choice = prompt("Select environment: ", completer=completer).strip()
        if not choice:
            return
        if choice not in mapping:
            print("Not found.")
            return

        e = mapping[choice]
        cmds = ActivationCommandBuilder.build(e)
        print()
        print(f"Activation commands for: {e.name} ({e.type})")
        for sh, cmd in cmds.items():
            print(f"{sh}: {cmd}")
        print()

    def _group(self):
        out: Dict[str, List[Environment]] = {}
        for e in self.envs:
            out.setdefault(e.type, []).append(e)
        for k in out:
            out[k].sort(key=lambda x: (not x.is_active, x.name.lower()))
        return dict(sorted(out.items(), key=lambda kv: kv[0]))
class EnvironmentDeleter:
    """Handles deletion of local environments."""
    
    def __init__(self, project_dir: str, logger: logging.Logger):
        self.project_dir = os.path.abspath(project_dir)
        self.logger = logger
    
    def delete_venv(self, path: str) -> bool:
        """Delete a venv/poetry/pipenv environment directory."""
        try:
            self.logger.info(f"Deleting environment directory: {path}")
            print(f"Deleting environment at {path}...")
            
            # Use onerror handler for Windows permission issues
            def handle_remove_error(func, path, exc_info):
                """Error handler for Windows readonly files."""
                import stat
                # Try to change permissions and retry
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception as e:
                    self.logger.warning(f"Could not delete {path}: {e}")
            
            shutil.rmtree(path, onerror=handle_remove_error)
            self.logger.info(f"Successfully deleted: {path}")
            print(f"SUCCESS: Deleted {path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete {path}: {e}")
            print(f"ERROR: Failed to delete {path}: {e}")
            print(f"TIP: Try running as Administrator or close any programs using this environment.")
            return False
    
    def delete_conda_env(self, name: str) -> bool:
        """Delete a conda environment."""
        try:
            self.logger.info(f"Deleting conda environment: {name}")
            print(f"Deleting conda environment '{name}'...")
            subprocess.run(["conda", "env", "remove", "-n", name, "-y"], check=True)
            self.logger.info(f"Successfully deleted conda environment: {name}")
            print(f"SUCCESS: Deleted conda environment '{name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete conda environment {name}: {e}")
            print(f"ERROR: Failed to delete conda environment '{name}': {e}")
            return False
    
    def delete_pdm_env(self, path: str) -> bool:
        """Delete PDM __pypackages__ directory."""
        try:
            self.logger.info(f"Deleting PDM environment: {path}")
            print(f"Deleting PDM environment at {path}...")
            shutil.rmtree(path)
            self.logger.info(f"Successfully deleted PDM environment: {path}")
            print(f"SUCCESS: Deleted PDM environment")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete PDM environment {path}: {e}")
            print(f"ERROR: Failed to delete PDM environment: {e}")
            return False
    
    def interactive_delete(self, envs: List[Environment]) -> int:
        """Interactive environment deletion wizard."""
        if not envs:
            print("WARNING: No local environments found to delete.")
            return 0
        
        print("\n" + "="*70)
        print("Environment Deletion Wizard")
        print("="*70)
        print("\nLocal environments found:")
        print("-"*70)
        
        for i, env in enumerate(envs, 1):
            print(f"  {i}. [{env.type}] {env.name} - {env.location}")
        
        print("-"*70)
        print("\nEnter environment number(s) to delete:")
        print("  - Single: 1")
        print("  - Multiple: 1,3,5")
        print("  - Range: 1-3")
        print("  - All: all")
        print("  - Cancel: 0 or press Enter")
        
        selection = input("\nSelect: ").strip()
        
        if not selection or selection == "0":
            self.logger.info("Deletion cancelled by user")
            print("Cancelled.")
            return 0
        
        # Parse selection
        selected_indices = self._parse_selection(selection, len(envs))
        if not selected_indices:
            print("ERROR: Invalid selection.")
            return 0
        
        selected_envs = [envs[i-1] for i in selected_indices]
        
        # Show confirmation
        print(f"\nYou are about to delete {len(selected_envs)} environment(s):")
        for env in selected_envs:
            print(f"  - [{env.type}] {env.name}")
        
        confirm = input(f"\nAre you sure? Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            self.logger.info("Deletion cancelled by user")
            print("Cancelled.")
            return 0
        
        # Delete environments
        deleted_count = 0
        failed_count = 0
        
        print()
        for env in selected_envs:
            print(f"Processing: [{env.type}] {env.name}...")
            success = False
            
            if env.type in ("venv", "poetry", "pipenv", "hatch"):
                success = self.delete_venv(env.location)
            elif env.type == "conda":
                # Check if it's a local conda env (has path in project)
                if env.location and env.location.startswith(self.project_dir):
                    success = self.delete_venv(env.location)
                else:
                    success = self.delete_conda_env(env.name)
            elif env.type == "pdm":
                success = self.delete_pdm_env(env.location)
            else:
                print(f"WARNING: Deletion not supported for type '{env.type}'")
                failed_count += 1
                continue
            
            if success:
                deleted_count += 1
            else:
                failed_count += 1
        
        print("\n" + "="*70)
        print(f"Deletion Summary: {deleted_count} deleted, {failed_count} failed")
        print("="*70 + "\n")
        
        return deleted_count
    
    def _parse_selection(self, selection: str, max_count: int) -> List[int]:
        """Parse user selection input (e.g., '1,3,5' or '1-3' or 'all')."""
        indices = set()
        
        if selection.lower() == "all":
            return list(range(1, max_count + 1))
        
        parts = selection.split(',')
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Range: 1-3
                try:
                    start, end = part.split('-')
                    start, end = int(start.strip()), int(end.strip())
                    if 1 <= start <= max_count and 1 <= end <= max_count and start <= end:
                        indices.update(range(start, end + 1))
                    else:
                        return []
                except:
                    return []
            else:
                # Single number
                try:
                    num = int(part)
                    if 1 <= num <= max_count:
                        indices.add(num)
                    else:
                        return []
                except:
                    return []
        
        return sorted(list(indices))


class EnvironmentSwitcher:
    """Handles switching between environments (deactivate current, activate another)."""
    
    def __init__(self, project_dir: str, logger: logging.Logger):
        self.project_dir = os.path.abspath(project_dir)
        self.logger = logger
    
    def get_active_environment(self) -> Optional[Dict[str, str]]:
        """Detect currently active environment."""
        active_env = {}
        
        # Check VIRTUAL_ENV (venv, poetry, pipenv, hatch)
        venv_path = os.environ.get("VIRTUAL_ENV")
        if venv_path:
            active_env['type'] = 'venv/poetry/pipenv'
            active_env['path'] = venv_path
            active_env['name'] = os.path.basename(venv_path)
            return active_env
        
        # Check CONDA_DEFAULT_ENV (conda)
        conda_env = os.environ.get("CONDA_DEFAULT_ENV")
        if conda_env:
            active_env['type'] = 'conda'
            active_env['name'] = conda_env
            active_env['path'] = os.environ.get("CONDA_PREFIX", "")
            return active_env
        
        return None
    
    def generate_deactivation_script(self, env_info: Dict[str, str]) -> str:
        """Generate deactivation command based on environment type."""
        if env_info['type'] == 'conda':
            return "conda deactivate"
        else:
            # venv/poetry/pipenv/hatch all use 'deactivate'
            return "deactivate"
    
    def generate_activation_script(self, env: Environment) -> Optional[str]:
        """Generate activation command for target environment."""
        system = platform.system()
        
        if env.type == "conda":
            # Use the actual conda environment name, not the display name
            # For conda, env.location is the path, we need to extract the env name
            if env.location:
                # Check if it's base environment
                if os.path.basename(env.location).lower() in ('miniconda3', 'anaconda3', 'miniforge3'):
                    return 'conda activate base'
                # Check if it's in envs folder
                elif '\\envs\\' in env.location or '/envs/' in env.location:
                    env_name = os.path.basename(env.location)
                    return f'conda activate "{env_name}"'
                else:
                    # It might be base
                    return 'conda activate base'
            return f'conda activate "{env.name}"'
        
        elif env.type in ("venv", "poetry", "pipenv", "hatch", "pyenv"):
            if not env.location:
                return None
            
            if system == "Windows":
                scripts_dir = os.path.join(env.location, "Scripts")
                activate_ps1 = os.path.join(scripts_dir, "Activate.ps1")
                if os.path.exists(activate_ps1):
                    return f'& "{activate_ps1}"'
            else:
                bin_dir = os.path.join(env.location, "bin")
                activate_sh = os.path.join(bin_dir, "activate")
                if os.path.exists(activate_sh):
                    return f'source "{activate_sh}"'
        
        elif env.type == "pdm":
            return "pdm shell"
        
        return None
    
    def interactive_switch(self, environments: List[Environment]) -> bool:
        """Interactively switch from current environment to another."""
        print("\n" + "="*70)
        print("Environment Switcher")
        print("="*70)
        
        # Check current environment
        current_env = self.get_active_environment()
        
        if current_env:
            print(f"\nCurrently Active Environment:")
            print(f"  Type: {current_env['type']}")
            print(f"  Name: {current_env['name']}")
            print(f"  Path: {current_env.get('path', 'N/A')}")
        else:
            print(f"\nNo environment currently active.")
            print(f"TIP: You can activate an environment directly without switching.")
        
        # Filter switchable environments
        switchable = [e for e in environments if e.type in ('venv', 'conda', 'poetry', 'pipenv', 'hatch', 'pyenv', 'pdm')]
        
        if not switchable:
            print(f"\nERROR: No switchable environments found.")
            print(f"TIP: Create an environment first using the creation wizard.")
            return False
        
        # Display available environments
        print(f"\n{'='*70}")
        print(f"Available Environments to Switch To:")
        print(f"{'='*70}")
        
        for idx, env in enumerate(switchable, 1):
            status = "[ACTIVE]" if env.is_active else ""
            print(f"{idx}. {env.name:<30} Type: {env.type:<15} {status}")
            if env.location:
                print(f"   Location: {env.location}")
        
        print(f"{'='*70}")
        
        # Get user selection
        selection = input(f"\nSelect environment to activate [1-{len(switchable)}] or 'q' to quit: ").strip()
        
        if selection.lower() == 'q':
            print("Cancelled.")
            return False
        
        try:
            selected_idx = int(selection)
            if selected_idx < 1 or selected_idx > len(switchable):
                print(f"ERROR: Invalid selection. Must be between 1 and {len(switchable)}.")
                return False
        except ValueError:
            print(f"ERROR: Invalid input. Please enter a number.")
            return False
        
        target_env = switchable[selected_idx - 1]
        
        # Generate switch script
        script_lines = []
        
        if current_env:
            deactivate_cmd = self.generate_deactivation_script(current_env)
            script_lines.append(f"# Deactivate current environment")
            script_lines.append(deactivate_cmd)
            script_lines.append("")
        
        activation_cmd = self.generate_activation_script(target_env)
        if not activation_cmd:
            print(f"\nERROR: Could not generate activation command for {target_env.name}")
            return False
        
        script_lines.append(f"# Activate target environment: {target_env.name}")
        script_lines.append(activation_cmd)
        
        # Save switch script
        switch_script = os.path.join(self.project_dir, "switch_env.ps1")
        try:
            with open(switch_script, 'w') as f:
                f.write('\n'.join(script_lines))
            
            print(f"\n{'='*70}")
            print(f"Environment Switch Script Generated")
            print(f"{'='*70}")
            print(f"\nTo switch environments, run:")
            print(f"\n    .\\switch_env.ps1")
            print(f"\nScript saved to: {switch_script}")
            print(f"\nCommands in script:")
            for line in script_lines:
                if line and not line.startswith('#'):
                    print(f"  {line}")
            print(f"\n{'='*70}\n")
            
            self.logger.info(f"Generated switch script: {switch_script}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create switch script: {e}")
            print(f"ERROR: Failed to create switch script: {e}")
            return False
    
    def deactivate_current(self) -> bool:
        """Deactivate the currently active environment."""
        print("\n" + "="*70)
        print("Environment Deactivator")
        print("="*70)
        
        current_env = self.get_active_environment()
        
        if not current_env:
            print(f"\nNo environment currently active.")
            print(f"Nothing to deactivate.")
            return False
        
        print(f"\nCurrently Active Environment:")
        print(f"  Type: {current_env['type']}")
        print(f"  Name: {current_env['name']}")
        print(f"  Path: {current_env.get('path', 'N/A')}")
        
        # Generate deactivation script
        deactivate_cmd = self.generate_deactivation_script(current_env)
        
        # Save deactivation script
        deactivate_script = os.path.join(self.project_dir, "deactivate_env.ps1")
        try:
            with open(deactivate_script, 'w') as f:
                f.write(f"# Deactivate current environment: {current_env['name']}\n")
                f.write(deactivate_cmd)
            
            print(f"\n{'='*70}")
            print(f"Deactivation Script Generated")
            print(f"{'='*70}")
            print(f"\nTo deactivate the current environment, run:")
            print(f"\n    .\\deactivate_env.ps1")
            print(f"\nScript saved to: {deactivate_script}")
            print(f"\nCommand: {deactivate_cmd}")
            print(f"\n{'='*70}\n")
            
            self.logger.info(f"Generated deactivation script: {deactivate_script}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create deactivation script: {e}")
            print(f"ERROR: Failed to create deactivation script: {e}")
            return False


class EnvironmentVerifier:
    """Verifies availability of environment package managers."""
    
    PACKAGE_MANAGERS = {
        'venv': {
            'command': [sys.executable, '-m', 'venv', '--help'],
            'description': 'Python venv (built-in)',
            'required': True
        },
        'conda': {
            'command': ['conda', '--version'],
            'description': 'Conda package manager',
            'required': False
        },
        'poetry': {
            'command': ['poetry', '--version'],
            'description': 'Poetry dependency manager',
            'required': False
        },
        'pipenv': {
            'command': ['pipenv', '--version'],
            'description': 'Pipenv package manager',
            'required': False
        },
        'pdm': {
            'command': ['pdm', '--version'],
            'description': 'PDM package manager',
            'required': False
        },
        'hatch': {
            'command': ['hatch', '--version'],
            'description': 'Hatch project manager',
            'required': False
        },
        'pyenv': {
            'command': ['pyenv', '--version'],
            'description': 'Pyenv version manager',
            'required': False,
            'fallback_windows': lambda: os.path.join(os.environ.get('USERPROFILE', ''), '.pyenv', 'pyenv-win', 'bin', 'pyenv.bat')
        },
        'docker': {
            'command': ['docker', '--version'],
            'description': 'Docker containerization',
            'required': False
        }
    }
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.results = {}
    
    def _check_command(self, cmd: List[str]) -> tuple[bool, str]:
        """Check if a command is available and return its version."""
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip()
                return True, version.split('\n')[0]  # First line only
            return False, "Command failed"
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except FileNotFoundError:
            return False, "Not found"
        except Exception as e:
            return False, str(e)
    
    def verify_all(self) -> Dict[str, Dict[str, Any]]:
        """Verify all package managers and return results."""
        self.logger.info("Starting package manager verification")
        
        for name, config in self.PACKAGE_MANAGERS.items():
            self.logger.debug(f"Checking {name}...")
            available, version = self._check_command(config['command'])
            
            # Try fallback location for Windows-specific tools
            if not available and platform.system() == "Windows" and 'fallback_windows' in config:
                fallback_path = config['fallback_windows']()
                if os.path.exists(fallback_path):
                    available, version = self._check_command([fallback_path, '--version'])
                    if available:
                        version = f"{version} (found at {fallback_path}, not in PATH)"
            
            self.results[name] = {
                'available': available,
                'version': version,
                'description': config['description'],
                'required': config['required']
            }
            
            if available:
                self.logger.info(f"{name}: Available - {version}")
            else:
                level = logging.WARNING if config['required'] else logging.DEBUG
                self.logger.log(level, f"{name}: Not available - {version}")
        
        return self.results
    
    def print_report(self):
        """Print a formatted verification report."""
        if not self.results:
            self.verify_all()
        
        print("\n" + "="*70)
        print("Environment Package Manager Verification")
        print("="*70)
        print(f"\nSystem: {platform.system()} {platform.release()}")
        print(f"Python: {sys.version.split()[0]} ({sys.executable})")
        print("\n" + "-"*70)
        
        # Header
        print(f"{'Package Manager':<20} {'Status':<12} {'Version/Info':<38}")
        print("-"*70)
        
        available_count = 0
        required_missing = []
        
        for name, result in sorted(self.results.items()):
            status = "AVAILABLE" if result['available'] else "NOT FOUND"
            status_display = status
            
            if result['available']:
                available_count += 1
            elif result['required']:
                required_missing.append(name)
                status_display = "MISSING*"
            
            version_info = result['version'] if len(result['version']) <= 38 else result['version'][:35] + "..."
            print(f"{name:<20} {status_display:<12} {version_info:<38}")
        
        print("-"*70)
        print(f"\nSummary: {available_count}/{len(self.results)} package managers available")
        
        if required_missing:
            print(f"\nWARNING: Required package managers missing: {', '.join(required_missing)}")
            print("* Required package managers must be installed")
        
        # Installation hints
        missing = [name for name, result in self.results.items() if not result['available']]
        if missing:
            print(f"\n{'-'*70}")
            print("Installation Commands:")
            print(f"{'-'*70}")
            
            # Platform-specific installation commands
            is_windows = platform.system() == "Windows"
            
            hints = {
                'venv': {
                    'windows': 'python -m pip install --user virtualenv',
                    'unix': 'pip install virtualenv'
                },
                'conda': {
                    'windows': 'Invoke-WebRequest -Uri "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" -OutFile ".\\Downloads\\Miniconda3-latest-Windows-x86_64.exe"',
                    'unix': 'wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && bash Miniconda3-latest-Linux-x86_64.sh'
                },
                'poetry': {
                    'windows': '(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -',
                    'unix': 'curl -sSL https://install.python-poetry.org | python3 -'
                },
                'pipenv': {
                    'windows': 'pip install pipenv',
                    'unix': 'pip install pipenv'
                },
                'pdm': {
                    'windows': 'powershell -ExecutionPolicy ByPass -c "irm https://pdm-project.org/install-pdm.py | py -"',
                    'unix': 'curl -sSL https://pdm-project.org/install-pdm.py | python3 -'
                },
                'hatch': {
                    'windows': 'pip install hatch',
                    'unix': 'pip install hatch'
                },
                'pyenv': {
                    'windows': 'Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" -OutFile "./install-pyenv-win.ps1"; &"./install-pyenv-win.ps1"',
                    'unix': 'curl https://pyenv.run | bash'
                },
                'docker': {
                    'windows': 'Download from: https://www.docker.com/products/docker-desktop',
                    'unix': 'Download from: https://docs.docker.com/engine/install/'
                }
            }
            
            for name in missing:
                if name in hints:
                    cmd = hints[name]['windows'] if is_windows else hints[name]['unix']
                    print(f"\n  {name}:")
                    print(f"    {cmd}")
                    
                    # Add PATH note for pyenv on Windows
                    if name == 'pyenv' and is_windows:
                        result = self.results.get(name, {})
                        if 'not in PATH' in result.get('version', ''):
                            print(f"    NOTE: pyenv is installed but not in PATH.")
                            print(f"          Add to PATH: $env:USERPROFILE\\.pyenv\\pyenv-win\\bin")
                            print(f"          Or restart your terminal to apply environment changes.")
        
        print("="*70 + "\n")
        
        return available_count, len(required_missing)


class EnvManagerApp:
    def __init__(self):
        self.logger = logging.getLogger("env_manager")

    def configure_logging(self, level):
        lvl = getattr(logging, level.upper(), logging.WARNING)
        logging.basicConfig(
            level=lvl,
            format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
        )

    def parse_args(self):
        p = argparse.ArgumentParser(
            description="Python Environment Manager - Complete lifecycle management for Python environments",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
EXAMPLES:
  # Verify installed package managers
  python env_manager.py --verify
  
  # Create new environment interactively
  python env_manager.py
  
  # Switch between environments
  python env_manager.py --switch
  
  # Deactivate current environment
  python env_manager.py --deactivate
  
  # Delete environments interactively
  python env_manager.py --delete
  
  # Scan only project environments
  python env_manager.py --scan project --output json
  
  # Filter by environment type
  python env_manager.py --type conda --type poetry

SUPPORTED ENVIRONMENT TYPES:
  venv      - Python built-in virtual environments
  conda     - Conda package manager environments
  poetry    - Poetry dependency manager environments
  pipenv    - Pipenv virtual environments
  pdm       - PDM package manager environments
  hatch     - Hatch project manager environments
  pyenv     - Pyenv Python version manager
  docker    - Docker containerized environments

POWERSHELL WRAPPER:
  For automatic activation in your current shell, use:
    .\\env_wrapper.ps1              # Create environment
    .\\env_wrapper.ps1 -Action switch    # Switch environments
    .\\env_wrapper.ps1 -Action deactivate # Deactivate environment

NOTES:
  - Python subprocesses cannot modify parent shell environment variables
  - Generated scripts (activate_poetry.ps1, switch_env.ps1, deactivate_env.ps1)
    must be executed in your shell to take effect
  - Use the env_wrapper.ps1 PowerShell wrapper for automatic execution
  
For detailed documentation, see: ENV_MANAGER_README.md
            """
        )
        p.add_argument("--project", "-p", default=".", 
                      help="Project directory to scan (default: current directory)")
        p.add_argument("--output", "-o", choices=["menu", "table", "tui", "json"], default="menu",
                      help="Output format: menu (default), table, tui, or json")
        p.add_argument("--log-level", "-l", default="WARNING",
                      help="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        p.add_argument("--type", "-t", action="append", 
                      help="Filter environment types (can be used multiple times). Example: --type conda --type poetry")
        p.add_argument("--only-project", action="store_true", 
                      help="Disable global environment scanning (only scan project-local environments)")
        p.add_argument(
         "--scan",
            choices=["project", "global", "all"],
            default="all",
            help="Which environments to scan: project (local only), global (system-wide), or all (default)"
        )
        p.add_argument("--verify", action="store_true", 
                      help="Verify availability of package managers and show installation instructions")
        p.add_argument("--delete", action="store_true", 
                      help="Delete local environments interactively with selection support (1,3,5 or 1-3 or all)")
        p.add_argument("--switch", action="store_true", 
                      help="Switch between environments (deactivate current, activate another)")
        p.add_argument("--deactivate", action="store_true", 
                      help="Deactivate the currently active environment")
        return p.parse_args()

    def run(self):
        args = self.parse_args()
        self.configure_logging(args.log_level)
        
        # Handle --verify flag
        if args.verify:
            verifier = EnvironmentVerifier(self.logger)
            verifier.verify_all()
            available_count, missing_required = verifier.print_report()
            
            # Exit with appropriate code
            if missing_required > 0:
                sys.exit(1)  # Required package managers missing
            sys.exit(0)  # All good
        
        # Handle --delete flag
        if args.delete:
            if not os.path.exists(args.project):
                print(f"ERROR: Project directory '{args.project}' does not exist.")
                sys.exit(1)
            
            scanner = EnvironmentScanner(
                project_dir=args.project,
                logger=self.logger,
                only_project=True,  # Only scan local for deletion
                type_filters=args.type or []
            )
            
            environments = scanner.scan_only_project()
            deleter = EnvironmentDeleter(args.project, self.logger)
            deleted_count = deleter.interactive_delete(environments)
            
            sys.exit(0 if deleted_count >= 0 else 1)
        
        # Handle --switch flag
        if args.switch:
            if not os.path.exists(args.project):
                print(f"ERROR: Project directory '{args.project}' does not exist.")
                sys.exit(1)
            
            scanner = EnvironmentScanner(
                project_dir=args.project,
                logger=self.logger,
                only_project=False,  # Scan both local and global
                type_filters=args.type or []
            )
            
            environments = scanner.scan_all()
            switcher = EnvironmentSwitcher(args.project, self.logger)
            success = switcher.interactive_switch(environments)
            
            sys.exit(0 if success else 1)
        
        # Handle --deactivate flag
        if args.deactivate:
            if not os.path.exists(args.project):
                print(f"ERROR: Project directory '{args.project}' does not exist.")
                sys.exit(1)
            
            switcher = EnvironmentSwitcher(args.project, self.logger)
            success = switcher.deactivate_current()
            
            sys.exit(0 if success else 1)
        
        # Ensure project directory exists
        if not os.path.exists(args.project):
            self.logger.warning(f"Project directory '{args.project}' does not exist")
            print(f"WARNING: Project directory '{args.project}' does not exist.")
            create_dir = input("Would you like to create it? [y/N]: ").strip().lower()
            if create_dir == "y":
                try:
                    os.makedirs(args.project, exist_ok=True)
                    self.logger.info(f"Created directory: {os.path.abspath(args.project)}")
                    print(f"SUCCESS: Created directory: {os.path.abspath(args.project)}")
                except Exception as e:
                    self.logger.error(f"Failed to create directory: {e}")
                    print(f"ERROR: Failed to create directory: {e}")
                    return
            else:
                self.logger.info("User declined to create directory")
                print("Exiting.")
                return

        scanner = EnvironmentScanner(
            project_dir=args.project,
            logger=self.logger,
            only_project=args.only_project,
            type_filters=args.type or []
        )

        if args.scan == "project":
            environments = scanner.scan_only_project()

        elif args.scan == "global":
            environments = scanner.scan_only_global()

        else:  # "all"
            environments = scanner.scan_all()
        presenter = EnvironmentPresenter(environments, project_dir=args.project, logger=self.logger)

        if args.output == "menu":
            presenter.show_menu()
            print()
            print("JSON output:")
            presenter.show_json()

        elif args.output == "table":
            presenter.show_table()
            print("JSON output:")
            presenter.show_json()

        elif args.output == "tui":
            presenter.show_tui()
            print()
            print("JSON output:")
            presenter.show_json()

        elif args.output == "json":
            presenter.show_json()


if __name__ == "__main__":
    EnvManagerApp().run()
    # End of env_manager.py    