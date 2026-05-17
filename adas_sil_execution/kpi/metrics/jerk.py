"""
Jerk metric.

Computes longitudinal jerk from acceleration signal.
Stateful metric (depends on previous sample).
"""

class JerkMetric:
    def __init__(self):
        self.last_acc = None
        self.last_ts = None

    def reset(self):
        self.last_acc = None
        self.last_ts = None

    def compute(self, timestamp: float, signals: dict):
        """
        Expected inputs:
        - timestamp: float (seconds)
        - signals:
            {
                "longitudinal_acc": float (m/s^2)
            }

        Returns:
            jerk (float) in m/s^3, or None if invalid
        """
        acc = signals.get("longitudinal_acc")

        if acc is None:
            return None

        if self.last_acc is None or self.last_ts is None:
            self.last_acc = acc
            self.last_ts = timestamp
            return None

        dt = timestamp - self.last_ts
        if dt <= 0:
            return None

        jerk = (acc - self.last_acc) / dt

        self.last_acc = acc
        self.last_ts = timestamp

        return jerk