"""
TTC (Time-To-Collision) metric.

This module computes TTC purely from observable signals.
No KPI thresholds, no verdict logic.
"""

class TTCMetric:
    def __init__(self, min_speed_eps=0.1, max_ttc=100.0):
        """
        :param min_speed_eps: minimum relative speed to consider TTC valid
        :param max_ttc: cap TTC to avoid huge numbers
        """
        self.min_speed_eps = min_speed_eps
        self.max_ttc = max_ttc

    def compute(self, signals: dict):
        """
        Expected signals input:
        {
            "distance_to_target": float (meters),
            "ego_speed": float (m/s),
            "target_speed": float (optional, m/s)
        }

        Returns:
            ttc (float) in seconds, or None if invalid
        """
        distance = signals.get("distance_to_target")
        ego_speed = signals.get("ego_speed")
        target_speed = signals.get("target_speed", 0.0)

        if distance is None or ego_speed is None:
            return None

        # relative closing speed
        closing_speed = ego_speed - target_speed

        if closing_speed < self.min_speed_eps:
            return None  # not closing or too small

        ttc = distance / closing_speed

        if ttc < 0:
            return None

        return min(ttc, self.max_ttc)