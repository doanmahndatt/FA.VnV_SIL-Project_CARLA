from pythonfmu import Fmi2Causality, Fmi2Slave, Real


class ACCController(Fmi2Slave):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Inputs - keep stable modelDescription.xml names.
        self.ego_speed = 0.0
        self.lead_distance = 100.0
        self.lead_speed = 0.0
        self.target_speed = 20.0
        self.time_gap = 2.2
        self.min_distance = 8.0
        self.heading_error = 0.0
        self.has_lead = 0.0
        self.has_waypoint = 0.0

        # Tunable controller parameters.
        self.kp_speed = 0.20
        self.kp_steer = 1.2
        self.max_throttle = 0.75
        self.max_brake = 0.45
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
        self._prev_target_speed = 0.0
        self._prev_safe_distance = 0.0
        self._lead_was_present = False
        self._prev_throttle = 0.0
        self._prev_brake = 0.0

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
        has_lead = self.has_lead >= 0.5
        self.safe_distance = self._smooth_safe_distance(has_lead, step_size)
        self.distance_error = self.lead_distance - self.safe_distance
        effective_error = self._distance_error_with_deadband(self.distance_error)

        if not has_lead:
            raw_target_speed = self.target_speed
        else:
            raw_target_speed = self._follow_target_speed(effective_error)

        self.acc_target_speed = self._rate_limited_target_speed(raw_target_speed, step_size, has_lead)
        speed_error = self.acc_target_speed - self.ego_speed

        effective_kp_speed = self._effective_kp_speed(has_lead)
        raw_accel = effective_kp_speed * speed_error

        raw_throttle, raw_brake = self._raw_longitudinal_outputs(raw_accel, has_lead)
        self.throttle, self.brake = self._smooth_longitudinal_outputs(
            raw_throttle,
            raw_brake,
            step_size,
        )
        self.acceleration = self.throttle
        self.deceleration = self.brake
        if self.has_waypoint >= 0.5:
            raw_steer = self.kp_steer * self.heading_error
            self.steer = max(-self.max_steer, min(self.max_steer, raw_steer))
        else:
            self.steer = 0.0

        dt = max(float(step_size), 1e-6)
        signed_acceleration_cmd = self.throttle - self.brake
        self.jerk = (signed_acceleration_cmd - self._prev_acceleration) / dt
        self._prev_acceleration = signed_acceleration_cmd
        self._lead_was_present = has_lead

        return True

    def _smooth_safe_distance(self, has_lead, step_size):
        desired_safe_distance = max(self.min_distance, self.ego_speed * self.time_gap)
        if not has_lead:
            self._prev_safe_distance = desired_safe_distance
            return desired_safe_distance

        if not self._lead_was_present or self._prev_safe_distance <= 0.0:
            self._prev_safe_distance = min(
                desired_safe_distance,
                max(0.0, self.lead_distance),
            )
            return self._prev_safe_distance

        max_delta = 1.0 * max(float(step_size), 1e-6)
        self._prev_safe_distance = max(
            self._prev_safe_distance - max_delta,
            min(self._prev_safe_distance + max_delta, desired_safe_distance),
        )
        return self._prev_safe_distance

    def _distance_error_with_deadband(self, distance_error):
        deadband = 1.5
        if abs(distance_error) < deadband:
            return 0.0
        if distance_error > 0.0:
            return distance_error - deadband
        return distance_error + deadband

    def _follow_target_speed(self, effective_error):
        relative_speed = self.lead_speed - self.ego_speed
        settle_time = max(6.0, self.time_gap * 3.0)
        gap_correction = effective_error / settle_time
        closing_correction = min(0.0, relative_speed) * 0.35
        raw_target_speed = self.lead_speed + gap_correction + closing_correction

        comfort_floor = max(0.0, self.lead_speed - 1.2)
        if self.lead_distance >= max(3.0, self.min_distance * 0.75):
            raw_target_speed = max(comfort_floor, raw_target_speed)

        return max(0.0, min(self.target_speed, raw_target_speed))

    def _rate_limited_target_speed(self, raw_target_speed, step_size, has_lead):
        if self._prev_target_speed <= 0.0:
            self._prev_target_speed = min(self.target_speed, max(self.ego_speed, raw_target_speed))

        rate = 0.8 if has_lead else 1.5
        max_delta = rate * max(float(step_size), 1e-6)
        limited_target = max(
            self._prev_target_speed - max_delta,
            min(self._prev_target_speed + max_delta, raw_target_speed),
        )
        self._prev_target_speed = limited_target
        return limited_target

    def _effective_kp_speed(self, has_lead):
        if has_lead:
            return max(0.08, min(0.14, self.kp_speed))
        return max(0.08, min(0.20, self.kp_speed))

    def _raw_longitudinal_outputs(self, raw_accel, has_lead):
        deadzone = 0.03
        if raw_accel > deadzone:
            if has_lead and self.distance_error < 0.5:
                return 0.0, 0.0
            return min(self.max_throttle, raw_accel), 0.0
        if raw_accel < -deadzone:
            if has_lead and self._should_coast_in_follow():
                return 0.0, 0.0
            follow_brake_cap = 0.22 if self.lead_distance >= self.min_distance else 0.35
            brake_cap = min(self.max_brake, follow_brake_cap) if has_lead else self.max_brake
            return 0.0, min(brake_cap, abs(raw_accel))
        return 0.0, 0.0

    def _should_coast_in_follow(self):
        relative_speed = self.lead_speed - self.ego_speed
        if self.lead_distance < max(4.0, self.min_distance * 0.65):
            return False
        if self.distance_error < -3.0:
            return False
        return relative_speed > -0.8

    def _smooth_longitudinal_outputs(self, raw_throttle, raw_brake, step_size):
        dt = max(float(step_size), 1e-6)
        throttle = self._rate_limit(self._prev_throttle, raw_throttle, 0.8 * dt, 1.2 * dt)
        brake = self._rate_limit(self._prev_brake, raw_brake, 0.35 * dt, 0.75 * dt)

        if brake > 0.01:
            throttle = 0.0
        elif throttle > 0.01:
            brake = 0.0

        self._prev_throttle = throttle
        self._prev_brake = brake
        return throttle, brake

    @staticmethod
    def _rate_limit(previous, target, max_decrease, max_increase):
        if target > previous:
            return min(previous + max_increase, target)
        return max(previous - max_decrease, target)
