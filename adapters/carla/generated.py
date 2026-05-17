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
    """
    Return a pretty-printed XML string for the Element.
    
    Args:
        elem: ElementTree Element to format
        indent: Indentation string (default: 2 spaces)
        
    Returns:
        Formatted XML string
    """
    rough_string = ET.tostring(elem, encoding="unicode")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent=indent)
    
    # Remove extra blank lines and XML declaration (will be added separately)
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    
    # Remove the XML declaration from minidom (we'll add it manually)
    if lines and lines[0].startswith('<?xml'):
        lines = lines[1:]
    
    return '\n'.join(lines)

def write_xosc_file(tree, output_path):
    """
    Write XOSC file with proper XML declaration and formatting.
    
    Args:
        tree: ElementTree object
        output_path: Path to output file
    """
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

    # --- LIGHT ---
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

    # --- WEATHER ---
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
# MANEUVER GROUP INSERTION (FIXED)
# =========================================================

def insert_maneuver_group(act, maneuver_group):
    
    """
    Insert ManeuverGroup before StartTrigger, after all existing ManeuverGroups.
    
    This ensures proper XML structure:
    <Act>
      <ManeuverGroup>...</ManeuverGroup>
      <ManeuverGroup>...</ManeuverGroup>
      <StartTrigger>...</StartTrigger>
    </Act>
    """
    start_trigger = act.find("StartTrigger")
    if start_trigger is None:
        raise RuntimeError("StartTrigger must exist in Act")

    # Find all existing ManeuverGroups
    maneuver_groups = act.findall("ManeuverGroup")
    
    if maneuver_groups:
        # Insert after the last ManeuverGroup
        last_group = maneuver_groups[-1]
        index = list(act).index(last_group) + 1
    else:
        # No ManeuverGroups yet, insert before StartTrigger
        index = list(act).index(start_trigger)

    act.insert(index, maneuver_group)

# =========================================================
# MANEUVER GROUP RENDERING
# =========================================================

def render_maneuver_group(block_file, params, actor):
    """
    Render a ManeuverGroup from template file with parameter substitution.
    
    Args:
        block_file: Template filename (e.g., "appear.xosc")
        params: Dictionary of parameters to substitute
        actor: Actor name for the maneuver
        
    Returns:
        ElementTree Element representing the ManeuverGroup
        
    Raises:
        RuntimeError: If template not found or XML parsing fails
    """
    path = os.path.join(BASE, "templates", "maneuver_blocks", block_file)
    
    if not os.path.exists(path):
        raise RuntimeError(f"Template file not found: {path}")
    
    text = load_text(path)

    # Replace actor placeholder
    text = text.replace("${actor}", escape(str(actor)))

    # Replace parameter placeholders
    for k, v in params.items():
        text = text.replace(f"${{{k}}}", escape(str(v)))

    # Parse XML
    try:
        group = ET.fromstring(text)
    except ET.ParseError as e:
        raise RuntimeError(f"XML parse error in block {block_file}: {e}")

    # Validate root element
    if group.tag != "ManeuverGroup":
        raise RuntimeError(
            f"Block {block_file} root is <{group.tag}>, expected <ManeuverGroup>"
        )

    return group

# =========================================================
# CORE GENERATOR
# =========================================================

def generate_xosc(core):
    """
    Generate XOSC file from core scenario definition.
    
    Args:
        core: Dictionary containing 'parameters' and 'logic' keys
        
    Returns:
        ElementTree object with generated scenario
        
    Raises:
        RuntimeError: If storyboard template not found or maneuver type unknown
    """
    params = core.get("parameters", {})
    logic = core.get("logic", {})

    # Load base storyboard template
    storyboard_path = os.path.join(
        BASE, "templates", "storyboard", "base_storyboard.xosc"
    )
    
    if not os.path.exists(storyboard_path):
        raise RuntimeError(f"Storyboard template not found: {storyboard_path}")

    tree = ET.parse(storyboard_path)
    root = tree.getroot()

    # Find Act element
    act = root.find(".//Act")
    if act is None:
        raise RuntimeError("Act node not found in storyboard template")

    # --- INSERT MANEUVERS IN ORDER ---
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

    # --- PARAMETER & ENVIRONMENT SUBSTITUTION ---
    # Convert to string for global parameter replacement
    xml_str = ET.tostring(root, encoding="unicode")
    
    # Replace scenario parameters (e.g., ${ev_speed}, ${tv_speed})
    for k, v in params.items():
        xml_str = xml_str.replace(f"${{{k}}}", escape(str(v)))
    
    # Replace environment variables (e.g., ${time_of_day}, ${sun_intensity})
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
    """Main entry point for scenario generation."""
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

    # Determine which scenarios to process
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

        # Process all YAML files in scenario directory
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
                
                # Use custom write function for proper formatting
                write_xosc_file(tree, out_path)

                generated += 1
                print(f"[OK] {sid}/{fname}")
                
            except Exception as e:
                skipped += 1
                print(f"[SKIP] {sid}/{fname}: {e}")

        print(f"[DONE] {sid}: generated={generated}, skipped={skipped}\n")

if __name__ == "__main__":
    main()