"""本地结构化 JSON 行：终端 + 可选文件。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from log.config import LocalConfig
from log.events import TraceEvent

LOGGER_NAME = "trace"


class LocalTracer:
    def __init__(self, config: LocalConfig):
        self._config = config
        self._log = logging.getLogger(LOGGER_NAME)

    def setup(self) -> None:
        logger = self._log
        logger.handlers.clear()
        logger.propagate = False
        level = getattr(logging, self._config.level, logging.INFO)
        logger.setLevel(level)
        formatter = logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S")
        if self._config.stream:
            stream = logging.StreamHandler()
            stream.setLevel(level)
            stream.setFormatter(formatter)
            logger.addHandler(stream)
        if self._config.file:
            path = Path(self._config.file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info(
                "%s",
                json.dumps(
                    {"event": "trace.ready", "file": str(path)},
                    ensure_ascii=False,
                ),
            )

    def emit(self, event: TraceEvent) -> None:
        self._log.info("%s", json.dumps(event.payload(), ensure_ascii=False))
        for handler in self._log.handlers:
            handler.flush()

    def chat_callbacks(self) -> list:
        from log.callbacks import ChatTraceCallback

        return [ChatTraceCallback()]
