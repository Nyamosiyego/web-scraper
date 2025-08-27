import os
import textwrap
import hashlib
import json
import pathlib
from twilio.rest import Client
from playwright.sync_api import sync_playwright

TARGET_URL = os.environ.get(
    "TARGET_URL", "https://chan.mookh.com/event/chan-2024-finals/"
)
TO_NUMBER = os.environ["TWILIO_TO_NUMBER"]
TWILIO_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = os.environ["TWILIO_WHATSAPP_FROM"]

ALWAYS_SEND = os.environ.get("ALWAYS_SEND", "true").lower() in {"1", "true", "yes"}
MAX_SEGMENT = int(os.environ.get("SMS_SEGMENT_LIMIT", "1400"))
MAX_PARTS = int(os.environ.get("SMS_MAX_PARTS", "6"))


def send_whatsapp(client: Client, text: str, header_prefix: str = ""):
    parts = textwrap.wrap(
        text, width=MAX_SEGMENT, break_long_words=False, replace_whitespace=False
    )
    total = len(parts)
    clipped = False
    if total > MAX_PARTS:
        parts = parts[:MAX_PARTS]
        clipped = True
        total = len(parts)

    for i, chunk in enumerate(parts, start=1):
        prefix = f"{header_prefix} (Part {i}/{total}) " if total > 1 else header_prefix
        body = f"{prefix}{chunk}".strip()
        client.messages.create(
            to="whatsapp:" + TO_NUMBER,
            from_="whatsapp:" + TWILIO_WHATSAPP_FROM,
            body=body,
        )

    if clipped:
        client.messages.create(
            to="whatsapp:" + TO_NUMBER,
            from_="whatsapp:" + TWILIO_WHATSAPP_FROM,
            body="[Truncated: additional content omitted. Increase SMS_MAX_PARTS to receive more.]",
        )


def scrape_text(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            )
        )
        try:
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=90_000)
            page.wait_for_timeout(3000)
            visible_text = page.evaluate("() => document.body.innerText")
            visible_text = "\n".join(
                line.strip() for line in visible_text.splitlines() if line.strip()
            )
            if not visible_text or len(visible_text) < 50:
                visible_text = page.content()
            return visible_text
        finally:
            context.close()
            browser.close()


def main():
    sms_client = Client(TWILIO_SID, TWILIO_TOKEN)
    page_text = scrape_text(TARGET_URL)

    if ALWAYS_SEND:
        send_whatsapp(sms_client, page_text, header_prefix="CHAN Finals page:")
        return

    digest = hashlib.sha256(page_text.encode("utf-8")).hexdigest()
    state_path = pathlib.Path(".state/state.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    old = {}
    if state_path.exists():
        try:
            old = json.loads(state_path.read_text())
        except Exception:
            old = {}
    if old.get("digest") != digest:
        send_whatsapp(sms_client, page_text, header_prefix="CHAN Finals page changed:")
        state_path.write_text(json.dumps({"digest": digest}))


if __name__ == "__main__":
    main()
