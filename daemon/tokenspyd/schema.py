from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Window:
    id: str
    label: str
    used_pct: float
    resets_at: Optional[str]
    window_seconds: int


@dataclass
class ProviderSnapshot:
    id: str
    display_name: str
    status: str  # ok | auth_expired | auth_missing | network_error | parse_error | disabled
    windows: list[Window] = field(default_factory=list)
    last_polled_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "status": self.status,
            "windows": [
                {
                    "id": w.id,
                    "label": w.label,
                    "used_pct": w.used_pct,
                    "resets_at": w.resets_at,
                    "window_seconds": w.window_seconds,
                }
                for w in self.windows
            ],
            "last_polled_at": self.last_polled_at,
            "error": self.error,
        }
