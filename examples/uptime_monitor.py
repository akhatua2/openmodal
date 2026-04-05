"""Uptime Monitor -- pings https://arpandeep.com/ every minute.

    openmodal deploy examples/uptime_monitor.py
    openmodal ps
    openmodal logs uptime-monitor
    openmodal stop uptime-monitor
"""

import openmodal

app = openmodal.App("uptime-monitor")

image = openmodal.Image.debian_slim().pip_install("requests")


@app.function(
    image=image,
    schedule=openmodal.Cron("* * * * *"),
    timeout=30,
    retries=2,
)
def check_uptime():
    import requests

    url = "https://arpandeep.com/"
    try:
        resp = requests.get(url, timeout=10)
        print(f"[OK] {url} responded {resp.status_code} in {resp.elapsed.total_seconds():.2f}s")
    except requests.RequestException as e:
        print(f"[FAIL] {url} error: {e}")
        raise  # let retries handle transient failures
