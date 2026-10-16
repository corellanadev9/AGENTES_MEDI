"""Carga opcional de secretos locales sin sobrescribir variables del entorno."""

import os
from pathlib import Path


ENV_FILE = Path(__file__).with_name(".env")
LOCAL_KEYS = {"OPENAI_API_KEY"}


def load_local_env() -> None:
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in LOCAL_KEYS or name in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value:
            os.environ[name] = value
