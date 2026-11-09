"""Надсилання в Telegram (Bot API, безкоштовно)."""
from __future__ import annotations

import html
import logging
import time

import requests

log = logging.getLogger(__name__)


class Telegram:
    def __init__(self, token: str | None, chat_id: str | None, dry_run: bool = False):
        self.token = token
        self.chat_id = chat_id
        self.dry_run = dry_run or not (token and chat_id)
        self.sent = 0

    def call(self, method: str, payload: dict, with_chat: bool = True) -> dict:
        """Будь-який метод Bot API. with_chat=False — для методів без chat_id (getUpdates, setMyCommands…)."""
        return self._call(method, payload, with_chat)

    def _call(self, method: str, payload: dict, with_chat: bool = True) -> dict:
        if self.dry_run:
            log.info("[dry-run] %s %s", method, {k: v for k, v in payload.items() if k != "chat_id"})
            return {"ok": True}
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        body = {"chat_id": self.chat_id, **payload} if with_chat else payload
        for attempt in range(4):
            r = requests.post(url, json=body, timeout=30)
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 429:
                time.sleep(int(j.get("parameters", {}).get("retry_after", 5)) + 1)
                continue
            if not j.get("ok"):
                raise RuntimeError(f"Telegram {method}: {r.status_code} {j.get('description') or r.text[:200]}")
            time.sleep(1.1)  # ліміт Telegram: ~1 повідомлення/с у чат
            self.sent += 1
            return j
        raise RuntimeError(f"Telegram {method}: 429 після повторів")

    def text(self, text: str) -> None:
        self._call("sendMessage", {"text": text, "parse_mode": "HTML", "disable_web_page_preview": True})

    def listing(self, caption: str, photos: list[str], url: str) -> None:
        """Один товар — одне повідомлення. 1 фото: sendPhoto з кнопкою; кілька: альбом (кнопок у альбомів немає,
        тому посилання є в підписі)."""
        keyboard = {"inline_keyboard": [[{"text": "Відкрити на Shafa", "url": url}]]}
        try:
            if len(photos) > 1:
                media = [{"type": "photo", "media": p} for p in photos[:10]]
                media[0].update({"caption": caption, "parse_mode": "HTML"})
                self._call("sendMediaGroup", {"media": media})
            elif photos:
                self._call("sendPhoto", {"photo": photos[0], "caption": caption, "parse_mode": "HTML",
                                         "reply_markup": keyboard})
            else:
                self._call("sendMessage", {"text": caption, "parse_mode": "HTML", "reply_markup": keyboard})
        except RuntimeError as e:
            # Якщо Telegram не зміг завантажити фото — шлемо хоча б текст.
            log.warning("фото не надіслано (%s), шлю текстом", e)
            self._call("sendMessage", {"text": caption, "parse_mode": "HTML", "reply_markup": keyboard})


def esc(s) -> str:
    return html.escape(str(s or ""), quote=False)
