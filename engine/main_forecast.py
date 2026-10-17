"""
Standalone entry point: refresh the 14-day forecast + sector universe only.
Costs zero Twelve Data credits (pure ephemeris compute), so it's safe to run
any time -- used to populate/inspect the forecast on Actions without waiting
for the ~10-minute main_daily.py (swisseph can't run on the dev machine).
"""
import forecast

if __name__ == "__main__":
    forecast.run_forecast()
