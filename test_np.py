# -*- coding: utf-8 -*-
"""
Standalone test for NumberPanel poller – no Flask/DB needed.
Just logs in, fetches SMS, and prints to console.
"""

import re
import time
import httpx
from bs4 import BeautifulSoup


NP_LOGIN_URL = "http://51.89.99.105/NumberPanel/login"
NP_SIGNIN_URL = "http://51.89.99.105/NumberPanel/signin"
NP_SMS_URL = "http://51.89.99.105/NumberPanel/agent/SMSCDRReports"
NP_USERNAME = "steadycashout"
NP_PASSWORD = "Godswill"


def solve_math_captcha(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for label in soup.find_all("label"):
        text = label.get_text()
        if "what is" in text.lower():
            match = re.search(r"(\d+)\s*\+\s*(\d+)", text)
            if match:
                a, b = int(match.group(1)), int(match.group(2))
                print(f"  [Captcha] {a} + {b} = {a + b}")
                return str(a + b)
            match = re.search(r"(\d+)\s*-\s*(\d+)", text)
            if match:
                a, b = int(match.group(1)), int(match.group(2))
                print(f"  [Captcha] {a} - {b} = {a - b}")
                return str(a - b)
            match = re.search(r"(\d+)\s*[x\xd7\*]\s*(\d+)", text)
            if match:
                a, b = int(match.group(1)), int(match.group(2))
                print(f"  [Captcha] {a} * {b} = {a * b}")
                return str(a * b)
    return None


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def make_client():
    return httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        verify=False,
    )


def login(client: httpx.Client) -> bool:
    page = client.get(NP_LOGIN_URL)
    captcha = solve_math_captcha(page.text)
    if not captcha:
        print("  No captcha found")
        return False

    data = {"username": NP_USERNAME, "password": NP_PASSWORD, "capt": captcha}
    resp = client.post(NP_SIGNIN_URL, data=data)
    final_url = str(resp.url)

    if "login" in final_url.split("/")[-1].lower():
        return False

    print(f"  Logged in! -> {final_url}")
    return True


def fetch_sms(client: httpx.Client):
    print(f"\nFetching SMS reports...")
    resp = client.get(NP_SMS_URL)
    final_url = str(resp.url)

    if "login" in final_url.lower().split("/")[-1]:
        print("  Session lost - redirected to login")
        return

    # Extract sAjaxSource from DataTable init
    match = re.search(r'"sAjaxSource"\s*:\s*"([^"]+)"', resp.text)
    if not match:
        print("  No sAjaxSource found in page")
        return

    ajax_path = match.group(1)
    ajax_url = f"http://51.89.99.105/NumberPanel/agent/{ajax_path}"
    print(f"  AJAX URL: {ajax_url[:120]}...")

    # Fetch SMS data
    r = client.get(ajax_url, headers={
        "Referer": NP_SMS_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })

    if r.status_code != 200:
        print(f"  AJAX error: {r.status_code} - {r.text[:300]}")
        return

    try:
        data = r.json()
    except Exception as e:
        print(f"  Not JSON: {e} - {r.text[:500]}")
        return

    total = data.get("iTotalRecords", "?")
    rows = data.get("aaData", [])
    print(f"  Total: {total}, Rows: {len(rows)}")

    print(f"\n{'='*80}")
    print(f"  SMS MESSAGES ({len(rows)} rows)")
    print(f"{'='*80}")

    for i, row in enumerate(rows):
        if isinstance(row, list) and len(row) >= 6:
            date = strip_html(str(row[0])).strip()
            country = strip_html(str(row[1])).strip()
            number = strip_html(str(row[2])).strip()
            cli = strip_html(str(row[3])).strip()
            client_name = strip_html(str(row[4])).strip()
            sms = strip_html(str(row[5])).strip().replace("\x00", "")

            print(f"\n  [{i+1}] Date: {date}")
            print(f"      Country: {country}")
            print(f"      Number: {number}")
            print(f"      CLI/Source: {cli}")
            print(f"      Client: {client_name}")
            print(f"      SMS: {sms}")
            print(f"      {'-'*60}")


if __name__ == "__main__":
    print("=" * 50)
    print("  NumberPanel Poller Test")
    print("=" * 50)

    for attempt in range(10):
        print(f"\n--- Attempt {attempt + 1} ---")
        client = make_client()
        try:
            if login(client):
                fetch_sms(client)
                client.close()
                break
            else:
                print(f"  Login failed, retrying...")
                client.close()
                time.sleep(2)
        except Exception as e:
            print(f"  Error: {e}")
            client.close()
            time.sleep(2)
    else:
        print("\nFailed after 10 attempts.")

    print("\n" + "=" * 50)
    print("  Done")
    print("=" * 50)
