"""Telegram Bot API delivery.

Renders the digest to Telegram HTML and sends it via sendMessage, splitting into
multiple messages when it exceeds Telegram's per-message limit.
"""

from __future__ import annotations

import logging
import os

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from digest_engine.config import Config
from digest_engine.delivery.base import DeliveryChannel, DeliveryError, register_channel
from digest_engine.models import Digest
from digest_engine.render import render_telegram_html

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = httpx.Timeout(30.0)


def chunk_message(text: str, limit: int) -> list[str]:
    """Split text into <=limit-char chunks, preferring paragraph then line boundaries."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    buf = ""
    for para in text.split("\n\n"):
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) <= limit:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(para) <= limit:
            buf = para
        else:
            # A single paragraph exceeds the limit: hard-split on lines/length.
            for line in para.split("\n"):
                while len(line) > limit:
                    chunks.append(line[:limit])
                    line = line[limit:]
                cand = f"{buf}\n{line}" if buf else line
                if len(cand) <= limit:
                    buf = cand
                else:
                    chunks.append(buf)
                    buf = line
    if buf:
        chunks.append(buf)
    return chunks


@register_channel("telegram")
class TelegramChannel(DeliveryChannel):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.opts = config.delivery.telegram

    def _credentials(self) -> tuple[str, str]:
        token = os.environ.get(self.opts.bot_token_env, "")
        chat_id = os.environ.get(self.opts.chat_id_env, "")
        if not token or not chat_id:
            raise DeliveryError(
                f"missing Telegram credentials: set {self.opts.bot_token_env} "
                f"and {self.opts.chat_id_env}"
            )
        return token, chat_id

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _send(self, client: httpx.Client, token: str, chat_id: str, text: str) -> None:
        resp = client.post(
            _API.format(token=token),
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": self.opts.disable_web_page_preview,
            },
        )
        resp.raise_for_status()

    def deliver(self, digest: Digest) -> None:
        token, chat_id = self._credentials()
        html = render_telegram_html(digest, self.config)
        chunks = chunk_message(html, self.opts.max_message_chars)

        with httpx.Client(timeout=_TIMEOUT) as client:
            for i, chunk in enumerate(chunks, start=1):
                self._send(client, token, chat_id, chunk)
                logger.info("sent Telegram message %d/%d", i, len(chunks))
