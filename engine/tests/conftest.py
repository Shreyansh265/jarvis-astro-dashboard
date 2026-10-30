"""
Test setup. The engine runs on GitHub Actions with the real pyswisseph; tests
exercise pure logic, so a tiny stand-in for `swisseph` is installed when the
real one isn't importable (e.g. on a dev machine without a C++ toolchain).
Network and database access are always replaced per test with monkeypatch --
nothing here talks to Twelve Data or Supabase.
"""
import os
import sys
import types
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test")

try:  # noqa: SIM105
    import swisseph  # noqa: F401
except Exception:
    swe = types.ModuleType("swisseph")
    swe.SUN, swe.MOON, swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER, swe.SATURN, swe.MEAN_NODE = 0, 1, 2, 3, 4, 5, 6, 10
    swe.julday = lambda y, m, d, h: datetime(y, m, d).toordinal() + h / 24.0
    _SPEEDS = {0: 0.98, 1: 13.2, 2: 1.2, 3: 1.1, 4: 0.5, 5: 0.08, 6: 0.03, 10: -0.05}

    def _calc_ut(jd, pid):
        speed = _SPEEDS[pid]
        if pid == 2 and int(jd // 10) % 2 == 0:
            speed = -0.5  # Mercury retrograde every other 10-day block
        return ((pid * 37 + jd * _SPEEDS[pid]) % 360, 0.0, 1.0, speed), 0

    swe.calc_ut = _calc_ut
    sys.modules["swisseph"] = swe
