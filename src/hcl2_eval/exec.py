
""" Implements the execution of HCL2 ASTs. """


import textwrap
from beartype import beartype
import typeapi
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, cast
from hcl2_ast import ast
T = TypeVar("T")


def _indent_but_first(text: str, indent: str) -> str:
    lines = text.splitlines()
    return (lines[0] + "\n" + textwrap.indent("\n".join(lines[1:]), indent)).rstrip()


def block_function(name: Optional[str] = None) -> Callable[[T], T]:
    """ Decorator for methods to let :class:`Block` subclasses to pick it up as block openers."""

    def decorator(func: T) -> T:
        func.__block_function_name__ = name or func.__name__  # type: ignore
        return func

    return decorator


def block_opener(name: Optional[str] = None) -> Callable[[T], T]:
    """ Decorator for methods to let :class:`Block` subclasses to pick it up as block openers."""

    def decorator(func: T) -> T:
        func.__block_opener_name__ = name or func.__name__  # type: ignore
        return func

    return decorator


class Block:
    """ Represents a block in a HCL2 configuration script. Blocks provide attributes, functions
    and other blocks. HCL2 AST statements are executed in the context of a block. Block attributes
    are recognized by type annotations. """

    __block_attributes__: Dict[str, typeapi.Hint] = {}
    __block_functions__: Dict[str, Callable[["Block", "ExecContext", ast.FunctionCall], Any]] = {}
    __block_openers__: Dict[str, Callable[["Block", "ExecContext", ast.Block], "Block"]] = {}

    def __init_subclass__(cls) -> None:
        cls.__block_attributes__ = {}

        # Store annotations as attributes and initialize default value of fields that are None.
        for key, value in typeapi.get_annotations(cls, include_bases=True).items():
            if key.startswith('_'):
                continue
            hint = typeapi.of(value)
            # TODO (@NiklasRosenstein): Validate that the type is one that is supported by HCL.
            if isinstance(hint, typeapi.Union) and hint.has_none_type() and not hasattr(cls, key):
                setattr(cls, key, None)
            # elif not hasattr(cls, key):
            #     raise ValueError(f"need default value for Block attribute {cls.__name__}.{key}")
            cls.__block_attributes__[key] = hint

        # Recognize registered block openers and functions.
        for key, value in vars(cls).items():

            function_name = getattr(value, '__block_function_name__', None)
            if function_name is not None:
                cls.__block_functions__[function_name] = value
                continue

            block_name = getattr(value, '__block_opener_name__', None)
            if block_name is not None:
                cls.__block_openers__[block_name] = value
                continue

    def __repr__(self) -> str:
        lines = [f'<{type(self).__name__}']
        for key in self.__block_attributes__:
            if hasattr(self, key):
                value = repr(getattr(self, key))
            else:
                value = '(unset)'
            lines.append(f'  {key}={_indent_but_first(value, "  ")}')
        lines.append('>')
        return '\n'.join(lines)

    def attr_get(self, ctx: "ExecContext", node: Union[ast.Identifier, ast.GetAttr]) -> None:
        if node.key not in self.__block_attributes__:
            raise AttributeError(node.key)
        return getattr(self, node.key)

    def attr_set(self, ctx: "ExecContext", node: ast.Attribute) -> None:
        if node.key not in self.__block_attributes__:
            raise AttributeError(node.key)
        setattr(self, node.key, ctx.eval(node.value))

    def function_eval(self, ctx: "ExecContext", node: ast.FunctionCall) -> None:
        if node.name in self.__block_functions__:
            return self.__block_functions__[node.name](self, ctx, node)
        else:
            raise AttributeError(f"{node.name}()")

    def open_block(self, ctx: "ExecContext", node: ast.Block) -> "Block":
        if node.name in self.__block_openers__:
            return self.__block_openers__[node.name](self, ctx, node)
        else:
            raise AttributeError(f"{node.name} {{}}")


class ExecContext:
    """Represents the execution context of a single block. It keeps track of the hierarchy of
    blocks in order to resolve variable references and named blocks. """

    def __init__(self, block: Block, parent: Optional["ExecContext"] = None) -> None:
        self.block = block
        self.parent = parent
        self.named_blocks: Dict[str, Block] = {}

    def execute(self, stmts: List[ast.Stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Attribute):
                self.block.attr_set(self, stmt)
            elif isinstance(stmt, ast.Block):
                sub_ctx = ExecContext(self.block.open_block(self, stmt), self)
                sub_ctx.execute(stmt.body)
            else:
                raise RuntimeError(f"unexpected statement: {stmt!r}")

    def eval(self, expr: ast.Expression) -> Any:
        return Eval().eval(expr, self)

    def attr_get(self, ctx: "ExecContext", node: Union[ast.Identifier, ast.GetAttr]) -> None:
        try:
            return self.block.attr_get(ctx, node)
        except AttributeError:
            if self.parent:
                return self.parent.attr_get(ctx, node)
            raise

    def function_eval(self, ctx: "ExecContext", node: ast.FunctionCall) -> None:
        try:
            return self.block.function_eval(ctx, node)
        except AttributeError:
            if self.parent:
                return self.parent.function_eval(ctx, node)
            raise


class Eval:

    @beartype
    def eval(self, expr: ast.Expression, ctx: ExecContext) -> Any:
        method = "_eval_" + type(expr).__name__
        return getattr(self, method)(expr, ctx)

    @beartype
    def _eval_Literal(self, literal: ast.Literal, ctx: ExecContext) -> Any:
        return literal.value

    @beartype
    def _eval_Identifier(self, identifier: ast.Identifier, ctx: ExecContext) -> Any:
        return ctx.attr_get(identifier.name)

    @beartype
    def _eval_Array(self, array: ast.Array, ctx: ExecContext) -> List[Any]:
        return [self.eval(value, ctx) for value in array.values]

    @beartype
    def _eval_Object(self, obj: ast.Object, ctx: ExecContext) -> Dict[str, Any]:
        return {key: self.eval(value, ctx) for key, value in obj.fields.items()}

    @beartype
    def _eval_FunctionCall(self, func: ast.FunctionCall, ctx: ExecContext) -> Any:
        function = ctx.function_get(func.name)
        args = [self.eval(arg, ctx) for arg in func.args]
        return function(args)

    @beartype
    def _eval_GetAttr(self, get_attr: ast.GetAttr, ctx: ExecContext) -> Any:
        value = self.eval(get_attr.on, ctx)
        if isinstance(value, ExecContext):
            return value.attr_get(get_attr.name)  # type: ignore[unreachable]
        return getattr(value, get_attr.name)

    @beartype
    def _eval_UnaryOp(self, unary_op: ast.UnaryOp, ctx: ExecContext) -> Any:
        raise NotImplementedError

    @beartype
    def _eval_BinaryOp(self, binary_op: ast.BinaryOp, ctx: ExecContext) -> Any:
        raise NotImplementedError
