from typing import Dict, List, Union

from typing_extensions import Protocol

from .error import ConfigurationError
from .types import Function, ValueType


class StanzaOpener(Protocol):
    def __call__(self, *args: ValueType) -> "Stanza":
        raise NotImplementedError


class Stanza:
    """A *stanza* is a container for configuration content.

    Stanzas contain attributes and can expose other context-specific stanzas."""

    def __repr__(self) -> str:
        return f"(Stanza {type(self).__module__}.{type(self).__qualname__})"

    def attribute_get(self, attr_name: str) -> Union[ValueType, "Stanza"]:
        raise ConfigurationError(self, f"attribute {attr_name!r} does not exist")

    def attribute_set(self, attr_name: str, value: ValueType) -> None:
        raise ConfigurationError(self, f"attribute {attr_name!r} does not exist")

    def function_get(self, func_name: str) -> Function:
        raise ConfigurationError(self, f"function {func_name!r} does not exist")

    def stanza_open(self, stanza_name: str, args: List[ValueType]) -> "Stanza":
        raise ConfigurationError(self, f"stanza {stanza_name!r} does not exist")

    def close(self) -> None:
        pass


class CommonStanza(Stanza):
    """A common Stanza class to use as a base or to instantiate."""

    def __init__(self, **attributes: ValueType) -> None:
        self.attributes = attributes
        self.stanza_openers: Dict[str, StanzaOpener] = {}
        self.functions: Dict[str, Function] = {}

    def add_stanza_opener(self, stanza_name: str, stanza_opener: StanzaOpener) -> None:
        self.stanza_openers[stanza_name] = stanza_opener

    def add_function(self, func_name: str, function: Function) -> None:
        self.functions[func_name] = function

    def attribute_get(self, attr_name: str) -> Union[ValueType, "Stanza"]:
        if attr_name in self.attributes:
            return self.attributes[attr_name]
        return super().attribute_get(attr_name)

    def attribute_set(self, attr_name: str, value: ValueType) -> None:
        if attr_name in self.attributes:
            self.attributes[attr_name] = value
        else:
            return super().attribute_set(attr_name, value)

    def function_get(self, func_name: str) -> Function:
        if func_name in self.functions:
            return self.functions[func_name]
        return super().function_get(func_name)

    def stanza_open(self, stanza_name: str, args: List[ValueType]) -> "Stanza":
        if stanza_name in self.stanza_openers:
            return self.stanza_openers[stanza_name](*args)
        return super().stanza_open(stanza_name, args)
