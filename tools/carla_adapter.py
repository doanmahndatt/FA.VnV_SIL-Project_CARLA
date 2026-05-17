import yaml
import os
import xml.etree.ElementTree as ET

BASE = "../scenarios"


# ================= BASIC IO =================

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_text(path):
    with open(path, "r") as f:
        return f.read()


# ================= XML FORMAT (PRETTY PRINT) =================

def indent(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = i


# ================= CORE GENERATOR =================

def generate_xosc(core):

    params = core["parameters"]

    ev_speed = params.get("ev_speed", 10)
    tv_speed = params.get("tv_speed", 5)
    cutin_time = params.get("cutin_time", 5)

    # ===== LOAD STORYBOARD TEMPLATE =====
    tree = ET.parse(f"{BASE}/templates/storyboard/base_storyboard.xosc")
    root = tree.getroot()

    # ===== FIND ACT NODE =====
    act = root.find(".//Act")
    if act is None:
        raise Exception("Act node not found in storyboard")

    # ===== LOAD CUTIN BLOCK =====
    cutin_text = load_text(f"{BASE}/templates/maneuver_blocks/cutin.xosc")

    # ===== PARAMETER REPLACE =====
    cutin_text = cutin_text.replace("${cutin_time}", str(cutin_time))

    # ⚠️ lane mapping: right → ego
    cutin_text = cutin_text.replace("${lane_delta}", "-1")

    # ===== CONVERT STRING → XML NODE =====
    maneuver_xml = ET.fromstring(cutin_text)

    # ===== INSERT ĐÚNG VỊ TRÍ =====
    start_trigger = act.find("StartTrigger")

    if start_trigger is not None:
        index = list(act).index(start_trigger)
        act.insert(index, maneuver_xml)
    else:
        # fallback nếu không có StartTrigger
        act.append(maneuver_xml)

    # ===== SET SPEED (INIT SECTION) =====
    speed_tags = root.findall(".//AbsoluteTargetSpeed")

    if len(speed_tags) >= 2:
        speed_tags[0].set("value", str(ev_speed))
        speed_tags[1].set("value", str(tv_speed))
    else:
        print("[WARN] Cannot find enough speed tags")

    # ===== FORMAT XML =====
    indent(root)

    return tree


# ================= RUN =================

def run():

    scenario_id = "acc_csc_003"

    input_dir = f"{BASE}/core/{scenario_id}"
    output_dir = f"{BASE}/generated/carla"

    os.makedirs(output_dir, exist_ok=True)

    for file in os.listdir(input_dir):

        if not file.endswith(".yaml"):
            continue

        core_path = f"{input_dir}/{file}"
        core = load_yaml(core_path)

        tree = generate_xosc(core)

        out_file = f"{output_dir}/{file.replace('.yaml', '.xosc')}"
        tree.write(out_file, encoding="utf-8", xml_declaration=True)

        print(f"[OK] Generated: {out_file}")


if __name__ == "__main__":
    run()