from pythonfmu import Fmi2Causality, Fmi2Slave, Real


class AEBController(Fmi2Slave):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Inputs - keep stable modelDescription.xml names.
        self.ego_speed = 0.0
        self.lead_distance = 999.0
        self.lead_speed = 0.0
        self.target_speed = 20.0
        self.heading_error = 0.0
        self.has_lead = 0.0
        self.has_waypoint = 0.0

        # Tunable AEB parameters.
        self.min_distance = 4.5
        self.warning_ttc = 1.8
        self.brake_ttc = 1.5
        self.emergency_ttc = 0.55
        self.kp_speed = 0.35
        self.kp_brake = 0.7
        self.max_throttle = 0.75
        self.max_brake = 1.0
        self.brake_hold_time = 0.5
        self.hard_brake_distance = 3.2
        self.park_speed_threshold = 0.25
        self.park_hold_delay = 1.5
        self.kp_steer = 1.2
        self.max_steer = 0.6

        # Outputs.
        self.throttle = 0.0
        self.brake = 0.0
        self.steer = 0.0
        self.deceleration = 0.0
        self.ttc = 999.0
        self.relative_speed = 0.0
        self.safe_distance = 4.5
        self.distance_error = 0.0
        self.aeb_state = 0.0
        self.hand_brake = 0.0
        self.manual_gear_shift = 0.0
        self.gear = 1.0

        self._hold_until = 0.0
        self._intervened = False
        self._parked = False

        self.register_variable(Real("ego_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("lead_distance", causality=Fmi2Causality.input))
        self.register_variable(Real("lead_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("target_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("heading_error", causality=Fmi2Causality.input))
        self.register_variable(Real("has_lead", causality=Fmi2Causality.input))
        self.register_variable(Real("has_waypoint", causality=Fmi2Causality.input))
        self.register_variable(Real("min_distance", causality=Fmi2Causality.input))
        self.register_variable(Real("warning_ttc", causality=Fmi2Causality.input))
        self.register_variable(Real("brake_ttc", causality=Fmi2Causality.input))
        self.register_variable(Real("emergency_ttc", causality=Fmi2Causality.input))
        self.register_variable(Real("kp_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("kp_brake", causality=Fmi2Causality.input))
        self.register_variable(Real("max_throttle", causality=Fmi2Causality.input))
        self.register_variable(Real("max_brake", causality=Fmi2Causality.input))
        self.register_variable(Real("brake_hold_time", causality=Fmi2Causality.input))
        self.register_variable(Real("hard_brake_distance", causality=Fmi2Causality.input))
        self.register_variable(Real("park_speed_threshold", causality=Fmi2Causality.input))
        self.register_variable(Real("park_hold_delay", causality=Fmi2Causality.input))
        self.register_variable(Real("kp_steer", causality=Fmi2Causality.input))
        self.register_variable(Real("max_steer", causality=Fmi2Causality.input))

        self.register_variable(Real("throttle", causality=Fmi2Causality.output))
        self.register_variable(Real("brake", causality=Fmi2Causality.output))
        self.register_variable(Real("steer", causality=Fmi2Causality.output))
        self.register_variable(Real("deceleration", causality=Fmi2Causality.output))
        self.register_variable(Real("ttc", causality=Fmi2Causality.output))
        self.register_variable(Real("relative_speed", causality=Fmi2Causality.output))
        self.register_variable(Real("safe_distance", causality=Fmi2Causality.output))
        self.register_variable(Real("distance_error", causality=Fmi2Causality.output))
        self.register_variable(Real("aeb_state", causality=Fmi2Causality.output))
        self.register_variable(Real("hand_brake", causality=Fmi2Causality.output))
        self.register_variable(Real("manual_gear_shift", causality=Fmi2Causality.output))
        self.register_variable(Real("gear", causality=Fmi2Causality.output))

    def do_step(self, current_time, step_size):
        self.relative_speed = max(0.0, self.ego_speed - self.lead_speed)
        self.safe_distance = max(self.min_distance, self.ego_speed * 0.35)
        self.distance_error = self.lead_distance - self.safe_distance

        if self.has_lead >= 0.5 and self.relative_speed > 0.1:
            self.ttc = self.lead_distance / self.relative_speed
        else:
            self.ttc = 999.0

        brake_request = 0.0
        state = 0.0
        self.hand_brake = 0.0
        self.manual_gear_shift = 0.0
        self.gear = 1.0

        if self.has_lead >= 0.5:
            if self._hard_brake_condition():
                brake_request = self.max_brake
                state = 3.0
            elif self.ttc <= self.brake_ttc or self.distance_error < 0.0:
                brake_request = self.max_brake
                state = 2.0
            elif self.ttc <= self.warning_ttc:
                brake_request = 0.0
                state = 1.0

        if state >= 2.0:
            if not self._intervened:
                self._intervened = True
                self._hold_until = float(current_time) + max(0.0, self.brake_hold_time)
            elif self.ego_speed > self.park_speed_threshold:
                self._hold_until = max(
                    self._hold_until,
                    float(current_time) + max(0.0, self.brake_hold_time),
                )
        elif float(current_time) < self._hold_until:
            brake_request = max(brake_request, 0.35)
            state = max(state, 2.0)

        if self._intervened and not self._parked:
            # An AEB intervention is terminal for this test: do not resume
            # propulsion when the VRU leaves the TTC projection.
            brake_request = max(brake_request, self.max_brake)
            state = max(state, 3.0)

        if self._should_park_after_intervention(current_time):
            self._parked = True

        if self._parked:
            state = 4.0
            brake_request = 0.0
            self.hand_brake = 1.0
            self.manual_gear_shift = 1.0
            self.gear = 0.0

        self.brake = max(0.0, min(self.max_brake, brake_request))
        if state <= 1.0:
            speed_error = max(0.0, self.target_speed - self.ego_speed)
            self.throttle = max(0.0, min(self.max_throttle, self.kp_speed * speed_error))
        else:
            self.throttle = 0.0
        self.deceleration = self.brake
        self.aeb_state = state

        if self.has_waypoint >= 0.5:
            raw_steer = self.kp_steer * self.heading_error
            self.steer = max(-self.max_steer, min(self.max_steer, raw_steer))
        else:
            self.steer = 0.0

        return True

    def _hard_brake_condition(self):
        if self.has_lead < 0.5:
            return False
        if self.lead_distance <= self.hard_brake_distance:
            return True
        if self.lead_distance <= self.min_distance and self.ttc <= max(self.brake_ttc, self.emergency_ttc):
            return True
        return self.ttc <= self.emergency_ttc

    def _should_park_after_intervention(self, current_time):
        if self._parked:
            return True
        if not self._intervened:
            return False
        if self.ego_speed > self.park_speed_threshold:
            return False
        return float(current_time) >= self._hold_until + max(0.0, self.park_hold_delay)
