import os
import yaml
import argparse
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from xml.dom import minidom

# =========================================================
# PATH
# =========================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "scenarios"))

FEATURE_DOMAIN_DIRS = {
    "Longitudinal": "longitudinal_feature",
    "Lateral": "lateral_feature",
    "Parking": "parking_feature",
    "Brake": "brake_feature",
}

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

# =========================================================
# XML FORMATTING
# =========================================================

def prettify_xml(elem, indent="  "):
    rough_string = ET.tostring(elem, encoding="unicode")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent=indent)

    lines = [line for line in pretty_xml.split('\n') if line.strip()]

    if lines and lines[0].startswith('<?xml'):
        lines = lines[1:]

    return '\n'.join(lines)

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
        env.update({
            "time_of_day": "2026-01-01T12:00:00",
            "sun_intensity": "1.0",
            "sun_elevation": "70",
        })
    else:
        env.update({
            "time_of_day": "2026-01-01T00:00:00",
            "sun_intensity": "0.05",
            "sun_elevation": "-10",
        })

    if weather == "clear":
        env.update({
            "cloud_state": "free",
            "fog_range": "100000",
            "precip_type": "dry",
            "precip_intensity": "0",
            "friction": "1.0",
        })
    elif weather == "rain":
        env.update({
            "cloud_state": "overcast",
            "fog_range": "30000",
            "precip_type": "rain",
            "precip_intensity": "0.7",
            "friction": "0.7",
        })
    elif weather == "fog":
        env.update({
            "cloud_state": "cloudy",
            "fog_range": "80",
            "precip_type": "dry",
            "precip_intensity": "0",
            "friction": "0.9",
        })

    return env

# =========================================================
# MANEUVER MAP
# =========================================================

MANEUVER_MAP = {
    "appear_event": "appear.xosc",
    "follow_slowdown": "follow_slowdown.xosc",
    "follow_stable": "follow_stable.xosc",
    "follow_resume": "follow_resume.xosc",
    "cruise_event": "cruise_control.xosc",
    "stop_event": "stop.xosc",
    "resume_event": "resume.xosc",
    "cutin_event": "cutin.xosc",
    "cutout_event": "cutout.xosc",
    "ego_cutout_event": "ego_cutout.xosc",
    "ego_cutout_signal_event": "ego_cutout_signal.xosc",
}

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

def render_maneuver_group(block_file, params, actor):
    path = os.path.join(BASE, "templates", "maneuver_blocks", block_file)

    if not os.path.exists(path):
        raise RuntimeError(f"Template file not found: {path}")

    text = load_text(path)
    text = text.replace("${actor}", escape(str(actor)))

    for k, v in params.items():
        text = text.replace(f"${{{k}}}", escape(str(v)))

    try:
        group = ET.fromstring(text)
    except ET.ParseError as e:
        raise RuntimeError(f"XML parse error in block {block_file}: {e}")

    if group.tag != "ManeuverGroup":
        raise RuntimeError(
            f"Block {block_file} root is <{group.tag}>, expected <ManeuverGroup>"
        )

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

    If metadata is missing, fall back to base_storyboard.xosc.
    """
    logic = core.get("logic", {}) or {}

    functional = core.get("functional") or logic.get("functional")
    feature_domain = core.get("feature_domain") or logic.get("feature_domain")

    if not functional and not feature_domain:
        return os.path.join(BASE, "templates", "storyboard", "base_storyboard.xosc")

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
            f"Unknown feature_domain '{feature_domain}'. "
            f"Supported values: {valid_domains}"
        )

    storyboard_path = os.path.join(
        BASE,
        "templates",
        "storyboard",
        feature_dir,
        f"{functional}_storyboard.xosc",
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

    act = root.find(".//Act")
    if act is None:
        raise RuntimeError("Act node not found in storyboard template")

    for m in logic.get("maneuvers", []):
        m_type = m.get("type")
        actor = m.get("actor")

        if not m_type or not actor:
            raise RuntimeError(f"Maneuver missing 'type' or 'actor': {m}")

        if m_type not in MANEUVER_MAP:
            raise RuntimeError(f"Unknown maneuver type: {m_type}")

        block_file = MANEUVER_MAP[m_type]

        try:
            maneuver_group = render_maneuver_group(
                block_file=block_file,
                params=params,
                actor=actor
            )
            insert_maneuver_group(act, maneuver_group)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to insert maneuver {m_type} for {actor}: {e}")

    xml_str = ET.tostring(root, encoding="unicode")

    for k, v in params.items():
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

# =========================================================
# MAIN
# =========================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate XOSC scenario files from YAML definitions"
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        help="Scenario IDs to generate (default: all)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate all scenarios"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean output directory before generation"
    )
    args = parser.parse_args()

    core_root = os.path.join(BASE, "core")

    if not os.path.exists(core_root):
        print(f"[ERROR] Core directory not found: {core_root}")
        return

    scenario_ids = args.scenarios or os.listdir(core_root)

    for sid in scenario_ids:
        in_dir = os.path.join(core_root, sid)
        out_dir = os.path.join(BASE, "generated", "carla", sid)

        if not os.path.isdir(in_dir):
            continue

        os.makedirs(out_dir, exist_ok=True)

        if args.clean:
            clean_dir(out_dir)

        generated = 0
        skipped = 0

        yaml_files = [f for f in os.listdir(in_dir) if f.endswith(".yaml")]

        if not yaml_files:
            print(f"[WARN] No YAML files found in {sid}")
            continue

        for fname in yaml_files:
            yaml_path = os.path.join(in_dir, fname)

            try:
                core = load_yaml(yaml_path)

                if not core:
                    raise ValueError("YAML file is empty")

                tree = generate_xosc(core)
                out_path = os.path.join(out_dir, fname.replace(".yaml", ".xosc"))

                write_xosc_file(tree, out_path)

                generated += 1
                print(f"[OK] {sid}/{fname}")

            except Exception as e:
                skipped += 1
                print(f"[SKIP] {sid}/{fname}: {e}")

        print(f"[DONE] {sid}: generated={generated}, skipped={skipped}\n")

if __name__ == "__main__":
    main()