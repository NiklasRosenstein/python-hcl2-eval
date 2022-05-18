from typing import Callable, Dict, Optional

from hcl2_ast import ast

from .eval import EvalContext
from .exec import Block, ExecContext

ExecContextFactory = Callable[["Environment", Block, Optional[ExecContext]], ExecContext]
EvalContextFactory = Callable[["Environment"], EvalContext]
BlockOpenerFunc = Callable[["ExecContext", ast.Block], None]


class Environment:
    """HCL2 evaluation environment. Keeps track of the #ExecContext and #EvalContext implementations, as well as
    global block openers, functions and variables."""

    def __init__(
        self,
        exec_context: ExecContextFactory = ExecContext,
        eval_context: EvalContextFactory = EvalContext,
    ) -> None:
        self.exec_context = exec_context
        self.eval_context = eval_context
        self.block_openers: Dict[str, BlockOpenerFunc] = {}

        from .matrix import MatrixBlock

        self.add_block_opener(
            "matrix",
            lambda ctx, node: ctx.sub_context(MatrixBlock(ctx, ctx.eval(node.args[0]) if node.args else None)).execute(
                node.body
            ),
        )

    def add_block_opener(self, name: str, opener: BlockOpenerFunc) -> None:
        self.block_openers[name] = opener

    def execute(self, root_block: Block, module: ast.Module) -> None:
        ctx = self.exec_context(self, root_block, None)
        ctx.execute(module.body)
