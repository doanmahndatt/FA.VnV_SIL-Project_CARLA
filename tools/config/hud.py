import argparse
import math
import queue
import time
import weakref
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import carla
import numpy as np
import pygame
import yaml


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[2]
MAPS_DIR = BASE_DIR / "maps_CARLA"
OPENDRIVE_DIR = MAPS_DIR / "OpenDrive"

TOTAL_WIDTH = 1280
HEIGHT = 720
PANEL_WIDTH = 220
CAM_WIDTH = TOTAL_WIDTH - PANEL_WIDTH
FPS = 30

FEATURE_CONFIG = {
    "ACC": {
        "domain": "longitudinal_feature",
        "signals": REPO_ROOT
        / "config"
        / "controllers_fmu"
        / "longitudinal_feature"
        / "ACC"
        / "signals.yaml",
    },
    "AEB": {
        "domain": "brake_feature",
        "signals": REPO_ROOT
        / "config"
        / "controllers_fmu"
        / "brake_feature"
        / "AEB"
        / "signals.yaml",
    },
    "LKA": {
        "domain": "lateral_feature",
        "signals": REPO_ROOT
        / "config"
        / "controllers_fmu"
        / "lateral_feature"
        / "LKA"
        / "signals.yaml",
    },
}

STATUS_COLORS = {
    "ok": (81, 207, 102),
    "warn": (255, 212, 59),
    "risk": (255, 107, 107),
    "muted": (134, 142, 150),
    "active": (77, 171, 247),
}

BG = (13, 17, 23)
PANEL_BG = (22, 27, 34)
SECTION_BG = (32, 38, 46)
TEXT = (230, 237, 243)
SUBTLE = (139, 148, 158)
LINE = (48, 54, 61)


_map_cache = {}


@dataclass
class LanePosition:
    map_name: str
    road_id: int | None
    lane_id: int | None
    configured: bool
    offset_m: float | None
    heading_error_deg: float | None


@dataclass
class RuntimeSnapshot:
    sim_time: float
    server_fps: float
    client_fps: float
    map_name: str
    ego_role: str
    target_role: str
    ego_speed_kph: float
    target_speed_kph: float
    acceleration_mps2: float
    distance_m: float | None
    relative_speed_mps: float
    ttc_s: float | None
    nearby_vehicle_count: int
    nearby_vehicles: list[str]
    control: carla.VehicleControl | None
    brake_active: bool
    gear_text: str
    hand_brake_active: bool
    ego_lane: LanePosition
    target_lane: LanePosition


def get_args():
    parser = argparse.ArgumentParser(description="CARLA ADAS visualization HUD")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--ego-role", default="ev")
    parser.add_argument("--target-prefix", default="tv")
    parser.add_argument("--feature", choices=sorted(FEATURE_CONFIG), default="ACC")
    parser.add_argument("--width", type=int, default=TOTAL_WIDTH)
    parser.add_argument("--height", type=int, default=HEIGHT)
    parser.add_argument("--panel-width", type=int, default=PANEL_WIDTH)
    parser.add_argument("--camera-distance-scale", type=float, default=1.85)
    parser.add_argument("--camera-height-scale", type=float, default=1.75)
    parser.add_argument("--camera-pitch", type=float, default=6.0)
    return parser.parse_args()


def find_vehicle(world, role):
    for vehicle in world.get_actors().filter("vehicle.*"):
        if vehicle.attributes.get("role_name") == role:
            return vehicle
    return None


def get_vehicle_role(vehicle):
    if not vehicle:
        return ""
    return vehicle.attributes.get("role_name", "")


def get_actor_display_name(actor, truncate=22):
    name = " ".join(actor.type_id.replace("vehicle.", "").replace("_", ".").split(".")[1:])
    return (name[: truncate - 3] + "...") if len(name) > truncate else name


def get_speed(vehicle):
    if not vehicle:
        return 0.0
    velocity = vehicle.get_velocity()
    return 3.6 * math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)


def get_acceleration(vehicle):
    if not vehicle:
        return 0.0
    acceleration = vehicle.get_acceleration()
    return math.sqrt(acceleration.x**2 + acceleration.y**2 + acceleration.z**2)


def format_gear(control):
    if control is None:
        return "--"
    if control.reverse or control.gear < 0:
        return "R"
    if control.manual_gear_shift and control.gear == 0 and control.hand_brake:
        return "P"
    if control.gear == 0:
        return "N"
    return f"D{control.gear}"


def signed_longitudinal_distance(ev, tv):
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


def normalize_angle_degrees(angle):
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle


def get_lane_position(world_map, vehicle):
    map_name = get_world_map_name(world_map)
    if not vehicle:
        return LanePosition(map_name, None, None, False, None, None)

    waypoint = world_map.get_waypoint(
        vehicle.get_location(),
        project_to_road=True,
        lane_type=carla.LaneType.Driving,
    )
    if waypoint is None:
        return LanePosition(map_name, None, None, False, None, None)

    lane_index = load_opendrive_lane_index(map_name)
    road_id = waypoint.road_id
    lane_id = waypoint.lane_id
    is_configured = bool(lane_index) and lane_id in lane_index.get(road_id, set())

    vehicle_location = vehicle.get_location()
    lane_location = waypoint.transform.location
    offset_vector = vehicle_location - lane_location
    lane_right = waypoint.transform.get_right_vector()
    signed_offset = (
        offset_vector.x * lane_right.x
        + offset_vector.y * lane_right.y
        + offset_vector.z * lane_right.z
    )
    heading_error = normalize_angle_degrees(
        vehicle.get_transform().rotation.yaw - waypoint.transform.rotation.yaw
    )

    return LanePosition(map_name, road_id, lane_id, is_configured, signed_offset, heading_error)


def find_target_vehicle(world, world_map, ev, target_role_prefix="tv"):
    if not ev:
        return None

    candidates = []
    ev_lane_position = get_lane_position(world_map, ev)

    for vehicle in world.get_actors().filter("vehicle.*"):
        if vehicle.id == ev.id:
            continue

        role = get_vehicle_role(vehicle)
        if not role.startswith(target_role_prefix):
            continue

        vehicle_lane_position = get_lane_position(world_map, vehicle)
        distance = signed_longitudinal_distance(ev, vehicle)
        same_lane = (
            ev_lane_position.road_id is not None
            and ev_lane_position.lane_id is not None
            and vehicle_lane_position.road_id == ev_lane_position.road_id
            and vehicle_lane_position.lane_id == ev_lane_position.lane_id
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


def apply_ev_brake_lights(vehicle, brake_active):
    if not vehicle:
        return

    try:
        light_state = vehicle.get_light_state()
        if brake_active:
            light_state |= carla.VehicleLightState.Brake
        else:
            light_state &= ~carla.VehicleLightState.Brake
        vehicle.set_light_state(carla.VehicleLightState(light_state))
    except RuntimeError:
        return


def load_feature_signals(feature):
    path = FEATURE_CONFIG[feature]["signals"]
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class CameraView:
    def __init__(self, width, height, distance_scale, height_scale, pitch):
        self.width = width
        self.height = height
        self.distance_scale = distance_scale
        self.height_scale = height_scale
        self.pitch = pitch
        self.sensor = None
        self.parent_id = None
        self.world_id = None
        self.image_queue = queue.Queue(maxsize=1)
        self.surface = None

    def ensure_attached(self, world, ego):
        if not ego or not ego.is_alive:
            self.destroy()
            return
        if (
            self.sensor
            and self.parent_id == ego.id
            and self.world_id == world.id
            and self.sensor.is_alive
        ):
            return

        self.destroy()
        blueprint = world.get_blueprint_library().find("sensor.camera.rgb")
        blueprint.set_attribute("image_size_x", str(self.width))
        blueprint.set_attribute("image_size_y", str(self.height))
        blueprint.set_attribute("fov", "90")
        blueprint.set_attribute("gamma", "2.2")
        bound_x = 0.5 + ego.bounding_box.extent.x
        bound_z = 0.5 + ego.bounding_box.extent.z
        transform = carla.Transform(
            carla.Location(
                x=-self.distance_scale * bound_x,
                y=0.0,
                z=self.height_scale * bound_z,
            ),
            carla.Rotation(pitch=self.pitch),
        )
        try:
            self.sensor = world.spawn_actor(
                blueprint,
                transform,
                attach_to=ego,
                attachment_type=carla.AttachmentType.SpringArm,
            )
        except RuntimeError:
            self.sensor = None
            return
        self.parent_id = ego.id
        self.world_id = world.id
        weak_self = weakref.ref(self)
        self.sensor.listen(lambda image: CameraView._parse_image(weak_self, image))

    def destroy(self):
        if self.sensor is not None:
            try:
                self.sensor.stop()
                self.sensor.destroy()
            except RuntimeError:
                pass
        self.sensor = None
        self.parent_id = None
        self.world_id = None
        self.surface = None
        while not self.image_queue.empty():
            try:
                self.image_queue.get_nowait()
            except queue.Empty:
                break

    def render(self, display, left, top):
        try:
            self.surface = self.image_queue.get_nowait()
        except queue.Empty:
            pass

        rect = pygame.Rect(left, top, self.width, self.height)
        if self.surface:
            display.blit(self.surface, rect)
        else:
            pygame.draw.rect(display, BG, rect)
            font = pygame.font.SysFont("segoeui", 22)
            text = font.render("Waiting for ego camera", True, SUBTLE)
            display.blit(text, text.get_rect(center=rect.center))

    @staticmethod
    def _parse_image(weak_self, image):
        self = weak_self()
        if not self:
            return

        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = np.reshape(array, (image.height, image.width, 4))
        array = array[:, :, :3][:, :, ::-1]
        surface = pygame.surfarray.make_surface(array.swapaxes(0, 1))
        if self.image_queue.full():
            try:
                self.image_queue.get_nowait()
            except queue.Empty:
                pass
        self.image_queue.put(surface)


class RuntimeMonitor:
    def __init__(self):
        self.world_id = None
        self.start_time = None
        self.previous_snapshot_elapsed = None
        self.server_fps = 0.0

    def sample(self, world, ego_role, target_prefix, client_fps):
        if self.world_id != world.id:
            self.world_id = world.id
            self.start_time = None
            self.previous_snapshot_elapsed = None
            self.server_fps = 0.0

        world_map = world.get_map()
        map_name = get_world_map_name(world_map)
        snapshot_time = world.get_snapshot().timestamp.elapsed_seconds

        if self.start_time is None:
            self.start_time = snapshot_time
            self.previous_snapshot_elapsed = snapshot_time

        if self.previous_snapshot_elapsed is not None:
            delta = snapshot_time - self.previous_snapshot_elapsed
            if delta > 0:
                self.server_fps = 1.0 / delta
        self.previous_snapshot_elapsed = snapshot_time

        ev = find_vehicle(world, ego_role)
        tv = find_target_vehicle(world, world_map, ev, target_prefix) if ev else None
        vehicles = list(world.get_actors().filter("vehicle.*"))

        ego_speed = get_speed(ev)
        target_speed = get_speed(tv)
        distance = signed_longitudinal_distance(ev, tv) if ev and tv else None
        relative_speed = (ego_speed - target_speed) / 3.6 if tv else 0.0
        ttc = None
        if distance is not None and distance > 0 and relative_speed > 0.1:
            ttc = distance / relative_speed
        control = ev.get_control() if ev else None
        brake_active = bool(control and control.brake > 0.03)
        apply_ev_brake_lights(ev, brake_active)
        nearby_vehicles = self._nearby_vehicle_lines(vehicles, ev)

        return RuntimeSnapshot(
            sim_time=snapshot_time - self.start_time,
            server_fps=self.server_fps,
            client_fps=client_fps,
            map_name=map_name,
            ego_role=get_vehicle_role(ev).upper() if ev else ego_role.upper(),
            target_role=get_vehicle_role(tv).upper() if tv else "NO TARGET",
            ego_speed_kph=ego_speed,
            target_speed_kph=target_speed,
            acceleration_mps2=get_acceleration(ev),
            distance_m=distance,
            relative_speed_mps=relative_speed,
            ttc_s=ttc,
            nearby_vehicle_count=max(0, len(vehicles) - (1 if ev else 0)),
            nearby_vehicles=nearby_vehicles,
            control=control,
            brake_active=brake_active,
            gear_text=format_gear(control),
            hand_brake_active=bool(control and control.hand_brake),
            ego_lane=get_lane_position(world_map, ev),
            target_lane=get_lane_position(world_map, tv),
        )

    def _nearby_vehicle_lines(self, vehicles, ev, limit=9):
        if not ev:
            return []

        ev_location = ev.get_location()
        nearby = []
        for vehicle in vehicles:
            if vehicle.id == ev.id:
                continue
            distance = ev_location.distance(vehicle.get_location())
            nearby.append((distance, get_actor_display_name(vehicle)))

        nearby.sort(key=lambda item: item[0])
        return [f"{int(distance):>3}m {name}" for distance, name in nearby[:limit]]


class HudPanel:
    def __init__(self, width, height, feature):
        self.width = width
        self.height = height
        self.feature = feature
        self.signals = load_feature_signals(feature)
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.title_font = pygame.font.SysFont("segoeui", 22, bold=True)
        self.section_font = pygame.font.SysFont("segoeui", 15, bold=True)
        self.label_font = pygame.font.SysFont("segoeui", 14)
        self.value_font = pygame.font.SysFont("consolas", 14)
        self.small_font = pygame.font.SysFont("segoeui", 12)
        self.classic_font = pygame.font.SysFont("consolas", 13)
        self.classic_font_bold = pygame.font.SysFont("consolas", 13, bold=True)

    def set_feature(self, feature):
        self.feature = feature
        self.signals = load_feature_signals(feature)

    def render(self, display, snapshot):
        self._render_classic(snapshot)
        display.blit(self.surface, (0, 0))

    def _render_classic(self, snapshot):
        self.surface.fill((0, 0, 0, 104))

        control = snapshot.control
        throttle = control.throttle if control else 0.0
        brake = control.brake if control else 0.0
        steer = control.steer if control else 0.0

        y = 5
        y = self._classic_pair(y, "Server:", f"{snapshot.server_fps:>8.0f} FPS")
        y = self._classic_pair(y, "Client:", f"{snapshot.client_fps:>8.0f} FPS")
        y += 17

        y = self._classic_pair(y, "Vehicle:", snapshot.ego_role)
        y = self._classic_pair(y, "Map:", snapshot.map_name)
        y = self._classic_pair(y, "Simulation time:", self._clock(snapshot.sim_time))
        y = self._classic_pair(y, "Gear:", snapshot.gear_text)
        y = self._classic_pair(y, "EPB:", "ON" if snapshot.hand_brake_active else "OFF")
        y += 17

        y = self._classic_pair(y, "Speed:", f"{snapshot.ego_speed_kph:>7.0f} km/h")
        y = self._classic_pair(y, "Heading:", self._fmt(snapshot.ego_lane.heading_error_deg, "deg"))
        y = self._classic_pair(y, "Lane:", self._lane_text(snapshot.ego_lane))
        y = self._classic_pair(y, "Offset:", self._fmt(snapshot.ego_lane.offset_m, "m"))
        y += 17

        y = self._classic_bar(y, "Throttle:", throttle, 0.0, 1.0)
        y = self._classic_bar(y, "Steer:", steer, -1.0, 1.0)
        y = self._classic_bar(y, "Brake:", brake, 0.0, 1.0)
        y = self._classic_pair(y, "Hand brake:", "[X]" if snapshot.hand_brake_active else "[]")
        y = self._classic_pair(y, "Brake lights:", "ON" if snapshot.brake_active else "OFF")
        y += 17

        y = self._classic_line(y, "ADAS:")
        y = self._classic_pair(y, "Feature:", self.feature)
        y = self._classic_pair(y, "Target:", snapshot.target_role)
        y = self._classic_pair(y, "Distance:", self._fmt(snapshot.distance_m, "m"))
        y = self._classic_pair(y, "TTC:", self._fmt(snapshot.ttc_s, "s"))
        y = self._classic_pair(y, "Rel speed:", f"{snapshot.relative_speed_mps:>7.2f} m/s")

        if self.feature == "AEB":
            notice = (
                "[!] FAEB intervention - brake!!!"
                if self._is_aeb_intervention(snapshot)
                else "AEB monitoring"
            )
            color = STATUS_COLORS["risk"] if self._is_aeb_intervention(snapshot) else TEXT
            y = self._classic_line(y, notice, color=color, font=self.classic_font_bold)

        y += 8
        pygame.draw.line(self.surface, (255, 136, 0), (6, y), (self.width - 12, y), 2)
        y += 14

        y = self._classic_pair(y, "Number of vehicles:", str(snapshot.nearby_vehicle_count))
        y = self._classic_line(y, "Nearby vehicles:")
        for line in snapshot.nearby_vehicles:
            y = self._classic_line(y, line, x=20)

        self._classic_line(self.height - 22, "F2: switch ADAS function", color=(220, 220, 220))

    def _classic_line(self, y, text, x=6, color=TEXT, font=None):
        rendered = (font or self.classic_font).render(str(text), True, color)
        self.surface.blit(rendered, (x, y))
        return y + 16

    def _classic_pair(self, y, label, value):
        self._classic_line(y, label)
        value_surface = self.classic_font.render(str(value), True, TEXT)
        self.surface.blit(value_surface, (self.width - value_surface.get_width() - 10, y))
        return y + 16

    def _classic_bar(self, y, label, value, min_value, max_value):
        self._classic_line(y, label)
        percent_text = self._percent_text(value, signed=min_value < 0.0)
        percent_surface = self.classic_font.render(percent_text, True, TEXT)
        self.surface.blit(percent_surface, (self.width - percent_surface.get_width() - 10, y))
        bar_x = 98
        bar_y = y + 5
        bar_w = self.width - bar_x - percent_surface.get_width() - 24
        pygame.draw.rect(self.surface, TEXT, (bar_x, bar_y, bar_w, 6), 1)

        if min_value < 0:
            mid = bar_x + bar_w // 2
            pygame.draw.line(self.surface, TEXT, (mid, bar_y - 2), (mid, bar_y + 8), 1)
            normalized = max(-1.0, min(1.0, value))
            if normalized >= 0:
                fill = pygame.Rect(mid, bar_y + 1, int((bar_w / 2) * normalized), 4)
            else:
                fill = pygame.Rect(
                    mid + int((bar_w / 2) * normalized),
                    bar_y + 1,
                    int((bar_w / 2) * -normalized),
                    4,
                )
        else:
            normalized = max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))
            fill = pygame.Rect(bar_x, bar_y + 1, int((bar_w - 2) * normalized), 4)

        if fill.width > 0:
            pygame.draw.rect(self.surface, TEXT, fill)
        return y + 16

    def _clock(self, seconds):
        seconds = max(0, int(seconds))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"

    def _lane_text(self, lane_position):
        if lane_position.road_id is None or lane_position.lane_id is None:
            return "--"
        return f"R{lane_position.road_id} L{lane_position.lane_id}"

    def _render_header(self, y):
        domain = FEATURE_CONFIG[self.feature]["domain"]
        title = self.title_font.render("ADAS Visualizer", True, TEXT)
        self.surface.blit(title, (18, y))
        y += 31

        badge = pygame.Rect(18, y, 88, 24)
        pygame.draw.rect(self.surface, STATUS_COLORS["active"], badge, border_radius=5)
        self._text(self.feature, 30, y + 3, self.small_font, BG)
        self._text(domain, 116, y + 3, self.small_font, SUBTLE)
        self._text("F2 switch", self.width - 74, y + 4, self.small_font, SUBTLE)
        return y + 40

    def _render_aeb_alert_if_needed(self, y, snapshot):
        if self.feature != "AEB" or not self._is_aeb_intervention(snapshot):
            return y

        x = 14
        width = self.width - 28
        rect = pygame.Rect(x, y, width, 32)
        pygame.draw.rect(self.surface, (100, 18, 18), rect, border_radius=6)
        pygame.draw.rect(self.surface, STATUS_COLORS["risk"], rect, 2, border_radius=6)
        self._text("[!] FAEB intervention - brake!!!", x + 12, y + 6, self.section_font, TEXT)
        return y + 36

    def _render_system(self, y, snapshot):
        rows = [
            ("Server FPS", f"{snapshot.server_fps:5.1f}"),
            ("Client FPS", f"{snapshot.client_fps:5.1f}"),
            ("Sim time", f"{snapshot.sim_time:6.2f} s"),
            ("Map", snapshot.map_name),
            ("Gear", snapshot.gear_text),
            ("EPB", "ON" if snapshot.hand_brake_active else "OFF"),
        ]
        return self._section("System", rows, y)

    def _render_ego(self, y, snapshot):
        ego_lane = snapshot.ego_lane
        lane = "--"
        if ego_lane.road_id is not None and ego_lane.lane_id is not None:
            lane = f"R{ego_lane.road_id} / L{ego_lane.lane_id}"
        rows = [
            ("Role", snapshot.ego_role),
            ("Speed", f"{snapshot.ego_speed_kph:5.1f} km/h"),
            ("Accel", f"{snapshot.acceleration_mps2:5.2f} m/s2"),
            ("Road/Lane", lane),
            ("Lane offset", self._fmt(snapshot.ego_lane.offset_m, "m")),
            ("Heading err", self._fmt(snapshot.ego_lane.heading_error_deg, "deg")),
        ]
        return self._section("Ego Vehicle", rows, y)

    def _render_environment(self, y, snapshot):
        rows = [
            ("Target", snapshot.target_role),
            ("Target speed", f"{snapshot.target_speed_kph:5.1f} km/h"),
            ("Distance", self._fmt(snapshot.distance_m, "m")),
            ("Rel speed", f"{snapshot.relative_speed_mps:5.2f} m/s"),
            ("TTC", self._fmt(snapshot.ttc_s, "s")),
            ("Nearby vehicles", str(snapshot.nearby_vehicle_count)),
        ]
        return self._section("Target / Environment", rows, y)

    def _render_function_details(self, y, snapshot):
        if self.feature == "AEB":
            return self._render_aeb(y, snapshot)
        if self.feature == "LKA":
            return self._render_lka(y, snapshot)
        return self._render_acc(y, snapshot)

    def _render_acc(self, y, snapshot):
        params = self.signals.get("parameters", {})
        target_speed = float(params.get("target_speed", 0.0)) * 3.6
        time_gap = float(params.get("time_gap", 0.0))
        min_distance = float(params.get("min_distance", 0.0))
        safe_distance = max(min_distance, snapshot.ego_speed_kph / 3.6 * time_gap)
        distance_error = None
        if snapshot.distance_m is not None:
            distance_error = snapshot.distance_m - safe_distance

        state, color = self._acc_state(snapshot, safe_distance)
        y = self._section(
            "Function Details",
            [
                ("State", state),
                ("Target speed", f"{target_speed:5.1f} km/h"),
                ("Time gap", f"{time_gap:4.1f} s"),
                ("Safe distance", f"{safe_distance:5.1f} m"),
                ("Distance err", self._fmt(distance_error, "m")),
            ],
            y,
            state_color=color,
        )
        return self._control_bars(y, snapshot)

    def _render_aeb(self, y, snapshot):
        params = self.signals.get("parameters", {})
        warning_ttc = float(params.get("warning_ttc", 1.8))
        brake_ttc = float(params.get("brake_ttc", 1.0))
        emergency_ttc = float(params.get("emergency_ttc", 0.55))
        hard_brake_distance = float(params.get("hard_brake_distance", 3.2))
        min_distance = float(params.get("min_distance", 0.0))
        state, color = self._aeb_state(
            snapshot, warning_ttc, brake_ttc, emergency_ttc, hard_brake_distance
        )
        intervention = self._is_aeb_intervention(snapshot)
        notice = "[!] FAEB intervention - brake!!!" if intervention else "Ready"

        y = self._section(
            "Function Details",
            [
                ("State", state),
                ("Notice", notice),
                ("Warning TTC", f"{warning_ttc:4.1f} s"),
                ("Brake TTC", f"{brake_ttc:4.1f} s"),
                ("Emergency TTC", f"{emergency_ttc:4.1f} s"),
                ("Min distance", f"{min_distance:4.1f} m"),
                ("Hard distance", f"{hard_brake_distance:4.1f} m"),
            ],
            y,
            state_color=color,
            notice_color=STATUS_COLORS["risk"] if intervention else SUBTLE,
        )
        return self._control_bars(y, snapshot)

    def _render_lka(self, y, snapshot):
        params = self.signals.get("parameters", {})
        activation = float(params.get("activation_offset", 0.25))
        deadband = float(params.get("deadband_offset", 0.05))
        offset = snapshot.ego_lane.offset_m
        state, color = self._lka_state(offset, activation, deadband)

        y = self._section(
            "Function Details",
            [
                ("State", state),
                ("Lane offset", self._fmt(offset, "m")),
                ("Heading err", self._fmt(snapshot.ego_lane.heading_error_deg, "deg")),
                ("Activation", f"{activation:4.2f} m"),
                ("Deadband", f"{deadband:4.2f} m"),
                ("Has lane", "YES" if snapshot.ego_lane.road_id is not None else "NO"),
            ],
            y,
            state_color=color,
        )
        return self._control_bars(y, snapshot)

    def _section(self, title, rows, y, state_color=None, notice_color=None):
        x = 14
        width = self.width - 28
        row_h = 18
        height = 28 + row_h * len(rows)
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.surface, SECTION_BG, rect, border_radius=6)
        pygame.draw.rect(self.surface, LINE, rect, 1, border_radius=6)
        self._text(title.upper(), x + 12, y + 6, self.section_font, TEXT)

        row_y = y + 28
        for label, value in rows:
            self._text(label, x + 12, row_y, self.label_font, SUBTLE)
            color = state_color if label == "State" and state_color else TEXT
            if label == "Notice" and notice_color:
                color = notice_color
            self._text(str(value), x + 142, row_y, self.value_font, color)
            row_y += row_h
        return y + height + 8

    def _control_bars(self, y, snapshot):
        control = snapshot.control
        throttle = control.throttle if control else 0.0
        brake = control.brake if control else 0.0
        steer = control.steer if control else 0.0
        brake_active = snapshot.brake_active

        x = 14
        width = self.width - 28
        rect = pygame.Rect(x, y, width, 104)
        pygame.draw.rect(self.surface, SECTION_BG, rect, border_radius=6)
        pygame.draw.rect(self.surface, LINE, rect, 1, border_radius=6)
        self._text("CONTROL OUTPUT", x + 12, y + 6, self.section_font, TEXT)

        self._bar("Throttle", throttle, 0.0, 1.0, x + 12, y + 31, STATUS_COLORS["ok"])
        self._bar("Brake", brake, 0.0, 1.0, x + 12, y + 53, STATUS_COLORS["risk"])
        self._bar("Steer", steer, -1.0, 1.0, x + 12, y + 75, STATUS_COLORS["active"])
        self._brake_light_badge(x + 12, y + 88, brake_active)
        return y + 112

    def _bar(self, label, value, min_value, max_value, x, y, color):
        bar_x = x + 86
        bar_w = self.width - bar_x - 30
        self._text(label, x, y - 2, self.label_font, SUBTLE)
        pygame.draw.rect(self.surface, (18, 22, 28), (bar_x, y + 3, bar_w, 9), border_radius=4)

        if min_value < 0:
            mid = bar_x + bar_w // 2
            pygame.draw.line(self.surface, SUBTLE, (mid, y + 1), (mid, y + 15), 1)
            normalized = max(-1.0, min(1.0, value))
            if normalized >= 0:
                fill = pygame.Rect(mid, y + 3, int((bar_w / 2) * normalized), 9)
            else:
                fill = pygame.Rect(
                    mid + int((bar_w / 2) * normalized), y + 3, int((bar_w / 2) * -normalized), 9
                )
        else:
            normalized = max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))
            fill = pygame.Rect(bar_x, y + 3, int(bar_w * normalized), 9)
        pygame.draw.rect(self.surface, color, fill, border_radius=4)
        self._text(
            self._percent_text(value, signed=min_value < 0.0),
            bar_x + bar_w - 48,
            y - 3,
            self.value_font,
            TEXT,
        )

    @staticmethod
    def _percent_text(value, signed=False):
        percent = max(-100.0, min(100.0, float(value) * 100.0))
        if signed:
            return f"{percent:+.0f}%"
        return f"{max(0.0, percent):.0f}%"

    def _acc_state(self, snapshot, safe_distance):
        if snapshot.distance_m is None:
            return "FREE", STATUS_COLORS["active"]
        if snapshot.ttc_s is not None and snapshot.ttc_s < 1.5:
            return "BRAKE", STATUS_COLORS["risk"]
        if snapshot.distance_m < safe_distance:
            return "FOLLOW CLOSE", STATUS_COLORS["warn"]
        return "FOLLOW", STATUS_COLORS["ok"]

    def _aeb_state(self, snapshot, warning_ttc, brake_ttc, emergency_ttc, hard_brake_distance=None):
        if snapshot.hand_brake_active:
            return "PARKED", STATUS_COLORS["ok"]
        if hard_brake_distance is not None and snapshot.distance_m is not None:
            if snapshot.distance_m <= hard_brake_distance:
                return "EMERGENCY", STATUS_COLORS["risk"]
        if snapshot.ttc_s is None:
            return "STANDBY", STATUS_COLORS["muted"]
        if snapshot.ttc_s <= emergency_ttc:
            return "EMERGENCY", STATUS_COLORS["risk"]
        if snapshot.ttc_s <= brake_ttc:
            return "AEB ACTIVE", STATUS_COLORS["risk"]
        if snapshot.ttc_s <= warning_ttc:
            return "WARNING", STATUS_COLORS["warn"]
        return "MONITORING", STATUS_COLORS["ok"]

    def _lka_state(self, offset, activation, deadband):
        if offset is None:
            return "NO LANE", STATUS_COLORS["muted"]
        abs_offset = abs(offset)
        if abs_offset >= activation:
            return "CORRECTING", STATUS_COLORS["warn"]
        if abs_offset <= deadband:
            return "CENTERED", STATUS_COLORS["ok"]
        return "ACTIVE", STATUS_COLORS["active"]

    def _is_braking(self, snapshot):
        return snapshot.brake_active

    def _is_aeb_intervention(self, snapshot):
        params = self.signals.get("parameters", {})
        warning_ttc = float(params.get("warning_ttc", 1.8))
        brake_ttc = float(params.get("brake_ttc", 1.0))
        emergency_ttc = float(params.get("emergency_ttc", 0.55))
        hard_brake_distance = float(params.get("hard_brake_distance", 3.2))
        state, _ = self._aeb_state(
            snapshot, warning_ttc, brake_ttc, emergency_ttc, hard_brake_distance
        )
        return state in {"AEB ACTIVE", "EMERGENCY"}

    def _brake_light_badge(self, x, y, brake_active):
        color = STATUS_COLORS["risk"] if brake_active else STATUS_COLORS["muted"]
        text = "Brake lights ON" if brake_active else "Brake lights OFF"
        pygame.draw.circle(self.surface, color, (x + 8, y + 8), 6)
        pygame.draw.circle(
            self.surface, (255, 190, 190) if brake_active else LINE, (x + 8, y + 8), 2
        )
        self._text(text, x + 22, y - 1, self.label_font, color)

    def _fmt(self, value, unit):
        if value is None:
            return "--"
        return f"{value:5.2f} {unit}"

    def _text(self, text, x, y, font, color):
        rendered = font.render(str(text), True, color)
        self.surface.blit(rendered, (x, y))


def main():
    args = get_args()
    pygame.init()
    pygame.font.init()
    display = pygame.display.set_mode(
        (args.width, args.height), pygame.HWSURFACE | pygame.DOUBLEBUF
    )
    pygame.display.set_caption("ADAS CARLA Visualizer")

    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout)
    clock = pygame.time.Clock()
    monitor = RuntimeMonitor()
    camera_view = CameraView(
        args.width,
        args.height,
        args.camera_distance_scale,
        args.camera_height_scale,
        args.camera_pitch,
    )
    hud = HudPanel(args.panel_width, args.height, args.feature)
    feature_order = sorted(FEATURE_CONFIG)
    feature_index = feature_order.index(args.feature)

    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYUP and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.KEYUP and event.key == pygame.K_F2:
                    feature_index = (feature_index + 1) % len(feature_order)
                    hud.set_feature(feature_order[feature_index])

            world = client.get_world()
            ego = find_vehicle(world, args.ego_role)
            camera_view.ensure_attached(world, ego)
            snapshot = monitor.sample(world, args.ego_role, args.target_prefix, clock.get_fps())

            display.fill(BG)
            camera_view.render(display, 0, 0)
            hud.render(display, snapshot)
            pygame.display.flip()
            clock.tick(FPS)
    finally:
        camera_view.destroy()
        pygame.quit()


if __name__ == "__main__":
    main()
