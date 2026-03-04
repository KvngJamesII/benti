"""Quick test of the Playwright-based NumberPanel poller – heavy debug."""
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
    print(f"\n{'='*50}")
    print(f"--- Attempt {attempt+1} ---")

    # 1. Navigate to login page
    page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    html = page.content()
    print(f"  Page URL after goto: {page.url}")

    # 2. Dump form HTML for debug
    form_html = page.evaluate("document.querySelector('form') ? document.querySelector('form').outerHTML : 'NO FORM FOUND'")
    print(f"  Form HTML (first 500 chars):\n{form_html[:500]}")

    # 3. Solve captcha
    captcha = solve_math_captcha(html)
    if not captcha:
        print("  No captcha found in HTML!")
        # Try to find the label anyway
        labels = page.query_selector_all("label")
        for lbl in labels:
            print(f"    <label>: {lbl.inner_text()}")
        continue
    print(f"  Captcha answer: {captcha}")

    # 4. Fill fields using page.type() (character by character) instead of page.fill()
    page.evaluate("document.querySelector('input[name=\"username\"]').value = ''")
    page.type('input[name="username"]', username, delay=50)
    page.evaluate("document.querySelector('input[name=\"password\"]').value = ''")
    page.type('input[name="password"]', password, delay=50)
    page.evaluate("document.querySelector('input[name=\"capt\"]').value = ''")
    page.type('input[name="capt"]', str(captcha), delay=50)

    # 5. Verify the values were actually set
    vals = page.evaluate("""() => ({
        u: document.querySelector('input[name="username"]').value,
        p: document.querySelector('input[name="password"]').value,
        c: document.querySelector('input[name="capt"]').value,
        action: document.querySelector('form').action
    })""")
    print(f"  Field values -> user={vals['u']}, pass={'*'*len(vals['p'])}, capt={vals['c']}")
    print(f"  Form action: {vals['action']}")

    # 6. Submit form via JS
    print("  Submitting form via JS...")
    page.evaluate("document.querySelector('form').submit()")
    time.sleep(10)

    # 7. Check result
    current_url = page.url
    print(f"  URL after submit: {current_url}")

    body_text = page.inner_text("body")
    print(f"  Body text (first 300 chars): {body_text[:300]}")

    # Check login by page CONTENT (URL may not update after form.submit())
    body_lower = body_text.lower()
    if "welcome back" in body_lower or "dashboard" in body_lower or "sms module" in body_lower:
        print(f"  Logged in! (dashboard content detected)")
        logged_in = True
        break

    print("  No dashboard content found, retrying...")
    time.sleep(1)
    continue

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
