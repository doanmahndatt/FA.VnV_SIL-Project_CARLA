from pathlib import Path
import itertools
import argparse
import shutil
import yaml
import os
import stat
import time
import sys
from typing import Dict, List, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.project_paths import get_project_paths


# ==================================================
# Configuration
# ==================================================

PROJECT_PATHS = get_project_paths(Path(__file__))
BASE_SCENARIO_DIR = PROJECT_PATHS.scenarios_root
LOGICAL_DIR = BASE_SCENARIO_DIR / "logical"
PARAMETER_DIR = BASE_SCENARIO_DIR / "parameters"
CORE_DIR = BASE_SCENARIO_DIR / "core"


# ==================================================
# YAML Utilities
# ==================================================

def load_yaml(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data: Dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False)


# ==================================================
# Windows-safe clean logic (RENAME strategy)
# ==================================================

def _handle_remove_readonly(func, path, exc):
    excvalue = exc[1]
    if func in (os.remove, os.rmdir, os.unlink) and excvalue.errno == 5:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise


def prepare_output_dir(output_dir: Path, clean: bool) -> None:
    """
    Windows-robust clean:
    - Rename old folder instead of deleting directly
    - Create fresh folder immediately
    - Best-effort delete renamed folder
    """
    if not clean or not output_dir.exists():
        return

    timestamp = int(time.time())
    trash_dir = output_dir.parent / f".trash_{output_dir.name}_{timestamp}"

    print(f"[CLEAN] Renaming {output_dir} -> {trash_dir}")

    try:
        output_dir.rename(trash_dir)
    except PermissionError:
        print(f"[WARN] Cannot rename {output_dir}, skipping clean")
        return

    # Try deleting trash in background style
    try:
        shutil.rmtree(trash_dir, onerror=_handle_remove_readonly)
        print(f"[CLEAN] Removed old folder: {trash_dir}")
    except Exception as e:
        print(f"[WARN] Old folder kept (locked): {trash_dir}")
        print(f"       Reason: {e}")


# ==================================================
# Parameter Expansion
# ==================================================

def generate_parameter_combinations(
    parameters: Dict[str, List]
) -> Iterable[Dict[str, object]]:
    keys = list(parameters.keys())
    values = list(parameters.values())
    for combo in itertools.product(*values):
        yield dict(zip(keys, combo))


def validate_constraints(
    parameter_instance: Dict[str, object],
    constraints: List[str]
) -> bool:
    for rule in constraints:
        if not eval(rule, {}, parameter_instance):
            return False
    return True


# ==================================================
# Core Scenario Builder
# ==================================================

def build_core_scenario(
    base_scenario_id: str,
    index: int,
    logical: Dict,
    parameters: Dict
) -> Dict:
    return {
        "scenario_id": f"{base_scenario_id}_{index:03d}",
        "logic": logical,
        "parameters": parameters
    }


# ==================================================
# Expansion Logic
# ==================================================

def expand_single_scenario(scenario_id: str, clean: bool = False) -> None:
    logical_path = LOGICAL_DIR / f"{scenario_id}.yaml"
    parameter_path = PARAMETER_DIR / f"{scenario_id.replace('csc', 'par')}.yaml"
    output_dir = CORE_DIR / scenario_id

    print(f"\n[INFO] Expanding scenario: {scenario_id}")

    prepare_output_dir(output_dir, clean)

    logical = load_yaml(logical_path)
    param_cfg = load_yaml(parameter_path)

    parameters = param_cfg.get("parameters", {})
    constraints = param_cfg.get("constraints", [])

    generated = 0
    skipped = 0

    for instance in generate_parameter_combinations(parameters):
        if constraints and not validate_constraints(instance, constraints):
            skipped += 1
            continue

        generated += 1
        core = build_core_scenario(
            scenario_id,
            generated,
            logical,
            instance
        )

        output_path = output_dir / f"{core['scenario_id']}.yaml"
        save_yaml(core, output_path)

    print(
        f"[DONE] {scenario_id}: generated={generated}, skipped={skipped}"
    )


def expand_range(prefix: str, start: int, end: int, clean: bool) -> None:
    for i in range(start, end + 1):
        scenario_id = f"{prefix}_{i:03d}"
        try:
            expand_single_scenario(scenario_id, clean=clean)
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")


# ==================================================
# CLI
# ==================================================

def main():
    parser = argparse.ArgumentParser(description="Scenario Expander")

    parser.add_argument("prefix", help="Scenario prefix (e.g. acc_csc)")
    parser.add_argument("suffix", nargs="?", help="Scenario suffix (e.g. 003)")
    parser.add_argument("--from", dest="start", type=int)
    parser.add_argument("--to", dest="end", type=int)
    parser.add_argument("--clean", action="store_true")

    args = parser.parse_args()

    if args.suffix:
        expand_single_scenario(
            f"{args.prefix}_{int(args.suffix):03d}",
            clean=args.clean
        )
        return

    if args.start is not None and args.end is not None:
        expand_range(args.prefix, args.start, args.end, clean=args.clean)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
