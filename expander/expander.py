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

FEATURE_DOMAIN_DIRS = {
    "Longitudinal": "longitudinal_feature",
    "Lateral": "lateral_feature",
    "Parking": "parking_feature",
    "Brake": "brake_feature",
}


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


def to_feature_domain_dir(feature_domain: str) -> str:
    feature_domain = str(feature_domain).strip()
    if feature_domain in FEATURE_DOMAIN_DIRS:
        return FEATURE_DOMAIN_DIRS[feature_domain]
    return f"{feature_domain.lower().replace(' ', '_')}_feature"


def to_functional_dir(functional: str) -> str:
    return str(functional).strip()


def normalize_selector_part(value: str) -> str:
    value = value.strip().replace("\\", "/").strip("/")
    value = value.lower().replace("-", "_")
    if value and not value.endswith("_feature"):
        value = f"{value}_feature"
    return value


def normalize_functional_part(value: str) -> str:
    return value.strip().replace("\\", "/").strip("/").upper()


def split_selector(selector: str) -> List[str]:
    return [part for part in selector.replace("\\", "/").strip("/").split("/") if part]


def logical_path_from_selector(selector: str) -> Path:
    parts = split_selector(selector)
    if len(parts) == 1:
        matches = sorted(LOGICAL_DIR.rglob(f"{parts[0]}.yaml"))
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise FileNotFoundError(f"Logical scenario not found: {selector}")
        raise RuntimeError(f"Ambiguous scenario selector '{selector}': {matches}")

    if len(parts) == 3:
        domain_dir = normalize_selector_part(parts[0])
        functional_dir = normalize_functional_part(parts[1])
        scenario_id = parts[2]
        return LOGICAL_DIR / domain_dir / functional_dir / f"{scenario_id}.yaml"

    raise ValueError(
        "Selector must be '<scenario_id>' or '<feature_domain>/<functional>/<scenario_id>'"
    )


def logical_dir_from_selector(selector: str) -> Path:
    parts = split_selector(selector)
    if len(parts) != 2:
        raise ValueError("Folder selector must be '<feature_domain>/<functional>'")
    return LOGICAL_DIR / normalize_selector_part(parts[0]) / normalize_functional_part(parts[1])


def scenario_id_from_logical_path(logical_path: Path) -> str:
    return logical_path.stem


def parameter_path_for_logical(logical_path: Path, logical: Dict) -> Path:
    scenario_id = str(logical.get("scenario_id") or logical_path.stem)
    parameter_id = scenario_id.replace("csc", "par")
    relative_parent = logical_path.parent.relative_to(LOGICAL_DIR)
    return PARAMETER_DIR / relative_parent / f"{parameter_id}.yaml"


def output_dir_for_logical(logical: Dict, scenario_id: str) -> Path:
    functional = logical.get("functional")
    feature_domain = logical.get("feature_domain")

    if not functional or not feature_domain:
        raise RuntimeError(
            f"Logical YAML for {scenario_id} must define 'functional' and 'feature_domain'"
        )

    return (
        CORE_DIR
        / to_feature_domain_dir(str(feature_domain))
        / to_functional_dir(str(functional))
        / scenario_id
    )


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

def expand_single_logical(logical_path: Path, clean: bool = False) -> None:
    logical = load_yaml(logical_path)
    scenario_id = str(logical.get("scenario_id") or scenario_id_from_logical_path(logical_path))
    parameter_path = parameter_path_for_logical(logical_path, logical)
    output_dir = output_dir_for_logical(logical, scenario_id)

    print(f"\n[INFO] Expanding scenario: {scenario_id}")
    print(f"[INFO] Logical: {logical_path}")
    print(f"[INFO] Parameters: {parameter_path}")
    print(f"[INFO] Output: {output_dir}")

    prepare_output_dir(output_dir, clean)

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


def expand_single_scenario(selector: str, clean: bool = False) -> None:
    expand_single_logical(logical_path_from_selector(selector), clean=clean)


def expand_folder(selector: str, clean: bool = False) -> None:
    logical_dir = logical_dir_from_selector(selector)
    if not logical_dir.exists():
        raise FileNotFoundError(f"Logical folder not found: {logical_dir}")

    for logical_path in sorted(logical_dir.glob("*.yaml")):
        try:
            expand_single_logical(logical_path, clean=clean)
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")


def expand_all(clean: bool = False) -> None:
    for logical_path in sorted(LOGICAL_DIR.rglob("*.yaml")):
        try:
            expand_single_logical(logical_path, clean=clean)
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")


def expand_range(selector_prefix: str, start: int, end: int, clean: bool) -> None:
    for i in range(start, end + 1):
        selector = f"{selector_prefix}_{i:03d}"
        try:
            expand_single_scenario(selector, clean=clean)
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")


# ==================================================
# CLI
# ==================================================

def main():
    parser = argparse.ArgumentParser(description="Scenario Expander")

    parser.add_argument(
        "selectors",
        nargs="*",
        help=(
            "Scenario or folder selector, e.g. "
            "longitudinal/acc/acc_csc_001 or longitudinal/acc"
        ),
    )
    parser.add_argument("--from", dest="start", type=int)
    parser.add_argument("--to", dest="end", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--clean", action="store_true")

    args = parser.parse_args()

    if args.all:
        expand_all(clean=args.clean)
        return

    if args.start is not None and args.end is not None:
        if len(args.selectors) != 1:
            parser.error("--from/--to requires exactly one selector prefix")
        expand_range(args.selectors[0], args.start, args.end, clean=args.clean)
        return

    if args.start is not None or args.end is not None:
        parser.error("--from and --to must be used together")

    if not args.selectors:
        parser.print_help()
        return

    for selector in args.selectors:
        parts = split_selector(selector)
        try:
            if len(parts) == 2:
                expand_folder(selector, clean=args.clean)
            else:
                expand_single_scenario(selector, clean=args.clean)
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")


if __name__ == "__main__":
    main()
