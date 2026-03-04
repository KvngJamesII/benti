"""Quick test of the NumberPanel CR-API."""
import httpx
from datetime import datetime, timedelta, timezone
from numberpanel_poller import detect_service

API_URL = "http://147.135.212.197/crapi/st/viewstats"
API_TOKEN = "RlZVRklBUzSAYplnanhsQoRyhWaAdI5mfGyFf2aAlWiAj4BkYGGNSQ=="
MAX_RECORDS = 10

now = datetime.now(timezone.utc)
dt2 = now.strftime("%Y-%m-%d %H:%M:%S")
dt1 = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

print(f"Fetching SMS from {dt1} to {dt2} (max {MAX_RECORDS} records)")
print(f"API: {API_URL}\n")

resp = httpx.get(API_URL, params={
    "token": API_TOKEN,
    "dt1": dt1,
    "dt2": dt2,
    "records": MAX_RECORDS,
}, timeout=30)

print(f"Status: {resp.status_code}")
data = resp.json()

if not isinstance(data, list):
    print(f"Unexpected response: {data}")
    exit(1)

print(f"Total records: {len(data)}\n")

for i, record in enumerate(data):
    if not isinstance(record, list) or len(record) < 4:
        print(f"  [{i+1}] Skipped (invalid format): {record}")
        continue
    service = str(record[0] or "Unknown").strip()
    phone = str(record[1] or "").strip()
    sms = str(record[2] or "").strip().replace("\x00", "")
    date_str = str(record[3] or "").strip()
    detected = detect_service(sms)
    if detected == "Unknown":
        detected = service
    print(f"  [{i+1}] {date_str} | {detected} | {phone} | {sms[:60]}")

print("\nDone!")
