from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from .stanza import Stanza


class ConfigurationError(Exception):
    def __init__(self, stanza: "Stanza", message: str, causes: Sequence[Exception] = ()) -> None:
        self.stanza = stanza
        self.message = message
        self.causes = causes

    def __str__(self) -> str:
        result = f"in {self.stanza!r}: {self.message}"
        if self.causes:
            result += "\n- " + "\n- ".join(map(str, self.causes))
        return result
