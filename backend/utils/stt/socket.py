from abc import ABC, abstractmethod
from typing import Optional


class STTSocket(ABC):

    @abstractmethod
    def send(self, data: bytes) -> None: ...

    @abstractmethod
    def finish(self) -> None: ...

    @abstractmethod
    def finalize(self) -> None: ...

    @property
    @abstractmethod
    def is_connection_dead(self) -> bool: ...

    @property
    @abstractmethod
    def death_reason(self) -> Optional[str]: ...
