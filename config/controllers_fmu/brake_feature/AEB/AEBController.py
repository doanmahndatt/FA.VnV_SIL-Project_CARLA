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
        self.min_distance = 6.0
        self.warning_ttc = 2.5
        self.brake_ttc = 1.5
        self.emergency_ttc = 0.8
        self.kp_speed = 0.35
        self.kp_brake = 0.45
        self.max_throttle = 0.75
        self.max_brake = 1.0
        self.brake_hold_time = 0.5
        self.kp_steer = 1.2
        self.max_steer = 0.6

        # Outputs.
        self.throttle = 0.0
        self.brake = 0.0
        self.steer = 0.0
        self.deceleration = 0.0
        self.ttc = 999.0
        self.relative_speed = 0.0
        self.safe_distance = 6.0
        self.distance_error = 0.0
        self.aeb_state = 0.0

        self._hold_until = 0.0

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

        if self.has_lead >= 0.5:
            if self.lead_distance <= self.min_distance or self.ttc <= self.emergency_ttc:
                brake_request = self.max_brake
                state = 3.0
            elif self.ttc <= self.brake_ttc or self.distance_error < 0.0:
                ttc_error = max(0.0, self.brake_ttc - self.ttc)
                distance_error = max(0.0, -self.distance_error)
                brake_request = 0.45 + self.kp_brake * ttc_error + 0.03 * distance_error
                state = 2.0
            elif self.ttc <= self.warning_ttc:
                brake_request = 0.15
                state = 1.0

        if state >= 2.0:
            self._hold_until = max(
                self._hold_until,
                float(current_time) + max(0.0, self.brake_hold_time),
            )
        elif float(current_time) < self._hold_until:
            brake_request = max(brake_request, 0.35)
            state = max(state, 2.0)

        self.brake = max(0.0, min(self.max_brake, brake_request))
        if state == 0.0:
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
