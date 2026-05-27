#!/usr/bin/env python

# Copyright (c) 2018-2020 Intel Corporation
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

"""
This module provides the ScenarioManager implementation.
It must not be modified and is for reference only!
"""

from __future__ import print_function
import sys
import time

import py_trees

import carla

from srunner.autoagents.agent_wrapper import AgentWrapper
from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
from srunner.scenariomanager.result_writer import ResultOutputProvider
from srunner.scenariomanager.timer import GameTime
from srunner.scenariomanager.watchdog import Watchdog


class ScenarioManager(object):

    """
    Basic scenario manager class. This class holds all functionality
    required to start, and analyze a scenario.

    The user must not modify this class.

    To use the ScenarioManager:
    1. Create an object via manager = ScenarioManager()
    2. Load a scenario via manager.load_scenario()
    3. Trigger the execution of the scenario manager.run_scenario()
       This function is designed to explicitly control start and end of
       the scenario execution
    4. Trigger a result evaluation with manager.analyze_scenario()
    5. If needed, cleanup with manager.stop_scenario()
    """

    def __init__(self, debug_mode=False, sync_mode=False, timeout=2.0):
        """
        Setups up the parameters, which will be filled at load_scenario()

        """
        self.scenario = None
        self.scenario_tree = None
        self.ego_vehicles = None
        self.other_actors = None

        self._debug_mode = debug_mode
        self._agent = None
        self._sync_mode = sync_mode
        self._watchdog = None
        self._timeout = timeout

        self._running = False
        self._timestamp_last_run = 0.0
        self.scenario_duration_system = 0.0
        self.scenario_duration_game = 0.0
        self.start_system_time = None
        self.end_system_time = None
        self._next_sync_tick_time = None
        self._urban_traffic = None
        self._last_debug_print_time = -1.0

    def _reset(self):
        """
        Reset all parameters
        """
        self._running = False
        self._timestamp_last_run = 0.0
        self.scenario_duration_system = 0.0
        self.scenario_duration_game = 0.0
        self.start_system_time = None
        self.end_system_time = None
        self._next_sync_tick_time = None
        self._last_debug_print_time = -1.0
        GameTime.restart()

    def set_urban_traffic(self, urban_traffic):
        """
        Register ScenarioRunner-managed Traffic Manager background traffic.
        """
        self._urban_traffic = urban_traffic

    def cleanup(self):
        """
        This function triggers a proper termination of a scenario
        """

        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog = None

        if self.scenario is not None:
            self.scenario.terminate()

        if self._agent is not None:
            self._agent.cleanup()
            self._agent = None

        CarlaDataProvider.cleanup()

    def load_scenario(self, scenario, agent=None):
        """
        Load a new scenario
        """
        self._reset()
        self._agent = AgentWrapper(agent) if agent else None
        if self._agent is not None:
            self._sync_mode = True
        self.scenario = scenario
        self.scenario_tree = self.scenario.scenario_tree
        self.ego_vehicles = scenario.ego_vehicles
        self.other_actors = scenario.other_actors

        # To print the scenario tree uncomment the next line
        # py_trees.display.render_dot_tree(self.scenario_tree)

        if self._agent is not None:
            self._agent.setup_sensors(self.ego_vehicles[0], self._debug_mode)

    def run_scenario(self):
        """
        Trigger the start of the scenario and wait for it to finish/fail
        """
        print("ScenarioManager: Running scenario {}".format(self.scenario_tree.name))
        self.start_system_time = time.time()
        start_game_time = GameTime.get_time()

        self._watchdog = Watchdog(float(self._timeout))
        self._watchdog.start()
        self._running = True
        self._next_sync_tick_time = time.perf_counter()

        while self._running:
            timestamp = None
            world = CarlaDataProvider.get_world()
            if world:
                snapshot = world.get_snapshot()
                if snapshot:
                    timestamp = snapshot.timestamp
            if timestamp:
                self._tick_scenario(timestamp)

        #self.cleanup()

        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog = None

        print("[INFO] Skip cleanup - batch will handle actors")

        self.end_system_time = time.time()
        end_game_time = GameTime.get_time()

        self.scenario_duration_system = self.end_system_time - \
            self.start_system_time
        self.scenario_duration_game = end_game_time - start_game_time

        if self.scenario_tree.status == py_trees.common.Status.FAILURE:
            print("ScenarioManager: Terminated due to failure")

    def _tick_scenario(self, timestamp):

        if self._timestamp_last_run < timestamp.elapsed_seconds and self._running:
            self._timestamp_last_run = timestamp.elapsed_seconds

            self._watchdog.update()

            # ========================
            # ✅ TIME + PROVIDER
            # ========================
            GameTime.on_carla_tick(timestamp)
            CarlaDataProvider.on_carla_tick()

            world = CarlaDataProvider.get_world()

            settings = world.get_settings()
            debug_due = (
                self._last_debug_print_time < 0.0
                or GameTime.get_time() - self._last_debug_print_time >= 1.0
            )
            if debug_due:
                self._last_debug_print_time = GameTime.get_time()
                print("[DEBUG] fixed_delta_seconds =", settings.fixed_delta_seconds)


            # ========================
            # ✅ GET ACTORS
            # ========================
            ev = None
            tv = None

            for actor in world.get_actors().filter("vehicle.*"):
                role = actor.attributes.get("role_name")

                if role == "ev":
                    ev = actor
                elif role == "tv":
                    tv = actor
            if tv is None:
                for actor in world.get_actors().filter("walker.*"):
                    if actor.attributes.get("role_name") == "VRU":
                        tv = actor
                        break

            # ========================
            # ✅ DEBUG ACTORS
            # ========================
            if debug_due and ev is None:
                print("[DEBUG] EV NOT FOUND")
            if debug_due and tv is None:
                print("[DEBUG] TARGET NOT FOUND")

            # ========================
            # ✅ STEP 1: WAKE-UP PHASE (QUAN TRỌNG NHẤT)
            # ========================
            if ev is not None and ev.is_alive:

                if GameTime.get_time() < 0.5:

                    physics = ev.get_physics_control()
                    ev.apply_physics_control(physics)

                    ev.set_simulate_physics(True)
                    ev.set_autopilot(False)

                    ev.set_target_velocity(carla.Vector3D(0, 0, 0))
                    ev.set_target_angular_velocity(carla.Vector3D(0, 0, 0))

                    ev.set_transform(ev.get_transform())

                    print("[FIX] EV WAKE-UP APPLIED")

            # ========================
            # ✅ STEP 2: TICK SCENARIO (ONLY ONCE)
            # ========================
            self.scenario_tree.tick_once()

            # ========================
            # ✅ STEP 3: DEBUG RESULT (after physics updated)
            # ========================
            if self._urban_traffic is not None:
                self._urban_traffic.tick(GameTime.get_time())

            if debug_due and ev is not None:
                print(f"[EV] speed={ev.get_velocity().length():.2f}")

            if debug_due and tv is not None and tv.is_alive:
                vel = tv.get_velocity()
                ctrl = tv.get_control()
                if tv.type_id.startswith("walker."):
                    print(f"[TARGET VRU] speed={vel.length():.2f}")
                else:
                    print(
                        f"[TARGET TV] speed={vel.length():.2f} "
                        f"throttle={ctrl.throttle:.2f} brake={ctrl.brake:.2f}"
                    )

            if debug_due:
                print(f"[TREE] {self.scenario_tree.status}")
                print(f"[TIME] {GameTime.get_time():.2f}")

            # ========================
            # ✅ STOP CONDITION
            # ========================
            if self.scenario_tree.status != py_trees.common.Status.RUNNING:
                print(f"[INFO] Scenario finished at t={GameTime.get_time():.2f}")
                self._running = False

        # ========================
        # ✅ TICK WORLD (SYNC MODE)
        # ========================
        if self._sync_mode and self._running and self._watchdog.get_status():
            self._pace_sync_tick()
            CarlaDataProvider.get_world().tick()

    def _pace_sync_tick(self):
        world = CarlaDataProvider.get_world()
        if world is None:
            return

        fixed_delta_seconds = world.get_settings().fixed_delta_seconds
        if fixed_delta_seconds is None or fixed_delta_seconds <= 0:
            return

        now = time.perf_counter()
        if self._next_sync_tick_time is None or self._next_sync_tick_time < now - fixed_delta_seconds:
            self._next_sync_tick_time = now

        sleep_time = self._next_sync_tick_time - now
        if sleep_time > 0:
            time.sleep(sleep_time)

        self._next_sync_tick_time += fixed_delta_seconds

    def get_running_status(self):
        """
        returns:
           bool:  False if watchdog exception occured, True otherwise
        """
        return self._watchdog.get_status()

    def stop_scenario(self):
        """
        This function is used by the overall signal handler to terminate the scenario execution
        """
        self._running = False

    def analyze_scenario(self, stdout, filename, junit, json):
        """
        This function is intended to be called from outside and provide
        the final statistics about the scenario (human-readable, in form of a junit
        report, etc.)
        """

        failure = False
        timeout = False
        result = "SUCCESS"

        criteria = self.scenario.get_criteria()
        if len(criteria) == 0:
            print("Nothing to analyze, this scenario has no criteria")
            return True

        for criterion in criteria:
            if (not criterion.optional and
                    criterion.test_status != "SUCCESS" and
                    criterion.test_status != "ACCEPTABLE"):
                failure = True
                result = "FAILURE"
            elif criterion.test_status == "ACCEPTABLE":
                result = "ACCEPTABLE"

        if self.scenario.timeout_node.timeout and not failure:
            timeout = True
            result = "TIMEOUT"

        output = ResultOutputProvider(self, result, stdout, filename, junit, json)
        output.write()

        return failure or timeout
