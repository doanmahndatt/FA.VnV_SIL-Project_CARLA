import yaml
import argparse
import re
import os
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from xml.dom import minidom

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.project_paths import get_project_paths

# =========================================================
# PATH
# =========================================================

PROJECT_PATHS = get_project_paths(Path(__file__))
BASE = PROJECT_PATHS.scenarios_root

FEATURE_DOMAIN_DIRS = {
    "Longitudinal": "longitudinal_feature",
    "Lateral": "lateral_feature",
    "Parking": "parking_feature",
    "Brake": "brake_feature",
}

FEATURE_DOMAIN_NAMES = {value: key for key, value in FEATURE_DOMAIN_DIRS.items()}

# =========================================================
# IO
# =========================================================


def load_yaml(path):
    """Load YAML file with UTF-8 encoding."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_text(path):
    """Load text file with UTF-8 encoding."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def to_feature_domain_dir(feature_domain):
    feature_domain = str(feature_domain).strip()
    if feature_domain in FEATURE_DOMAIN_DIRS:
        return FEATURE_DOMAIN_DIRS[feature_domain]
    return f"{feature_domain.lower().replace(' ', '_')}_feature"


def to_functional_dir(functional):
    return str(functional).strip()


def normalize_selector_part(value):
    value = value.strip().replace("\\", "/").strip("/")
    value = value.lower().replace("-", "_")
    if value and not value.endswith("_feature"):
        value = f"{value}_feature"
    return value


def normalize_functional_part(value):
    return value.strip().replace("\\", "/").strip("/").upper()


def split_selector(selector):
    return [part for part in selector.replace("\\", "/").strip("/").split("/") if part]


def canonical_feature_domain_dir(value):
    value = str(value).strip()
    if not value:
        return ""
    if value in FEATURE_DOMAIN_DIRS:
        return FEATURE_DOMAIN_DIRS[value]
    return normalize_selector_part(value)


def validate_selector_domain(selector, allowed_feature_domain_dir):
    if allowed_feature_domain_dir is None:
        return

    parts = split_selector(selector)
    if len(parts) < 2:
        return

    selector_domain = canonical_feature_domain_dir(parts[0])
    if selector_domain != allowed_feature_domain_dir:
        expected = FEATURE_DOMAIN_NAMES.get(allowed_feature_domain_dir, allowed_feature_domain_dir)
        raise ValueError(
            f"Selector '{selector}' belongs to '{selector_domain}', "
            f"but this generator only supports '{expected}'"
        )


def validate_core_domain(core, source, allowed_feature_domain_dir):
    if allowed_feature_domain_dir is None:
        return

    feature_domain, _ = metadata_from_core(core)
    core_domain = to_feature_domain_dir(feature_domain)
    if core_domain != allowed_feature_domain_dir:
        expected = FEATURE_DOMAIN_NAMES.get(allowed_feature_domain_dir, allowed_feature_domain_dir)
        raise RuntimeError(
            f"{source} belongs to feature_domain='{feature_domain}', "
            f"but this generator only supports '{expected}'"
        )


def scenario_prefix_from_case_id(case_id):
    return "_".join(str(case_id).split("_")[:3])


def metadata_from_core(core):
    logic = core.get("logic", {}) or {}
    functional = core.get("functional") or logic.get("functional")
    feature_domain = core.get("feature_domain") or logic.get("feature_domain")

    if not functional or not feature_domain:
        raise RuntimeError("Core YAML must define 'functional' and 'feature_domain'")

    return str(feature_domain).strip(), str(functional).strip()


def core_dir_from_selector(selector):
    parts = split_selector(selector)
    core_root = BASE / "core"

    if len(parts) == 1:
        matches = sorted(path for path in core_root.rglob(parts[0]) if path.is_dir())
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise FileNotFoundError(f"Core scenario folder not found: {selector}")
        raise RuntimeError(f"Ambiguous scenario selector '{selector}': {matches}")

    if len(parts) == 3:
        return (
            core_root
            / normalize_selector_part(parts[0])
            / normalize_functional_part(parts[1])
            / parts[2]
        )

    raise ValueError(
        "Selector must be '<scenario_id>' or '<feature_domain>/<functional>/<scenario_id>'"
    )


def core_parent_from_selector(selector):
    parts = split_selector(selector)
    if len(parts) != 2:
        raise ValueError("Folder selector must be '<feature_domain>/<functional>'")
    return BASE / "core" / normalize_selector_part(parts[0]) / normalize_functional_part(parts[1])


def output_dir_for_core(core):
    case_id = core.get("scenario_id")
    if not case_id:
        raise RuntimeError("Core YAML must define 'scenario_id'")

    feature_domain, functional = metadata_from_core(core)
    return (
        BASE
        / "generated"
        / "carla"
        / to_feature_domain_dir(feature_domain)
        / to_functional_dir(functional)
        / scenario_prefix_from_case_id(case_id)
    )


CONTROLLER_DEFAULTS = {
    "time_gap": "1.8",
    "time_headway": "1.8",
    "min_distance": "10.0",
    "kp_speed": "0.35",
    "kp_steer": "1.2",
    "max_throttle": "0.75",
    "max_brake": "0.65",
    "max_steer": "0.6",
    "waypoint_reached_threshold": "2.0",
    "fixed_delta_seconds": "0.05",
    "activation_offset": "0.20",
    "deadband_offset": "0.04",
    "kp_offset": "0.11",
    "kp_heading": "0.38",
    "kp_speed": "0.22",
    "offset_command_steer": "0.075",
    "lane_departure_disturbance_duration": "1.4",
    "scenario_duration": "34",
    "trigger_lane_departure_time_1": "5",
    "trigger_lane_departure_time_2": "12",
    "trigger_lane_departure_time_3": "19",
}


def resolve_controller_module(core):
    feature_domain, functional = metadata_from_core(core)
    controller_path = (
        Path("config")
        / "controllers_fmu"
        / to_feature_domain_dir(feature_domain)
        / to_functional_dir(functional)
        / f"{to_functional_dir(functional)}_fmu_controller.py"
    )

    if not (PROJECT_PATHS.repo_root / controller_path).exists():
        raise RuntimeError(
            "FMU controller module not found for "
            f"functional='{functional}', feature_domain='{feature_domain}'. "
            f"Expected: {PROJECT_PATHS.repo_root / controller_path}"
        )

    return controller_path.as_posix()


def resolve_controller_config(core):
    feature_domain, functional = metadata_from_core(core)
    config_path = (
        Path("config")
        / "controllers_fmu"
        / to_feature_domain_dir(feature_domain)
        / to_functional_dir(functional)
        / "signals.yaml"
    )

    if not (PROJECT_PATHS.repo_root / config_path).exists():
        raise RuntimeError(
            "FMU controller config not found for "
            f"functional='{functional}', feature_domain='{feature_domain}'. "
            f"Expected: {PROJECT_PATHS.repo_root / config_path}"
        )

    return config_path.as_posix()


def resolve_controller_fmu(core):
    feature_domain, functional = metadata_from_core(core)
    fmu_path = (
        Path("config")
        / "controllers_fmu"
        / to_feature_domain_dir(feature_domain)
        / to_functional_dir(functional)
        / f"{to_functional_dir(functional)}_controller.fmu"
    )

    if not (PROJECT_PATHS.repo_root / fmu_path).exists():
        raise RuntimeError(
            "FMU binary not found for "
            f"functional='{functional}', feature_domain='{feature_domain}'. "
            f"Expected: {PROJECT_PATHS.repo_root / fmu_path}"
        )

    return fmu_path.as_posix()


# =========================================================
# XML FORMATTING
# =========================================================


def prettify_xml(elem, indent="  "):
    rough_string = ET.tostring(elem, encoding="unicode")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent=indent)

    lines = [line for line in pretty_xml.split("\n") if line.strip()]

    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]

    return "\n".join(lines)


def write_xosc_file(tree, output_path):
    root = tree.getroot()
    pretty_xml = prettify_xml(root, indent="  ")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("<?xml version='1.0' encoding='utf-8'?>\n")
        f.write(pretty_xml)
        f.write("\n")


# =========================================================
# ENVIRONMENT MAPPING
# =========================================================


def map_environment(params):
    """Map scenario parameters to environment configuration."""
    light = params.get("light", "day")
    weather = params.get("weather", "clear")

    env = {}

    if light == "day":
        env.update(
            {
                "time_of_day": "2026-01-01T12:00:00",
                "sun_intensity": "1.0",
                "sun_elevation": "70",
            }
        )
    else:
        env.update(
            {
                "time_of_day": "2026-01-01T00:00:00",
                "sun_intensity": "0.05",
                "sun_elevation": "-10",
            }
        )

    if weather == "clear":
        env.update(
            {
                "cloud_state": "free",
                "fog_range": "100000",
                "precip_type": "dry",
                "precip_intensity": "0",
                "friction": "1.0",
            }
        )
    elif weather == "rain":
        env.update(
            {
                "cloud_state": "overcast",
                "fog_range": "30000",
                "precip_type": "rain",
                "precip_intensity": "0.7",
                "friction": "0.7",
            }
        )
    elif weather == "fog":
        env.update(
            {
                "cloud_state": "cloudy",
                "fog_range": "80",
                "precip_type": "dry",
                "precip_intensity": "0",
                "friction": "0.9",
            }
        )

    return env


# =========================================================
# MANEUVER BLOCK DISCOVERY
# =========================================================


def maneuver_block_dir(core):
    feature_domain, functional = metadata_from_core(core)
    return (
        BASE
        / "templates"
        / "maneuver_blocks"
        / to_feature_domain_dir(feature_domain)
        / to_functional_dir(functional)
    )


def normalize_event_type(event_name):
    event_name = str(event_name).strip()
    for prefix in ("${actor}_", "actor_"):
        if event_name.startswith(prefix):
            return event_name[len(prefix) :]
    return event_name


def discover_maneuver_blocks(core):
    block_dir = maneuver_block_dir(core)
    if not block_dir.exists():
        raise RuntimeError(f"Maneuver block directory not found: {block_dir}")

    block_map = {}

    for block_path in sorted(block_dir.glob("*.xosc")):
        text = load_text(block_path)
        parse_text = text.replace("${actor}", "actor")

        try:
            group = ET.fromstring(parse_text)
        except ET.ParseError as e:
            raise RuntimeError(f"XML parse error while scanning block {block_path.name}: {e}")

        if group.tag != "ManeuverGroup":
            raise RuntimeError(
                f"Block {block_path.name} root is <{group.tag}>, expected <ManeuverGroup>"
            )

        for event in group.findall(".//Event"):
            event_type = normalize_event_type(event.get("name", ""))
            if event_type and event_type not in block_map:
                block_map[event_type] = block_path.name

        stem_event_type = f"{block_path.stem}_event"
        block_map.setdefault(stem_event_type, block_path.name)

    return block_map


def normalize_maneuvers(maneuvers):
    if maneuvers is None:
        return []
    if isinstance(maneuvers, dict):
        return [maneuvers]
    if isinstance(maneuvers, list):
        return maneuvers
    raise RuntimeError(
        "Maneuvers must be a mapping or a list of mappings, " f"got {type(maneuvers).__name__}"
    )


def maneuver_actor(maneuver):
    if not isinstance(maneuver, dict):
        return None
    actor = maneuver.get("actor")
    if actor is None:
        return None
    return str(actor).strip()


def uses_multi_tv_storyboard(core):
    logic = core.get("logic", {}) or {}
    maneuvers = normalize_maneuvers(logic.get("maneuvers"))
    return any(re.fullmatch(r"tv\d+", actor or "") for actor in map(maneuver_actor, maneuvers))


# =========================================================
# MANEUVER GROUP INSERTION
# =========================================================


def insert_maneuver_group(act, maneuver_group):
    start_trigger = act.find("StartTrigger")
    if start_trigger is None:
        raise RuntimeError("StartTrigger must exist in Act")

    maneuver_groups = act.findall("ManeuverGroup")

    if maneuver_groups:
        last_group = maneuver_groups[-1]
        index = list(act).index(last_group) + 1
    else:
        index = list(act).index(start_trigger)

    act.insert(index, maneuver_group)


# =========================================================
# MANEUVER GROUP RENDERING
# =========================================================


def render_maneuver_group(block_file, params, actor, core):
    path = maneuver_block_dir(core) / block_file

    if not os.path.exists(path):
        raise RuntimeError(f"Template file not found: {path}")

    render_params = dict(params)
    render_params["actor"] = actor
    default_speed_key = "tv_speed" if str(actor).startswith("tv") else "ev_speed"
    render_params.setdefault(
        "actor_speed",
        params.get(f"{actor}_speed", params.get(default_speed_key, "")),
    )

    text = load_text(path)

    for k, v in render_params.items():
        text = text.replace(f"${{{k}}}", escape(str(v)))

    try:
        group = ET.fromstring(text)
    except ET.ParseError as e:
        raise RuntimeError(f"XML parse error in block {block_file}: {e}")

    if group.tag != "ManeuverGroup":
        raise RuntimeError(f"Block {block_file} root is <{group.tag}>, expected <ManeuverGroup>")

    return group


# =========================================================
# STORYBOARD TEMPLATE RESOLUTION
# =========================================================


def resolve_storyboard_path(core):
    """
    Resolve storyboard template from core YAML only.

    Expected metadata:
      functional: ACC
      feature_domain: Longitudinal

    Supported placement:
      1. core["functional"], core["feature_domain"]
      2. core["logic"]["functional"], core["logic"]["feature_domain"]

    ACC storyboard templates are split by actor shape:
      - single-TV: maneuver actor is ev or tv
      - multi-TVs: maneuver actor is tv1, tv2, ...

    If metadata is missing, fall back to base_storyboard.xosc.
    """
    logic = core.get("logic", {}) or {}

    functional = core.get("functional") or logic.get("functional")
    feature_domain = core.get("feature_domain") or logic.get("feature_domain")

    if not functional and not feature_domain:
        return BASE / "templates" / "storyboard" / "base_storyboard.xosc"

    if not functional or not feature_domain:
        raise RuntimeError(
            "Storyboard template resolution requires both 'functional' and "
            "'feature_domain' in core YAML"
        )

    functional = str(functional).strip()
    feature_domain = str(feature_domain).strip()

    feature_dir = FEATURE_DOMAIN_DIRS.get(feature_domain)
    if feature_dir is None:
        valid_domains = ", ".join(FEATURE_DOMAIN_DIRS.keys())
        raise RuntimeError(
            f"Unknown feature_domain '{feature_domain}'. " f"Supported values: {valid_domains}"
        )

    storyboard_dir = BASE / "templates" / "storyboard" / feature_dir / functional

    if storyboard_dir.exists():
        storyboard_kind = "multi-TVs" if uses_multi_tv_storyboard(core) else "single-TV"
        storyboard_path = storyboard_dir / f"{functional}_{storyboard_kind}_storyboard.xosc"
    else:
        storyboard_path = (
            BASE / "templates" / "storyboard" / feature_dir / f"{functional}_storyboard.xosc"
        )

    if not os.path.exists(storyboard_path):
        raise RuntimeError(
            "Storyboard template not found for "
            f"functional='{functional}', feature_domain='{feature_domain}'. "
            f"Expected: {storyboard_path}"
        )

    return storyboard_path


# =========================================================
# CORE GENERATOR
# =========================================================


def generate_xosc(core):
    params = core.get("parameters", {})
    logic = core.get("logic", {})

    storyboard_path = resolve_storyboard_path(core)

    if not os.path.exists(storyboard_path):
        raise RuntimeError(f"Storyboard template not found: {storyboard_path}")

    tree = ET.parse(storyboard_path)
    root = tree.getroot()
    maneuver_map = discover_maneuver_blocks(core)

    act = root.find(".//Act")
    if act is None:
        raise RuntimeError("Act node not found in storyboard template")

    for m in normalize_maneuvers(logic.get("maneuvers")):
        if not isinstance(m, dict):
            raise RuntimeError(
                "Each maneuver must be a mapping with 'type' and 'actor', "
                f"got {type(m).__name__}: {m}"
            )

        m_type = m.get("type")
        actor = m.get("actor")

        if not m_type or not actor:
            raise RuntimeError(f"Maneuver missing 'type' or 'actor': {m}")

        if m_type not in maneuver_map:
            raise RuntimeError(f"Unknown maneuver type: {m_type}")

        block_file = maneuver_map[m_type]

        try:
            maneuver_group = render_maneuver_group(
                block_file=block_file, params=params, actor=actor, core=core
            )
            insert_maneuver_group(act, maneuver_group)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to insert maneuver {m_type} for {actor}: {e}")

    xml_str = ET.tostring(root, encoding="unicode")

    controller_module = resolve_controller_module(core)
    xml_str = xml_str.replace("${controller_module}", escape(controller_module))
    xml_str = xml_str.replace("${controller_config}", escape(resolve_controller_config(core)))
    xml_str = xml_str.replace("${controller_fmu}", escape(resolve_controller_fmu(core)))

    render_params = dict(CONTROLLER_DEFAULTS)
    render_params.update(params)

    for k, v in render_params.items():
        xml_str = xml_str.replace(f"${{{k}}}", escape(str(v)))

    env = map_environment(params)
    for k, v in env.items():
        xml_str = xml_str.replace(f"${{{k}}}", str(v))

    root = ET.fromstring(xml_str)
    tree._setroot(root)

    return tree


# =========================================================
# DIRECTORY MANAGEMENT
# =========================================================


def clean_dir(path):
    """Remove all files from directory."""
    if not os.path.exists(path):
        return

    for f in os.listdir(path):
        fp = os.path.join(path, f)
        if os.path.isfile(fp):
            try:
                os.remove(fp)
            except OSError as e:
                print(f"[WARN] Failed to remove {fp}: {e}")


def generate_core_dir(in_dir, clean=False, allowed_feature_domain_dir=None):
    if not os.path.isdir(in_dir):
        raise FileNotFoundError(f"Core scenario folder not found: {in_dir}")

    yaml_files = sorted(f for f in os.listdir(in_dir) if f.endswith(".yaml"))
    if not yaml_files:
        print(f"[WARN] No YAML files found in {in_dir}")
        return

    generated = 0
    skipped = 0
    output_dir = None

    for fname in yaml_files:
        yaml_path = Path(in_dir) / fname

        try:
            core = load_yaml(yaml_path)

            if not core:
                raise ValueError("YAML file is empty")

            validate_core_domain(core, yaml_path, allowed_feature_domain_dir)

            out_dir = output_dir_for_core(core)
            if output_dir is None:
                output_dir = out_dir
                os.makedirs(output_dir, exist_ok=True)
                if clean:
                    clean_dir(output_dir)

            tree = generate_xosc(core)
            out_path = out_dir / fname.replace(".yaml", ".xosc")

            write_xosc_file(tree, out_path)

            generated += 1
            print(f"[OK] {Path(in_dir).name}/{fname}")

        except Exception as e:
            skipped += 1
            print(f"[SKIP] {Path(in_dir).name}/{fname}: {e}")

    print(f"[DONE] {Path(in_dir).name}: generated={generated}, skipped={skipped}\n")


def generate_folder(selector, clean=False, allowed_feature_domain_dir=None):
    validate_selector_domain(selector, allowed_feature_domain_dir)
    core_parent = core_parent_from_selector(selector)
    if not core_parent.exists():
        raise FileNotFoundError(f"Core folder not found: {core_parent}")

    for in_dir in sorted(path for path in core_parent.iterdir() if path.is_dir()):
        generate_core_dir(
            in_dir,
            clean=clean,
            allowed_feature_domain_dir=allowed_feature_domain_dir,
        )


def generate_all(clean=False, allowed_feature_domain_dir=None):
    core_root = BASE / "core"
    if allowed_feature_domain_dir is not None:
        core_root = core_root / allowed_feature_domain_dir

    if not core_root.exists():
        print(f"[WARN] Core root not found: {core_root}")
        return

    for in_dir in sorted(
        path for path in core_root.rglob("*") if path.is_dir() and list(path.glob("*.yaml"))
    ):
        generate_core_dir(
            in_dir,
            clean=clean,
            allowed_feature_domain_dir=allowed_feature_domain_dir,
        )


def generate_range(selector_prefix, start, end, clean=False, allowed_feature_domain_dir=None):
    validate_selector_domain(selector_prefix, allowed_feature_domain_dir)
    for i in range(start, end + 1):
        selector = f"{selector_prefix}_{i:03d}"
        try:
            generate_core_dir(
                core_dir_from_selector(selector),
                clean=clean,
                allowed_feature_domain_dir=allowed_feature_domain_dir,
            )
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")


# =========================================================
# MAIN
# =========================================================


def main(allowed_feature_domain_dir=None):
    if allowed_feature_domain_dir is not None:
        allowed_feature_domain_dir = canonical_feature_domain_dir(allowed_feature_domain_dir)

    domain_help = ""
    if allowed_feature_domain_dir is not None:
        domain_name = FEATURE_DOMAIN_NAMES.get(allowed_feature_domain_dir, allowed_feature_domain_dir)
        domain_help = f" for {domain_name} scenarios"

    parser = argparse.ArgumentParser(
        description=f"Generate XOSC scenario files from YAML definitions{domain_help}"
    )
    parser.add_argument(
        "selectors",
        nargs="*",
        help=(
            "Scenario or folder selector, e.g. " "longitudinal/acc/acc_csc_001 or longitudinal/acc"
        ),
    )
    parser.add_argument("--all", action="store_true", help="Generate all scenarios")
    parser.add_argument("--from", dest="start", type=int)
    parser.add_argument("--to", dest="end", type=int)
    parser.add_argument(
        "--clean", action="store_true", help="Clean output directory before generation"
    )
    args = parser.parse_args()

    if args.all:
        generate_all(clean=args.clean, allowed_feature_domain_dir=allowed_feature_domain_dir)
        return

    if args.start is not None and args.end is not None:
        if len(args.selectors) != 1:
            parser.error("--from/--to requires exactly one selector prefix")
        generate_range(
            args.selectors[0],
            args.start,
            args.end,
            clean=args.clean,
            allowed_feature_domain_dir=allowed_feature_domain_dir,
        )
        return

    if args.start is not None or args.end is not None:
        parser.error("--from and --to must be used together")

    if not args.selectors:
        parser.print_help()
        return

    for selector in args.selectors:
        parts = split_selector(selector)
        try:
            validate_selector_domain(selector, allowed_feature_domain_dir)
            if len(parts) == 2:
                generate_folder(
                    selector,
                    clean=args.clean,
                    allowed_feature_domain_dir=allowed_feature_domain_dir,
                )
            else:
                generate_core_dir(
                    core_dir_from_selector(selector),
                    clean=args.clean,
                    allowed_feature_domain_dir=allowed_feature_domain_dir,
                )
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")
        except ValueError as e:
            print(f"[SKIP] {e}")


if __name__ == "__main__":
    main()
