"""
Standalone entry point: refresh the 21-day forecast + sector universe.
Costs zero Twelve Data credits (pure ephemeris compute), so it's safe to run
any time -- used to populate/inspect the forecast on Actions without waiting
for the ~10-minute main_daily.py (swisseph can't run on the dev machine).
Set WITH_ANALOGS=1 to also refresh the "it happened before" analog cache
(~2 credits per new analog, 8s apart).
"""
import os
import forecast

if __name__ == "__main__":
    forecast.run_forecast()
    import company_chart
    company_chart.sync_company_charts()   # no-op (loudly) until schema v2 is applied
    if os.environ.get("WITH_ANALOGS") == "1":
        import analogs
        print(f"analogs refreshed: {analogs.refresh_analogs()}")
