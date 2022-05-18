from typing import TYPE_CHECKING, Callable, Dict

from hcl2_ast import ast

from hcl2_eval.exec import BlockOpenerFunc

if TYPE_CHECKING:
    from .eval import EvalContext
    from .exec import Block, ExecContext


ExecContextFactory = Callable[["Environment", Block, ExecContext], ExecContext]
EvalContextFactory = Callable[["Environment"], EvalContext]
BlockOpenerFunc = Callable[["ExecContext", ast.Block], None]


class Environment:
    """HCL2 evaluation environment. Keeps track of the #ExecContext and #EvalContext implementations, as well as
    global block openers, functions and variables."""

    def __init__(self, exec_context: ExecContext, eval_context: EvalContext) -> None:
        self.exec_context = exec_context
        self.eval_context = eval_context
        self.block_openers: Dict[str, BlockOpenerFunc] = {}

        from .matrix import MatrixBlock

        self.add_block_opener(
            "matrix",
            lambda ctx, node: ctx.sub_context(MatrixBlock(ctx, ctx.eval(node.args[0]) if node.args else None), ctx).execute(
                node.body
            ),
        )

    def add_block_opener(self, name: str, opener: BlockOpenerFunc) -> None:
        self.block_openers[name] = opener
