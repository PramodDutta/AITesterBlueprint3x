"""Client for Subsystem A - the ShopSphere chatbot (the app under test).

The framework never imports the chatbot's code. It talks to the running
service over HTTP, exactly as a real user would, so what we score is the
deployed behaviour and not a unit-tested internal function.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

from token_meter import METER

load_dotenv()

CHATBOT_URL = os.getenv("CHATBOT_URL", "http://localhost:8201").rstrip("/")
TIMEOUT = float(os.getenv("CHATBOT_TIMEOUT", "60"))
# # curl --url 'https://www.google-analytics.com/g/collect?v=2&tid=G-NHVZN3FRCB&gtm=45je6921v9255463193za200zd9255463193&_p=1788678607861&gcd=13l3l3l3l1l1&npa=0&dma=0&_eu=AAAAAAQ&are=1&cid=254960942.1781532683&frm=0&ngs=1&pscdl=noapi&rcb=5&sr=1920x1080&uaa=arm&uab=64&uafvl=Not%253DA%253FBrand%3B99.0.0.0%7CGoogle%2520Chrome%3B151.0.7922.76%7CChromium%3B151.0.7922.76&uam=&uamb=0&uap=macOS&uapv=26.1.0&uaw=0&ul=en-in&_s=2&tag_exp=115616986~115938465~115938469~118897920~118897930~120213116~120385423~120469145~120469153&dp=%2F&sid=1788678607&sct=54&seg=0&dl=https%3A%2F%2Fbrowserbash.com%2F&dt=BrowserBash%20%E2%80%94%20free%2C%20open-source%20plain-English%20browser%20automation%20CLI&en=click&_ee=1&ep.link_text=Open%20chat&ep.link_url=&_et=813&tfd=13176' \
#   -X 'POST' \
#   -H 'sec-ch-ua-platform: "macOS"' \
#   -H 'Referer: https://browserbash.com/' \
#   -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36' \
#   -H 'sec-ch-ua: "Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"' \
#   -H 'DNT: 1' \
#   -H 'sec-ch-ua-mobile: ?0' ;
# curl --url 'https://aleeup.com/api/bots/NqLIxxNfaoPeChEFeF8nj/chat' \
#   -H 'sec-ch-ua-platform: "macOS"' \
#   -H 'Referer: https://aleeup.com/widget/NqLIxxNfaoPeChEFeF8nj' \
#   -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36' \
#   -H 'sec-ch-ua: "Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"' \
#   -H 'DNT: 1' \
#   -H 'Content-Type: application/json' \
#   -H 'sec-ch-ua-mobile: ?0' \
#   --data-raw '{"message":"dadad","visitorId":"9fpgpcjl2di"}'

@dataclass
class ChatReply:
    reply: str
    model: str
    mode: str


class ChatbotClient:
    def __init__(self, base_url: str = CHATBOT_URL):
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict:
        r = requests.get(f"{self.base_url}/health", timeout=10)
        r.raise_for_status()
        return r.json()

    def is_up(self) -> bool:
        try:
            return self.health().get("status") == "ok"
        except Exception:  # noqa: BLE001 - any failure means "not usable"
            return False

    def chat(self, message: str, history: list[dict] | None = None) -> ChatReply:
        payload: dict = {"message": message}
        if history:
            payload["history"] = history
        r = requests.post(f"{self.base_url}/chat", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage")
        if usage:
            METER.record("target",
                         usage.get("prompt_tokens", 0),
                         usage.get("completion_tokens", 0))
        return ChatReply(
            reply=data.get("reply") or "",
            model=data.get("model", "unknown"),
            mode=data.get("mode", "unknown"),
        )
