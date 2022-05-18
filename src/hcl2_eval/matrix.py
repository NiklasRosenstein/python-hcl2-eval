import itertools
from typing import Any, Dict, Iterator, List, Optional

from hcl2_ast import ast

from .exec import Block, ExecContext, block_function


class MatrixBlock(Block):

    _values: Dict[str, List[Any]]

    def __init__(self, ctx: ExecContext, id: Optional[str]) -> None:
        if id is not None:
            ctx.named_blocks[id] = self
            print("@@", ctx.named_blocks, self.__block_functions__)
        self._values: Dict[str, List[Any]] = {}
        self._ctx = ctx
        self._id = id

    def cross_product(self) -> Iterator[Dict[str, Any]]:
        factors = []
        for key, values in self._values.items():
            factors.append([(key, v) for v in values])
        for variables in itertools.product(*factors):
            yield dict(variables)

    def attr_set(self, ctx: "ExecContext", node: ast.Attribute) -> None:
        value = ctx.eval(node.value)
        if not isinstance(value, list):
            value = [value]
        self._values[node.key] = value

    def open_block(self, ctx: "ExecContext", node: ast.Block) -> None:
        for variables in self.cross_product():
            self._ctx.block.open_block(ctx.sub_context(variables), node)

    @block_function("cross")
    def _function_cross(self, ctx: ExecContext, node: ast.FunctionCall) -> Any:
        if len(node.args) != 1:
            raise ValueError(f"cross() takes 1 argument, got {len(node.args)}")
        try:
            result = []
            for variables in self.cross_product():
                result.append(ctx.sub_context(variables).eval(node.args[0]))
            print(">>", result)
            return result
        except:
            # TOOD (@NiklasRosenstein): We don't want to propate an AttributeError that we can
            #       mishap for the function not existing.
            raise Exception
