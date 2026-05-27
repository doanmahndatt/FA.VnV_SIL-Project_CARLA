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
SCENARIOS_DIR = PROJECT_PATHS.repo_root / "scenarios"
DEFAULT_SCENARIO_SET = "general_scenarios"
BASE = SCENARIOS_DIR / DEFAULT_SCENARIO_SET

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


def resolve_scenario_set(parts):
    if parts and parts[0].lower().endswith("_scenarios"):
        scenario_root = SCENARIOS_DIR / parts[0].lower()
        if not scenario_root.exists():
            raise FileNotFoundError(f"Scenario set not found: {scenario_root}")
        return scenario_root, parts[1:]
    return BASE, parts


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

    _, parts = resolve_scenario_set(split_selector(selector))
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
    scenario_root, parts = resolve_scenario_set(split_selector(selector))
    core_root = scenario_root / "core"

    if len(parts) == 1:
        matches = sorted(path for path in core_root.rglob(parts[0]) if path.is_dir())
        if len(matches) == 1:
            return scenario_root, matches[0]
        if not matches:
            raise FileNotFoundError(f"Core scenario folder not found: {selector}")
        raise RuntimeError(f"Ambiguous scenario selector '{selector}': {matches}")

    if len(parts) == 3:
        return scenario_root, (
            core_root
            / normalize_selector_part(parts[0])
            / normalize_functional_part(parts[1])
            / parts[2]
        )

    raise ValueError(
        "Selector must be '[<scenario_set>/]<scenario_id>' or "
        "'[<scenario_set>/]<feature_domain>/<functional>/<scenario_id>'"
    )


def core_parent_from_selector(selector):
    scenario_root, parts = resolve_scenario_set(split_selector(selector))
    if len(parts) != 2:
        raise ValueError(
            "Folder selector must be '[<scenario_set>/]<feature_domain>/<functional>'"
        )
    return scenario_root, (
        scenario_root / "core" / normalize_selector_part(parts[0]) / normalize_functional_part(parts[1])
    )


def output_dir_for_core(core, scenario_root=BASE):
    case_id = core.get("scenario_id")
    if not case_id:
        raise RuntimeError("Core YAML must define 'scenario_id'")

    feature_domain, functional = metadata_from_core(core)
    return (
        scenario_root
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
    "scenario_duration": "45",
    "trigger_lane_departure_time_1": "5",
    "trigger_lane_departure_time_2": "12",
    "trigger_lane_departure_time_3": "19",
    "ev_spawn_offset": "0.0",
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


def maneuver_block_dir(core, scenario_root=BASE):
    feature_domain, functional = metadata_from_core(core)
    return (
        scenario_root
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


def discover_maneuver_blocks(core, scenario_root=BASE):
    block_dir = maneuver_block_dir(core, scenario_root)
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


def render_maneuver_group(block_file, params, actor, core, scenario_root=BASE):
    path = maneuver_block_dir(core, scenario_root) / block_file

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


def resolve_storyboard_path(core, scenario_root=BASE):
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
        return scenario_root / "templates" / "storyboard" / "base_storyboard.xosc"

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

    storyboard_dir = scenario_root / "templates" / "storyboard" / feature_dir / functional

    if storyboard_dir.exists():
        # LKA uses road_type/geometry-based storyboard split.
        if functional == "LKA":
            pre_condition = (logic.get("pre_condition", {}) or {}) if isinstance(logic, dict) else {}
            road_type = str(pre_condition.get("road_type", "")).strip().lower()
            curve_side = str(pre_condition.get("curve_side", "")).strip().lower()

            if road_type == "straight":
                storyboard_name = "LKA_straightRoad_storyboard.xosc"
            elif road_type == "curve":
                storyboard_name = "LKA_curveRoad_storyboard.xosc"
            elif road_type == "mixed":
                transition = str(pre_condition.get("transition", "")).strip().lower()
                if transition == "curve_to_straight":
                    storyboard_name = "LKA_mixedCurveToStraight_storyboard.xosc"
                elif transition == "straight_to_curve":
                    storyboard_name = "LKA_mixedStraightToCurve_storyboard.xosc"
                elif curve_side == "right":
                    storyboard_name = "LKA_mixedRightCurve_storyboard.xosc"
                elif curve_side == "left":
                    storyboard_name = "LKA_mixedLeftCurve_storyboard.xosc"
                else:
                    storyboard_name = "LKA_mixedRoad_storyboard.xosc"
            else:
                storyboard_name = None

            if not storyboard_name:
                raise RuntimeError(
                    "LKA storyboard resolution requires pre_condition.road_type "
                    "with one of: straight, curve, mixed"
                )
            storyboard_path = storyboard_dir / storyboard_name
        else:
            storyboard_kind = "multi-TVs" if uses_multi_tv_storyboard(core) else "single-TV"
            storyboard_path = storyboard_dir / f"{functional}_{storyboard_kind}_storyboard.xosc"
    else:
        feature_storyboard_dir = scenario_root / "templates" / "storyboard" / feature_dir
        single_tv_path = feature_storyboard_dir / f"{functional}_single-TV_storyboard.xosc"
        storyboard_path = (
            single_tv_path
            if single_tv_path.exists()
            else feature_storyboard_dir / f"{functional}_storyboard.xosc"
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


def parameter_declaration_type(core):
    logic = core.get("logic", {}) or {}
    declarations = logic.get("parametersDeclaration")
    if not declarations:
        return None
    if isinstance(declarations, dict):
        declarations = [declarations]
    if not isinstance(declarations, list) or not declarations:
        raise RuntimeError("parametersDeclaration must be a mapping or non-empty list")
    declaration_type = declarations[0].get("type") if isinstance(declarations[0], dict) else None
    if not declaration_type:
        raise RuntimeError("parametersDeclaration entry must define 'type'")
    return str(declaration_type).strip()


def parameter_declaration_template_path(core, scenario_root=BASE):
    declaration_type = parameter_declaration_type(core)
    if declaration_type is None:
        return None
    feature_domain, functional = metadata_from_core(core)
    return (
        scenario_root
        / "templates"
        / "ParameterDeclarations"
        / to_feature_domain_dir(feature_domain)
        / to_functional_dir(functional)
        / f"{declaration_type}_parameters.xosc"
    )


def numeric_fixed_declarations(core, scenario_root=BASE):
    path = parameter_declaration_template_path(core, scenario_root)
    if path is None:
        return {}
    if not path.exists():
        raise RuntimeError(f"Parameter declaration template not found: {path}")
    try:
        declarations = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise RuntimeError(f"XML parse error in parameter declarations {path.name}: {e}")

    fixed = {}
    for declaration in declarations.findall("ParameterDeclaration"):
        name = declaration.attrib.get("name")
        value = declaration.attrib.get("value")
        try:
            fixed[name] = float(value)
        except (TypeError, ValueError):
            continue
    return fixed


def cpna_derived_parameters(params, fixed):
    required = (
        "ev_length",
        "ev_width",
        "ev_initS",
        "ev_BBcenter_x",
        "ev_initTTC",
        "VRU_finalSpeed_kph",
        "VRU_initLatDist",
        "VRU_trajectoryOrientation",
    )
    missing = [name for name in required if name not in fixed]
    if missing:
        raise RuntimeError(
            "CPNA fixed declarations must contain numeric values for: " + ", ".join(missing)
        )

    reserved_inputs = sorted(name for name in fixed if name in params)
    if reserved_inputs:
        raise RuntimeError(
            "CPNA fixed parameter(s) must be edited in CPNA_parameters.xosc, not core YAML: "
            + ", ".join(reserved_inputs)
        )

    ev_speed_kph = float(params["ev_speed_kph"])
    ev_speed_mps = ev_speed_kph / 3.6
    vru_speed_mps = fixed["VRU_finalSpeed_kph"] / 3.6
    if ev_speed_mps <= 0.0 or vru_speed_mps <= 0.0:
        raise RuntimeError("CPNA EV and VRU speeds must be positive for impact timing")
    overlap = float(params["overlap"])
    if not 0.0 <= overlap <= 100.0:
        raise RuntimeError(f"CPNA overlap must be between 0 and 100, got {overlap}")

    # CPNA is always a pedestrian crossing from the nearside. Overlap changes
    # the impact point, never the approach direction. The configured
    # orientation identifies the nearside sign in this CARLA placement.
    near_side_sign = 1.0 if fixed["VRU_trajectoryOrientation"] >= 0.0 else -1.0
    ev_impact_offset = near_side_sign * (
        fixed["ev_width"] / 2.0 - fixed["ev_width"] * (overlap / 100.0)
    )
    vru_collision_offset = near_side_sign * (0.6 / 2.0 - 0.36)
    vru_impact_offset = ev_impact_offset - vru_collision_offset
    vru_initial_offset = near_side_sign * fixed["VRU_initLatDist"]
    vru_final_offset = -vru_initial_offset
    if not min(vru_initial_offset, vru_final_offset) <= vru_impact_offset <= max(
        vru_initial_offset, vru_final_offset
    ):
        raise RuntimeError("CPNA impact point is outside the configured VRU crossing corridor")
    vru_time_to_impact = abs(vru_impact_offset - vru_initial_offset) / vru_speed_mps
    ev_front_bumper = fixed["ev_BBcenter_x"] + fixed["ev_length"] / 2.0
    # CARLA places the vehicle actor at its reference origin, while the NCAP
    # impact occurs at the EV front bumper. Advance the VRU timing so the
    # front bumper reaches the configured lateral impact point, not the actor
    # origin.
    ev_impact_time = fixed["ev_initTTC"] - ev_front_bumper / ev_speed_mps
    crossing_start = max(0.0, ev_impact_time - vru_time_to_impact)

    return {
        "ev_speed": f"{ev_speed_mps:.6f}",
        "ev_speed_mps": f"{ev_speed_mps:.6f}",
        "vru_speed_mps": f"{vru_speed_mps:.6f}",
        "vru_init_s": f"{fixed['ev_initS'] + fixed['ev_initTTC'] * ev_speed_mps:.6f}",
        "vru_initial_offset": f"{vru_initial_offset:.6f}",
        "vru_final_offset": f"{vru_final_offset:.6f}",
        "vru_crossing_duration": f"{(2.0 * fixed['VRU_initLatDist']) / vru_speed_mps:.6f}",
        "vru_crossing_start_time": f"{crossing_start:.6f}",
        "vru_crossing_end_time": (
            f"{crossing_start + (2.0 * fixed['VRU_initLatDist']) / vru_speed_mps:.6f}"
        ),
        "ev_front_bumper": f"{ev_front_bumper:.6f}",
        "ev_impact_offset": f"{ev_impact_offset:.6f}",
        "vru_collision_offset": f"{vru_collision_offset:.6f}",
        "environment_catalog_entry": (
            f"Env_{str(params.get('light', 'day')).title()}_"
            f"{str(params.get('weather', 'clear')).title()}"
        ),
    }


def render_parameters(core, params, scenario_root=BASE):
    rendered = dict(CONTROLLER_DEFAULTS)
    rendered.update(params)
    if parameter_declaration_type(core) == "CPNA":
        rendered.update(cpna_derived_parameters(params, numeric_fixed_declarations(core, scenario_root)))
    return rendered


def render_parameter_declarations(core, render_params, scenario_root=BASE):
    path = parameter_declaration_template_path(core, scenario_root)
    if path is None:
        return None
    if not path.exists():
        raise RuntimeError(f"Parameter declaration template not found: {path}")
    text = load_text(path)
    for key, value in render_params.items():
        text = text.replace(f"${{{key}}}", escape(str(value)))
    try:
        declarations = ET.fromstring(text)
    except ET.ParseError as e:
        raise RuntimeError(f"XML parse error in parameter declarations {path.name}: {e}")
    if declarations.tag != "ParameterDeclarations":
        raise RuntimeError(
            f"Parameter declaration template {path.name} root is "
            f"<{declarations.tag}>, expected <ParameterDeclarations>"
        )
    return declarations


def insert_parameter_declarations(root, declarations):
    if declarations is None:
        return
    current = root.find("ParameterDeclarations")
    if current is None:
        raise RuntimeError("Storyboard template must contain <ParameterDeclarations>")
    index = list(root).index(current)
    root.remove(current)
    root.insert(index, declarations)


def generate_xosc(core, scenario_root=BASE):
    params = core.get("parameters", {})
    logic = core.get("logic", {})
    render_params = render_parameters(core, params, scenario_root)

    storyboard_path = resolve_storyboard_path(core, scenario_root)

    if not os.path.exists(storyboard_path):
        raise RuntimeError(f"Storyboard template not found: {storyboard_path}")

    tree = ET.parse(storyboard_path)
    root = tree.getroot()
    maneuver_map = discover_maneuver_blocks(core, scenario_root)
    insert_parameter_declarations(
        root, render_parameter_declarations(core, render_params, scenario_root)
    )

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
                block_file=block_file,
                params=params,
                actor=actor,
                core=core,
                scenario_root=scenario_root,
            )
            insert_maneuver_group(act, maneuver_group)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to insert maneuver {m_type} for {actor}: {e}")

    xml_str = ET.tostring(root, encoding="unicode")

    controller_module = resolve_controller_module(core)
    xml_str = xml_str.replace("${controller_module}", escape(controller_module))
    xml_str = xml_str.replace("${controller_config}", escape(resolve_controller_config(core)))
    xml_str = xml_str.replace("${controller_fmu}", escape(resolve_controller_fmu(core)))

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


def generate_core_dir(in_dir, clean=False, allowed_feature_domain_dir=None, scenario_root=BASE):
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

            out_dir = output_dir_for_core(core, scenario_root)
            if output_dir is None:
                output_dir = out_dir
                os.makedirs(output_dir, exist_ok=True)
                if clean:
                    clean_dir(output_dir)

            tree = generate_xosc(core, scenario_root)
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
    scenario_root, core_parent = core_parent_from_selector(selector)
    if not core_parent.exists():
        raise FileNotFoundError(f"Core folder not found: {core_parent}")

    for in_dir in sorted(path for path in core_parent.iterdir() if path.is_dir()):
        generate_core_dir(
            in_dir,
            clean=clean,
            allowed_feature_domain_dir=allowed_feature_domain_dir,
            scenario_root=scenario_root,
        )


def generate_all(clean=False, allowed_feature_domain_dir=None, scenario_root=BASE):
    core_root = scenario_root / "core"
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
            scenario_root=scenario_root,
        )


def generate_range(selector_prefix, start, end, clean=False, allowed_feature_domain_dir=None):
    validate_selector_domain(selector_prefix, allowed_feature_domain_dir)
    for i in range(start, end + 1):
        selector = f"{selector_prefix}_{i:03d}"
        try:
            scenario_root, core_dir = core_dir_from_selector(selector)
            generate_core_dir(
                core_dir,
                clean=clean,
                allowed_feature_domain_dir=allowed_feature_domain_dir,
                scenario_root=scenario_root,
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
        if len(args.selectors) > 1:
            parser.error("--all accepts at most one scenario set, e.g. ncap_scenarios --all")
        if args.selectors:
            scenario_root, remaining = resolve_scenario_set(split_selector(args.selectors[0]))
            if remaining:
                parser.error("--all selector must be a scenario set, e.g. ncap_scenarios")
        else:
            scenario_root = BASE
        generate_all(
            clean=args.clean,
            allowed_feature_domain_dir=allowed_feature_domain_dir,
            scenario_root=scenario_root,
        )
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
        _, parts = resolve_scenario_set(split_selector(selector))
        try:
            validate_selector_domain(selector, allowed_feature_domain_dir)
            if len(parts) == 2:
                generate_folder(
                    selector,
                    clean=args.clean,
                    allowed_feature_domain_dir=allowed_feature_domain_dir,
                )
            else:
                scenario_root, core_dir = core_dir_from_selector(selector)
                generate_core_dir(
                    core_dir,
                    clean=args.clean,
                    allowed_feature_domain_dir=allowed_feature_domain_dir,
                    scenario_root=scenario_root,
                )
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")
        except ValueError as e:
            print(f"[SKIP] {e}")


if __name__ == "__main__":
    main()
