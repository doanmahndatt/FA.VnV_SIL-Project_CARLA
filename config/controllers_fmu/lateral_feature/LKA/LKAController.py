from pythonfmu import Fmi2Causality, Fmi2Slave, Real


class LKAController(Fmi2Slave):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Inputs - keep stable modelDescription.xml names.
        self.ego_speed = 0.0
        self.target_speed = 15.0
        self.lane_offset = 0.0
        self.heading_error = 0.0
        self.has_lane = 0.0

        # Tunable controller parameters.
        self.activation_offset = 0.25
        self.deadband_offset = 0.05
        self.kp_offset = 0.22
        self.kp_heading = 0.85
        self.kp_speed = 0.25
        self.max_steer = 0.45
        self.max_throttle = 0.45
        self.max_brake = 0.25

        # Outputs.
        self.throttle = 0.0
        self.brake = 0.0
        self.steer = 0.0
        self.corrected_offset = 0.0
        self.lka_state = 0.0

        self.register_variable(Real("ego_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("target_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("lane_offset", causality=Fmi2Causality.input))
        self.register_variable(Real("heading_error", causality=Fmi2Causality.input))
        self.register_variable(Real("has_lane", causality=Fmi2Causality.input))
        self.register_variable(Real("activation_offset", causality=Fmi2Causality.input))
        self.register_variable(Real("deadband_offset", causality=Fmi2Causality.input))
        self.register_variable(Real("kp_offset", causality=Fmi2Causality.input))
        self.register_variable(Real("kp_heading", causality=Fmi2Causality.input))
        self.register_variable(Real("kp_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("max_steer", causality=Fmi2Causality.input))
        self.register_variable(Real("max_throttle", causality=Fmi2Causality.input))
        self.register_variable(Real("max_brake", causality=Fmi2Causality.input))

        self.register_variable(Real("throttle", causality=Fmi2Causality.output))
        self.register_variable(Real("brake", causality=Fmi2Causality.output))
        self.register_variable(Real("steer", causality=Fmi2Causality.output))
        self.register_variable(Real("corrected_offset", causality=Fmi2Causality.output))
        self.register_variable(Real("lka_state", causality=Fmi2Causality.output))

    def do_step(self, current_time, step_size):
        speed_error = self.target_speed - self.ego_speed
        if speed_error >= 0.0:
            self.throttle = min(self.max_throttle, self.kp_speed * speed_error)
            self.brake = 0.0
        else:
            self.throttle = 0.0
            self.brake = min(self.max_brake, abs(self.kp_speed * speed_error))

        lane_available = self.has_lane >= 0.5
        offset_abs = abs(self.lane_offset)
        active = lane_available and offset_abs >= self.activation_offset

        if not lane_available:
            self.steer = 0.0
            self.corrected_offset = self.lane_offset
            self.lka_state = 0.0
            return True

        if offset_abs <= self.deadband_offset:
            offset_term = 0.0
        else:
            offset_term = self.lane_offset

        raw_steer = -self.kp_offset * offset_term - self.kp_heading * self.heading_error
        self.steer = max(-self.max_steer, min(self.max_steer, raw_steer))
        self.corrected_offset = offset_term
        self.lka_state = 1.0 if active else 0.0

        return True
