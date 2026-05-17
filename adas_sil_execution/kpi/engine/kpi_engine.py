from kpi.metrics.ttc import TTCMetric
from kpi.metrics.jerk import JerkMetric


class KPIEngine:
    """
    KPI evaluation engine.
    - Receives samples from collectors
    - Computes derived metrics via metric modules
    - Evaluates KPI verdict via profile (NO metric math here)
    """

    def __init__(self, kpi_profile: dict):
        self.profile = kpi_profile

        # metric plugins
        self.ttc_metric = TTCMetric()
        self.jerk_metric = JerkMetric()

        # history
        self.samples = []
        self.timeline = []

        # extrema
        self.min_distance = float("inf")
        self.min_ttc = float("inf")
        self.max_jerk = 0.0

        self.violations = []

    # ---------------------------------------------
    # Ingest data
    # ---------------------------------------------
    def push_sample(self, sample: dict):
        """
        sample:
        {
            "timestamp": float,
            "signals": {
                "ego_speed": float,
                "distance_to_target": float,
                "collision": bool,
                "acc_cmd": float
            }
        }
        """
        self.samples.append(sample)
        self._process_sample(sample)

    # ---------------------------------------------
    # Core processing
    # ---------------------------------------------
    def _process_sample(self, sample):
        ts = sample["timestamp"]
        sig = sample["signals"]

        # --- raw signals ---
        dist = sig.get("distance_to_target")
        if dist is not None:
            self.min_distance = min(self.min_distance, dist)

        # --- metrics ---
        ttc = self.ttc_metric.compute(sig)
        if ttc is not None:
            self.min_ttc = min(self.min_ttc, ttc)

        jerk = self.jerk_metric.compute(ts, {
            "longitudinal_acc": sig.get("acc_cmd")
        })
        if jerk is not None:
            self.max_jerk = max(self.max_jerk, abs(jerk))

        # --- timeline logging ---
        self.timeline.append({
            "timestamp": ts,
            "distance": dist,
            "ttc": ttc,
            "jerk": jerk,
            "ego_speed": sig.get("ego_speed"),
            "collision": sig.get("collision", False)
        })

        # --- verdict rules ---
        self._check_violations(ts, sig, ttc, jerk)

    # ---------------------------------------------
    # KPI rules (policy, not math)
    # ---------------------------------------------
    def _check_violations(self, ts, sig, ttc, jerk):
        th = self.profile["thresholds"]

        if sig.get("collision"):
            self._violate("COLLISION", "Collision detected", ts)

        if ttc is not None and ttc < th["min_ttc_s"]:
            self._violate(
                "TTC",
                f"TTC below threshold: {ttc:.2f}s",
                ts
            )

        if jerk is not None and abs(jerk) > th.get("max_jerk_mps3", float("inf")):
            self._violate(
                "JERK",
                f"Jerk too high: {jerk:.2f} m/s^3",
                ts
            )

    def _violate(self, vtype, msg, ts):
        self.violations.append({
            "type": vtype,
            "message": msg,
            "timestamp": ts
        })

    # ---------------------------------------------
    # Result
    # ---------------------------------------------
    def verdict(self):
        if any(v["type"] == "COLLISION" for v in self.violations):
            return "FAIL_COLLISION"
        if self.violations:
            return "FAIL_KPI"
        return "PASS"

    def summary(self):
        return {
            "verdict": self.verdict(),
            "min_distance": self.min_distance,
            "min_ttc": self.min_ttc,
            "max_jerk": self.max_jerk,
            "violations": self.violations
        }

    def get_timeline(self):
        return self.timeline