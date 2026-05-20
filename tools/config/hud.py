import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import carla
import pygame


BASE_DIR = Path(__file__).resolve().parent
MAPS_DIR = BASE_DIR / "maps_CARLA"
OPENDRIVE_DIR = MAPS_DIR / "OpenDrive"

WINDOW_WIDTH = 550
WINDOW_HEIGHT = 240
FPS_DELAY_SECONDS = 0.05


pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("ADAS HUD")
font = pygame.font.SysFont("consolas", 20)

client = carla.Client("localhost", 2000)
client.set_timeout(10)


_map_cache = {}


def find_vehicle(world, role):
    for vehicle in world.get_actors().filter("vehicle.*"):
        if vehicle.attributes.get("role_name") == role:
            return vehicle
    return None


def get_vehicle_role(vehicle):
    return vehicle.attributes.get("role_name", "")


def get_speed(vehicle):
    velocity = vehicle.get_velocity()
    return 3.6 * math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)


def signed_longitudinal_distance(ev, tv):
    """Return signed bumper-to-bumper distance from EV to TV along EV forward axis."""
    ev_transform = ev.get_transform()
    forward = ev_transform.get_forward_vector()
    relative_location = tv.get_location() - ev.get_location()

    center_distance = (
        relative_location.x * forward.x
        + relative_location.y * forward.y
        + relative_location.z * forward.z
    )
    bumper_offset = ev.bounding_box.extent.x + tv.bounding_box.extent.x

    if center_distance > 0:
        return center_distance - bumper_offset
    if center_distance < 0:
        return center_distance + bumper_offset
    return 0.0


def get_world_map_name(world_map):
    return Path(world_map.name).name


def load_opendrive_lane_index(map_name):
    """Load road/lane ids from the fixed CARLA OpenDRIVE resources."""
    if map_name in _map_cache:
        return _map_cache[map_name]

    xodr_path = OPENDRIVE_DIR / f"{map_name}.xodr"
    if not xodr_path.exists() and map_name.endswith("_Opt"):
        xodr_path = OPENDRIVE_DIR / f"{map_name[:-4]}.xodr"

    lane_index = {}
    if xodr_path.exists():
        try:
            root = ET.parse(xodr_path).getroot()
            for road in root.findall("road"):
                road_id = int(road.attrib["id"])
                lane_ids = set()
                lanes_node = road.find("lanes")
                if lanes_node is not None:
                    for lane in lanes_node.findall(".//lane"):
                        lane_id = int(lane.attrib["id"])
                        if lane_id != 0:
                            lane_ids.add(lane_id)
                lane_index[road_id] = lane_ids
        except (ET.ParseError, OSError, KeyError, ValueError):
            lane_index = {}

    _map_cache[map_name] = lane_index
    return lane_index


def get_lane_position(world_map, vehicle):
    """Return map, road and lane id for a vehicle location."""
    map_name = get_world_map_name(world_map)
    waypoint = world_map.get_waypoint(
        vehicle.get_location(),
        project_to_road=True,
        lane_type=carla.LaneType.Driving,
    )

    if waypoint is None:
        return map_name, None, None, False

    lane_index = load_opendrive_lane_index(map_name)
    road_id = waypoint.road_id
    lane_id = waypoint.lane_id
    is_configured = bool(lane_index) and lane_id in lane_index.get(road_id, set())

    return map_name, road_id, lane_id, is_configured


def find_target_vehicle(world, world_map, ev, target_role_prefix="tv"):
    candidates = []
    ev_lane_position = get_lane_position(world_map, ev)
    _, ev_road_id, ev_lane_id, _ = ev_lane_position

    for vehicle in world.get_actors().filter("vehicle.*"):
        if vehicle.id == ev.id:
            continue

        role = get_vehicle_role(vehicle)
        if not role.startswith(target_role_prefix):
            continue

        vehicle_lane_position = get_lane_position(world_map, vehicle)
        _, vehicle_road_id, vehicle_lane_id, _ = vehicle_lane_position
        distance = signed_longitudinal_distance(ev, vehicle)

        same_lane = (
            ev_road_id is not None
            and ev_lane_id is not None
            and vehicle_road_id == ev_road_id
            and vehicle_lane_id == ev_lane_id
        )
        ahead = distance > 0

        if same_lane and ahead:
            priority = 0
        elif ahead:
            priority = 1
        elif same_lane:
            priority = 2
        else:
            priority = 3

        candidates.append((priority, abs(distance), vehicle))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1], get_vehicle_role(item[2])))
    return candidates[0][2]


def format_lane_position(label, lane_position):
    map_name, road_id, lane_id, is_configured = lane_position
    if road_id is None or lane_id is None:
        return f"{label} lane_position : {map_name} road -- lane --"

    suffix = "" if is_configured else " *"
    return f"{label} lane_position : {map_name} road {road_id:>3} lane {lane_id:>3}{suffix}"


start_time = None


while True:
    pygame.event.pump()

    world = client.get_world()
    world_map = world.get_map()
    ev = find_vehicle(world, "ev")
    tv = find_target_vehicle(world, world_map, ev) if ev else None

    if ev and tv:
        snapshot_time = world.get_snapshot().timestamp.elapsed_seconds
        if start_time is None:
            start_time = snapshot_time

        sim_time = snapshot_time - start_time
        ev_speed = get_speed(ev)
        tv_speed = get_speed(tv)
        distance = signed_longitudinal_distance(ev, tv)
        ev_lane_position = get_lane_position(world_map, ev)
        tv_lane_position = get_lane_position(world_map, tv)
        tv_label = get_vehicle_role(tv).upper() or "TV"

        rel_speed = (ev_speed - tv_speed) / 3.6
        if distance > 0 and rel_speed > 0.1:
            ttc = distance / rel_speed
        else:
            ttc = 999
    elif ev:
        snapshot_time = world.get_snapshot().timestamp.elapsed_seconds
        if start_time is None:
            start_time = snapshot_time

        sim_time = snapshot_time - start_time
        ev_speed = get_speed(ev)
        tv_speed = 0
        distance = 0
        ttc = 0
        ev_lane_position = get_lane_position(world_map, ev)
        map_name = get_world_map_name(world_map)
        tv_lane_position = (map_name, None, None, False)
        tv_label = "TV"
    else:
        start_time = None
        map_name = get_world_map_name(world_map)
        sim_time = 0
        ev_speed = 0
        tv_speed = 0
        distance = 0
        ttc = 0
        ev_lane_position = (map_name, None, None, False)
        tv_lane_position = (map_name, None, None, False)
        tv_label = "TV"

    screen.fill((25, 25, 25))

    lines = [
        f"time : {sim_time:6.2f} s",
        f"EV   : {ev_speed:6.2f} km/h",
        f"{tv_label:<4}: {tv_speed:6.2f} km/h",
        f"distance : {distance:6.2f} m",
        f"TTC  : {ttc:6.2f} s",
        format_lane_position("EV", ev_lane_position),
        format_lane_position(tv_label, tv_lane_position),
    ]

    y = 15
    for line in lines:
        text = font.render(line, True, (255, 255, 255))
        screen.blit(text, (20, y))
        y += 28

    pygame.display.flip()
    time.sleep(FPS_DELAY_SECONDS)
