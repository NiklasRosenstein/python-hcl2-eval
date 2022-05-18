import operator
from typing import TYPE_CHECKING, Any, Dict, List

from hcl2_ast import ast

if TYPE_CHECKING:
    from .env import Environment
    from .exec import ExecContext


class EvalContext:
    def __init__(self, env: "Environment") -> None:
        self.env = env

    def eval(self, expr: ast.Expression, ctx: "ExecContext") -> Any:
        method = "_eval_" + type(expr).__name__
        return getattr(self, method)(expr, ctx)

    def _eval_Literal(self, literal: ast.Literal, ctx: "ExecContext") -> Any:
        if isinstance(literal.value, str):
            import string

            template = string.Template(literal.value)
            return template.substitute(ctx.as_mapping())
        return literal.value

    def _eval_Identifier(self, identifier: ast.Identifier, ctx: "ExecContext") -> Any:
        return ctx.attr_get(identifier)

    def _eval_Array(self, array: ast.Array, ctx: "ExecContext") -> List[Any]:
        return [self.eval(value, ctx) for value in array.values]

    def _eval_Object(self, obj: ast.Object, ctx: "ExecContext") -> Dict[str, Any]:
        return {key: self.eval(value, ctx) for key, value in obj.fields.items()}

    def _eval_FunctionCall(self, func: ast.FunctionCall, ctx: "ExecContext") -> Any:
        return ctx.function_eval(func)

    def _eval_GetAttr(self, get_attr: ast.GetAttr, ctx: "ExecContext") -> Any:
        from .exec import ExecContext

        value = self.eval(get_attr.on, ctx)
        if isinstance(value, ExecContext):
            return value.attr_get(get_attr)
        return getattr(value, get_attr.name)

    def _eval_UnaryOp(self, unary_op: ast.UnaryOp, ctx: "ExecContext") -> Any:
        func = {
            "-": operator.neg,
            "!": operator.not_,
        }[unary_op.op]
        value = self.eval(unary_op.expr, ctx)
        return func(value)

    def _eval_BinaryOp(self, binary_op: ast.BinaryOp, ctx: "ExecContext") -> Any:
        func = {
            "==": operator.eq,
            "!=": operator.ne,
            "<": operator.lt,
            ">": operator.gt,
            "<=": operator.le,
            ">=": operator.ge,
            "-": operator.sub,
            "*": operator.mul,
            "/": operator.truediv,
            "%": operator.mod,
            "&&": operator.and_,
            "||": operator.or_,
            "+": operator.add,
        }[binary_op.op]
        left, right = self.eval(binary_op.left, ctx), self.eval(binary_op.right, ctx)
        return func(left, right)

    def _eval_GetIndex(self, get_index: ast.GetIndex, ctx: "ExecContext") -> Any:
        return self.eval(get_index.on, ctx)[get_index.index.value]

    def _eval_IndexSplat(self, splat: ast.IndexSplat, ctx: "ExecContext") -> Any:
        raise NotImplementedError

    def _eval_AttrSplat(self, splat: ast.AttrSplat, ctx: "ExecContext") -> Any:
        raise NotImplementedError
