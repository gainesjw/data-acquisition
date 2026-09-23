"""Required collector settings shared by local and hosted execution."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    account_name: str
    container_name: str


def get_settings() -> Settings:
    values = []
    for name in ("STORAGE_ACCOUNT_NAME", "CONTAINER_NAME"):
        value = os.environ.get(name, "").strip()
        if not value or value.startswith("$("):
            raise ValueError(f"Set {name} explicitly before running the collector")
        values.append(value)
    return Settings(*values)
