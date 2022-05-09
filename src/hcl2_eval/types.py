from beartype.typing import Dict, List, Union
from typing_extensions import Protocol, runtime_checkable

# NOTE (@NiklasRosenstein): Mypy does not currently support recursive type definitions.
#       See https://github.com/python/mypy/issues/731
PlainType = Union[None, bool, int, str, float]
ValueType = Union[PlainType, List[PlainType], Dict[str, PlainType]]


@runtime_checkable
class Function(Protocol):
    def __call__(self, args: List[ValueType]) -> ValueType:
        ...
