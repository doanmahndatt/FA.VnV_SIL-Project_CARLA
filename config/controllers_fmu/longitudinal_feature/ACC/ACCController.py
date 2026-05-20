from pythonfmu import Fmi2Causality, Fmi2Slave, Real


class ACCController(Fmi2Slave):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Inputs - keep stable modelDescription.xml names.
        self.ego_speed = 0.0
        self.lead_distance = 100.0
        self.lead_speed = 0.0
        self.target_speed = 20.0
        self.time_gap = 2.0
        self.min_distance = 5.0
        self.heading_error = 0.0
        self.has_lead = 0.0
        self.has_waypoint = 0.0

        # Tunable controller parameters.
        self.kp_speed = 0.35
        self.kp_steer = 1.2
        self.max_throttle = 0.75
        self.max_brake = 0.65
        self.max_steer = 0.6

        # Outputs.
        self.acceleration = 0.0
        self.deceleration = 0.0
        self.jerk = 0.0
        self.throttle = 0.0
        self.brake = 0.0
        self.steer = 0.0
        self.acc_target_speed = 20.0
        self.safe_distance = 5.0
        self.distance_error = 0.0

        self._prev_acceleration = 0.0

        self.register_variable(Real("ego_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("lead_distance", causality=Fmi2Causality.input))
        self.register_variable(Real("lead_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("target_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("time_gap", causality=Fmi2Causality.input))
        self.register_variable(Real("min_distance", causality=Fmi2Causality.input))
        self.register_variable(Real("heading_error", causality=Fmi2Causality.input))
        self.register_variable(Real("has_lead", causality=Fmi2Causality.input))
        self.register_variable(Real("has_waypoint", causality=Fmi2Causality.input))
        self.register_variable(Real("kp_speed", causality=Fmi2Causality.input))
        self.register_variable(Real("kp_steer", causality=Fmi2Causality.input))
        self.register_variable(Real("max_throttle", causality=Fmi2Causality.input))
        self.register_variable(Real("max_brake", causality=Fmi2Causality.input))
        self.register_variable(Real("max_steer", causality=Fmi2Causality.input))

        self.register_variable(Real("acceleration", causality=Fmi2Causality.output))
        self.register_variable(Real("deceleration", causality=Fmi2Causality.output))
        self.register_variable(Real("jerk", causality=Fmi2Causality.output))
        self.register_variable(Real("throttle", causality=Fmi2Causality.output))
        self.register_variable(Real("brake", causality=Fmi2Causality.output))
        self.register_variable(Real("steer", causality=Fmi2Causality.output))
        self.register_variable(Real("acc_target_speed", causality=Fmi2Causality.output))
        self.register_variable(Real("safe_distance", causality=Fmi2Causality.output))
        self.register_variable(Real("distance_error", causality=Fmi2Causality.output))

    def do_step(self, current_time, step_size):
        self.safe_distance = max(self.min_distance, self.ego_speed * self.time_gap)
        self.distance_error = self.lead_distance - self.safe_distance

        if self.has_lead < 0.5 or self.distance_error >= 0.0:
            speed_error = self.target_speed - self.ego_speed
            self.acc_target_speed = self.target_speed
        else:
            self.acc_target_speed = max(
                0.0,
                min(
                    self.target_speed,
                    self.ego_speed - abs(self.distance_error) / max(self.time_gap, 0.1),
                ),
            )
            speed_error = self.acc_target_speed - self.ego_speed

        raw_accel = self.kp_speed * speed_error

        if raw_accel >= 0.0:
            self.acceleration = min(self.max_throttle, raw_accel)
            self.deceleration = 0.0
        else:
            self.acceleration = 0.0
            self.deceleration = min(self.max_brake, abs(raw_accel))

        self.throttle = self.acceleration
        self.brake = self.deceleration
        if self.has_waypoint >= 0.5:
            raw_steer = self.kp_steer * self.heading_error
            self.steer = max(-self.max_steer, min(self.max_steer, raw_steer))
        else:
            self.steer = 0.0

        dt = max(float(step_size), 1e-6)
        self.jerk = (self.acceleration - self._prev_acceleration) / dt
        self._prev_acceleration = self.acceleration

        return True
