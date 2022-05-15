
""" Implements the execution of HCL2 ASTs. """



import copy
import itertools
import operator
import textwrap
import typeapi
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, TypeVar, Union, cast
from hcl2_ast import ast
T = TypeVar("T")
FunctionType = Callable[["ExecContext", ast.FunctionCall], Any]
BlockOpenerType = Callable[["ExecContext", ast.Block], "Block"]


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
    __block_functions__: Dict[str, str] = {}
    __block_openers__: Dict[str, str] = {}

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
                cls.__block_functions__[function_name] = key
                continue

            block_name = getattr(value, '__block_opener_name__', None)
            if block_name is not None:
                cls.__block_openers__[block_name] = key
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
        print("Exists function?", node, self, self.__block_functions__)
        if node.name in self.__block_functions__:
            return getattr(self, self.__block_functions__[node.name])(ctx, node)
        else:
            raise AttributeError(f"{node.name}()")

    def open_block(self, ctx: "ExecContext", node: ast.Block) -> None:
        if node.name in self.__block_openers__:
            block = getattr(self, self.__block_openers__[node.name])(ctx, node)
            ExecContext(block, ctx).execute(node.body)
        else:
            raise AttributeError(f"{node.name} {{}}")


class ExecContext:
    """Represents the execution context of a single block. It keeps track of the hierarchy of
    blocks in order to resolve variable references and named blocks. """

    def __init__(self, block: Block, parent: Optional["ExecContext"] = None) -> None:
        self.block = block
        self.parent = parent
        self.named_blocks: Dict[str, Block] = {}
        self.variables: Dict[str, Any] = {}
        self.global_block_openers: Dict[str, BlockOpenerType] = {}
        self.global_block_openers['matrix'] = lambda ctx, node: ExecContext(MatrixBlock(ctx, ctx.eval(node.args[0]) if node.args else None), ctx).execute(node.body)

    def execute(self, stmts: List[ast.Stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Attribute):
                self.block.attr_set(self, stmt)
            elif isinstance(stmt, ast.Block):
                if stmt.name in self.global_block_openers:
                    self.global_block_openers[stmt.name](self, stmt)
                else:
                    self.block.open_block(self, stmt)
            else:
                raise RuntimeError(f"unexpected statement: {stmt!r}")

    def eval(self, expr: ast.Expression) -> Any:
        return Eval().eval(expr, self)

    def attr_get(self, node: Union[ast.Identifier, ast.GetAttr]) -> Any:
        if isinstance(node, ast.Identifier) and node.name in self.variables:
            return self.variables[node.name]
        try:
            return self.block.attr_get(self, node)
        except AttributeError:
            if self.parent:
                return self.parent.attr_get(node)
            raise

    def function_eval(self, node: ast.FunctionCall) -> Any:
        assert isinstance(node, ast.FunctionCall), node
        parts = node.name.split("__")
        current = self

        print(parts, current, self.named_blocks)

        while len(parts) > 1:
            if isinstance(current, ExecContext):
                if parts[0] in current.named_blocks:
                    current = current.named_blocks[parts.pop(0)]
                elif parts[0] in current.variables:
                    current = current.variables[parts.pop(0)]
                else:
                    break
            else:
                current = getattr(current, parts.pop(0))

        print('::', parts, current)
        if len(parts) == 1 and isinstance(current, Block):
            mod_node = copy.copy(node)
            mod_node.name = parts[0]
            try:
                return current.function_eval(self, mod_node)
            except AttributeError:
                pass
        elif not parts and callable(current):
            return current(*(self.eval(arg) for arg in node.args))


        if self.parent:
            return self.parent.function_eval(node)
        raise AttributeError(node.name)

    def with_variables(self, variables: Dict[str, Any]) -> "ExecContext":
        sub_ctx = ExecContext(self.block, self)
        sub_ctx.variables.update(variables)
        return sub_ctx

    def as_mapping(self) -> Mapping[str, Any]:
        class _Mapping:
            def __getitem__(_self, key: str) -> Any:
                return self.attr_get(ast.Identifier(key))
        return _Mapping()


class Eval:

    def eval(self, expr: ast.Expression, ctx: ExecContext) -> Any:
        method = "_eval_" + type(expr).__name__
        return getattr(self, method)(expr, ctx)

    def _eval_Literal(self, literal: ast.Literal, ctx: ExecContext) -> Any:
        if isinstance(literal.value, str):
            import string
            template = string.Template(literal.value)
            return template.substitute(ctx.as_mapping())
        return literal.value

    def _eval_Identifier(self, identifier: ast.Identifier, ctx: ExecContext) -> Any:
        return ctx.attr_get(identifier)

    def _eval_Array(self, array: ast.Array, ctx: ExecContext) -> List[Any]:
        return [self.eval(value, ctx) for value in array.values]

    def _eval_Object(self, obj: ast.Object, ctx: ExecContext) -> Dict[str, Any]:
        return {key: self.eval(value, ctx) for key, value in obj.fields.items()}

    def _eval_FunctionCall(self, func: ast.FunctionCall, ctx: ExecContext) -> Any:
        return ctx.function_eval(func)

    def _eval_GetAttr(self, get_attr: ast.GetAttr, ctx: ExecContext) -> Any:
        value = self.eval(get_attr.on, ctx)
        if isinstance(value, ExecContext):
            return value.attr_get(get_attr.name)  # type: ignore[unreachable]
        return getattr(value, get_attr.name)

    def _eval_UnaryOp(self, unary_op: ast.UnaryOp, ctx: ExecContext) -> Any:
        func = {
            "-": operator.neg,
            "!": operator.not_,
        }
        value = self.eval(unary_op.expr, ctx)
        return func(value)

    def _eval_BinaryOp(self, binary_op: ast.BinaryOp, ctx: ExecContext) -> Any:
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

    def open_block(self, ctx: "ExecContext", node: ast.Block) -> "Block":
        for variables in self.cross_product():
            self._ctx.block.open_block(ctx.with_variables(variables), node)

    @block_function("cross")
    def _function_cross(self, ctx: ExecContext, node: ast.FunctionCall) -> Any:
        if len(node.args) != 1:
            raise ValueError(f"cross() takes 1 argument, got {len(node.args)}")
        try:
            result = []
            for variables in self.cross_product():
                result.append(ctx.with_variables(variables).eval(node.args[0]))
            print('>>', result)
            return result
        except:
            # TOOD (@NiklasRosenstein): We don't want to propate an AttributeError that we can
            #       mishap for the function not existing.
            raise Exception
