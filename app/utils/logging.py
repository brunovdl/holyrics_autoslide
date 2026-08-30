"""Sistema de logging estruturado com rotação e sanitização de tokens."""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Callable

TOKEN_SANITIZE_REGEX = re.compile(r"(token=)[^&\s]+", re.IGNORECASE)
BEARER_SANITIZE_REGEX = re.compile(r"(Bearer\s+)[^\s]+", re.IGNORECASE)

LOG_CALLBACKS: list[Callable[[str, str, str], None]] = []


def sanitize_log_message(msg: str) -> str:
    """Sanitiza tokens e segredos para que nunca apareçam nos logs."""
    sanitized = TOKEN_SANITIZE_REGEX.sub(r"\1***", msg)
    sanitized = BEARER_SANITIZE_REGEX.sub(r"\1***", sanitized)
    return sanitized


class SafeFormatter(logging.Formatter):
    """Formatador customizado que sanitiza segredos e formata categorias."""
    def format(self, record: logging.LogRecord) -> str:
        orig_msg = record.getMessage()
        sanitized_msg = sanitize_log_message(orig_msg)
        record.msg = sanitized_msg
        record.args = None
        formatted = super().format(record)

        # Notifica listeners da UI
        category = getattr(record, "category", "APP")
        level = record.levelname
        for cb in LOG_CALLBACKS:
            try:
                cb(category, level, sanitized_msg)
            except Exception:
                pass
        return formatted


def register_log_listener(cb: Callable[[str, str, str], None]) -> None:
    """Registra callback para transmitir logs à interface gráfica."""
    if cb not in LOG_CALLBACKS:
        LOG_CALLBACKS.append(cb)


def unregister_log_listener(cb: Callable[[str, str, str], None]) -> None:
    """Remove callback de logs."""
    if cb in LOG_CALLBACKS:
        LOG_CALLBACKS.remove(cb)


def setup_logger(log_file: Path | None = None) -> logging.Logger:
    """Configura o logger principal da aplicação."""
    logger = logging.getLogger("holyrics_autoslide")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        formatter = SafeFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(category)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger


def log_event(category: str, message: str, level: int = logging.INFO) -> None:
    """Função utilitária para registrar eventos com categoria."""
    logger = logging.getLogger("holyrics_autoslide")
    logger.log(level, message, extra={"category": category})

