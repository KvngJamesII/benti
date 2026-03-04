"""Quick test of the Playwright-based NumberPanel poller."""
import re, time
from playwright.sync_api import sync_playwright
from numberpanel_poller import solve_math_captcha, _strip_html

login_url = "http://51.89.99.105/NumberPanel/login"
sms_url = "http://51.89.99.105/NumberPanel/agent/SMSCDRReports"
username = "steadycashout"
password = "Godswill"

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
page = browser.new_page()

logged_in = False
for attempt in range(5):
    print(f"--- Attempt {attempt+1} ---")
    page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
    html = page.content()
    captcha = solve_math_captcha(html)
    if not captcha:
        print("  No captcha found")
        continue
    print(f"  Captcha answer: {captcha}")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.fill('input[name="capt"]', captcha)

    # Submit form via JS (more reliable than Enter key)
    page.evaluate("document.querySelector('form').submit()")
    time.sleep(10)  # let server process and redirect

    current_url = page.url.lower()
    print(f"  Current URL: {page.url}")
    
    # Check for error messages on the page
    body_text = page.inner_text("body")
    if "invalid" in body_text.lower() or "wrong" in body_text.lower() or "error" in body_text.lower():
        # Find the error message
        for line in body_text.split("\n"):
            line = line.strip()
            if line and ("invalid" in line.lower() or "wrong" in line.lower() or "error" in line.lower() or "incorrect" in line.lower()):
                print(f"  Error on page: {line[:100]}")
                break
    
    current_url = page.url.lower()
    current_url = page.url.lower()
    print(f"  Current URL: {page.url}")
    if "/login" in current_url.split("?")[0]:
        print("  Still on login page, retrying...")
        time.sleep(1)
        continue
    print(f"  Logged in! -> {page.url}")
    logged_in = True
    break

if not logged_in:
    print("FAILED to login after 5 attempts")
    browser.close()
    pw.stop()
    exit(1)

# Intercept AJAX response
ajax_data = {}

def on_resp(response):
    try:
        if "data_smscdr" in response.url or "sesskey" in response.url:
            if response.status == 200:
                try:
                    ajax_data["json"] = response.json()
                except Exception:
                    pass
    except Exception:
        pass

page.on("response", on_resp)
print(f"\nNavigating to SMS reports: {sms_url}")
page.goto(sms_url, wait_until="domcontentloaded", timeout=60000)
page.wait_for_timeout(5000)
page.remove_listener("response", on_resp)

rows = []
if "json" in ajax_data:
    print("Got AJAX data via interception!")
    rows = ajax_data["json"].get("aaData") or ajax_data["json"].get("data") or []
else:
    print("No intercepted AJAX, trying fallback...")
    html2 = page.content()
    m = re.search(r'"sAjaxSource"\s*:\s*"([^"]+)"', html2)
    if m:
        ajax_path = m.group(1)
        base = sms_url.rsplit("/", 1)[0]
        ajax_url = f"{base}/{ajax_path}"
        print(f"  Fetching: {ajax_url}")
        resp = page.evaluate(
            """async (url) => {
                const r = await fetch(url, {
                    headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
                });
                return await r.json();
            }""",
            ajax_url,
        )
        rows = resp.get("aaData") or resp.get("data") or []
    else:
        print("  No sAjaxSource found in page!")

count = 0
for row in rows:
    if not isinstance(row, list) or len(row) < 6:
        continue
    d = _strip_html(str(row[0])).strip()
    if "," in d or "NAN" in d.upper() or "%" in d:
        continue
    count += 1
    if count <= 3:
        sms = _strip_html(str(row[5])).strip()
        num = _strip_html(str(row[2])).strip()
        print(f"  [{count}] {num} -> {sms[:60]}")

print(f"\nTotal SMS fetched: {count}")

browser.close()
pw.stop()
print("Done!")
