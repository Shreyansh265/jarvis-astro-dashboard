"""
Computes real planetary positions (tropical zodiac, geocentric) for any date
using the Swiss Ephemeris (pyswisseph) -- the same astronomical engine used
by professional astrology software. No API key needed; fully offline/free.
"""
import swisseph as swe
from datetime import datetime, timezone
from rulerships import SIGNS

PLANET_IDS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY,
    "Venus": swe.VENUS, "Mars": swe.MARS, "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE,  # Ketu = Rahu + 180
}


def _sign_for_longitude(lon: float) -> str:
    return SIGNS[int(lon // 30) % 12]


def get_positions(date: datetime) -> dict:
    """
    Returns a dict per planet with: longitude, sign, degree-in-sign,
    is_retrograde, speed.
    """
    jd = swe.julday(date.year, date.month, date.day,
                     date.hour + date.minute / 60.0)
    positions = {}
    for name, pid in PLANET_IDS.items():
        result, _ = swe.calc_ut(jd, pid)
        lon, lat, dist, speed_lon = result[0], result[1], result[2], result[3]
        positions[name] = {
            "longitude": round(lon, 4),
            "sign": _sign_for_longitude(lon),
            "degree_in_sign": round(lon % 30, 2),
            "is_retrograde": speed_lon < 0,
            "speed": round(speed_lon, 4),
        }
    # Ketu is always exactly opposite Rahu (mean south lunar node)
    rahu_lon = positions["Rahu"]["longitude"]
    ketu_lon = (rahu_lon + 180) % 360
    positions["Ketu"] = {
        "longitude": round(ketu_lon, 4),
        "sign": _sign_for_longitude(ketu_lon),
        "degree_in_sign": round(ketu_lon % 30, 2),
        "is_retrograde": True,  # nodes are always retrograde by convention
        "speed": positions["Rahu"]["speed"],
    }
    return positions


def get_aspects(positions: dict, orb: float = 6.0) -> list:
    """Finds all planet-pair aspects (conjunction/square/trine/opposition) within orb."""
    from rulerships import ASPECTS
    names = list(positions.keys())
    aspects = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            p1, p2 = names[i], names[j]
            diff = abs(positions[p1]["longitude"] - positions[p2]["longitude"])
            diff = min(diff, 360 - diff)
            for angle, meta in ASPECTS.items():
                if abs(diff - angle) <= orb:
                    aspects.append({
                        "planet1": p1, "planet2": p2,
                        "aspect": meta["name"], "tone": meta["tone"],
                        "exact_diff": round(diff, 2),
                    })
    return aspects


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    pos = get_positions(now)
    for planet, data in pos.items():
        print(f"{planet:8s} {data['sign']:12s} {data['degree_in_sign']:5.2f}° "
              f"{'(R)' if data['is_retrograde'] else '   '}")
    print("\nAspects:")
    for a in get_aspects(pos):
        print(a)
