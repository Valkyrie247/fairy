"""Shared protocol helpers for the UDP Tic-Tac-Toe project."""

import json
import random
import time
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


def encode(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


def decode(data: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(data.decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


class NetworkExperiment:
    """Optional artificial loss and delay for demonstrations."""

    def __init__(self, loss: float = 0.0, delay_ms: int = 0):
        self.loss = max(0.0, min(1.0, loss))
        self.delay_ms = max(0, delay_ms)

    def drop(self) -> bool:
        return random.random() < self.loss

    def delay(self) -> None:
        if self.delay_ms:
            time.sleep(random.uniform(0, self.delay_ms) / 1000)
