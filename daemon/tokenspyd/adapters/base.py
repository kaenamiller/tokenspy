from __future__ import annotations

from abc import ABC, abstractmethod

from ..schema import ProviderSnapshot


class Adapter(ABC):
    id: str
    display_name: str

    @abstractmethod
    async def fetch(self) -> ProviderSnapshot:
        """Returns a ProviderSnapshot. Never raises — all errors become snapshots."""
        ...
