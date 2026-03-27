from __future__ import annotations

import time

from bot.logs.logger import get_logger
from bot.runtime.service import TradingService


class BotRunner:
    def __init__(self, service: TradingService, poll_seconds: int):
        self.service = service
        self.poll_seconds = max(1, poll_seconds)
        self.logger = get_logger("bot.runtime.runner")

    def run(self, once: bool = False) -> None:
        while True:
            self.service.run_cycle()
            if once:
                return
            self.logger.info("sleeping seconds=%s", self.poll_seconds)
            time.sleep(self.poll_seconds)
