""" Implements the execution of HCL2 ASTs. """


import copy
import textwrap
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, List, Mapping, Optional, TypeVar, Union

import typeapi
from hcl2_ast import ast

if TYPE_CHECKING:
    from .env import Environment

T = TypeVar("T")
FunctionType = Callable[["ExecContext", ast.FunctionCall], Any]


def _indent_but_first(text: str, indent: str) -> str:
    lines = text.splitlines()
    return (lines[0] + "\n" + textwrap.indent("\n".join(lines[1:]), indent)).rstrip()


def block_function(name: Optional[str] = None) -> Callable[[T], T]:
    """Decorator for methods to let :class:`Block` subclasses to pick it up as block openers."""

    def decorator(func: T) -> T:
        func.__block_function_name__ = name or func.__name__  # type: ignore
        return func

    return decorator


def block_opener(name: Optional[str] = None) -> Callable[[T], T]:
    """Decorator for methods to let :class:`Block` subclasses to pick it up as block openers."""

    def decorator(func: T) -> T:
        func.__block_opener_name__ = name or func.__name__  # type: ignore
        return func

    return decorator


class Block:
    """Represents a block in a HCL2 configuration script. Blocks provide attributes, functions
    and other blocks. HCL2 AST statements are executed in the context of a block. Block attributes
    are recognized by type annotations."""

    __block_attributes__: Dict[str, typeapi.Hint] = {}
    __block_functions__: Dict[str, str] = {}
    __block_openers__: Dict[str, str] = {}

    def __init_subclass__(cls) -> None:
        cls.__block_attributes__ = {}

        # Store annotations as attributes and initialize default value of fields that are None.
        for key, value in typeapi.get_annotations(cls, include_bases=True).items():
            if key.startswith("_"):
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

            function_name = getattr(value, "__block_function_name__", None)
            if function_name is not None:
                cls.__block_functions__[function_name] = key
                continue

            block_name = getattr(value, "__block_opener_name__", None)
            if block_name is not None:
                cls.__block_openers__[block_name] = key
                continue

    def __repr__(self) -> str:
        lines = [f"<{type(self).__name__}"]
        for key in self.__block_attributes__:
            if hasattr(self, key):
                value = repr(getattr(self, key))
            else:
                value = "(unset)"
            lines.append(f'  {key}={_indent_but_first(value, "  ")}')
        lines.append(">")
        return "\n".join(lines)

    def attr_get(self, ctx: "ExecContext", node: Union[ast.Identifier, ast.GetAttr]) -> None:
        if node.name not in self.__block_attributes__:
            raise AttributeError(node.name)
        return getattr(self, node.name)

    def attr_set(self, ctx: "ExecContext", node: ast.Attribute) -> None:
        if node.key not in self.__block_attributes__:
            raise AttributeError(node.key)
        setattr(self, node.key, ctx.eval(node.value))

    def function_eval(self, ctx: "ExecContext", node: ast.FunctionCall) -> None:
        if node.name in self.__block_functions__:
            return getattr(self, self.__block_functions__[node.name])(ctx, node)
        else:
            raise AttributeError(f"{node.name}()")

    def open_block(self, ctx: "ExecContext", node: ast.Block) -> None:
        if node.name in self.__block_openers__:
            block = getattr(self, self.__block_openers__[node.name])(ctx, node)
            ctx.sub_context(block).execute(node.body)
        else:
            raise AttributeError(f"{node.name} {{}}")


class ExecContext:
    """Represents the execution context of a single block. It keeps track of the hierarchy of
    blocks in order to resolve variable references and named blocks."""

    def __init__(self, env: "Environment", block: Block, parent: Optional["ExecContext"] = None) -> None:
        self.env = env
        self.block = block
        self.parent = parent
        self.named_blocks: Dict[str, Block] = {}
        self.variables: Dict[str, Any] = {}

    def execute(self, stmts: List[ast.Stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Attribute):
                self.block.attr_set(self, stmt)
            elif isinstance(stmt, ast.Block):
                if stmt.name in self.env.block_openers:
                    self.env.block_openers[stmt.name](self, stmt)
                else:
                    self.block.open_block(self, stmt)
            else:
                raise RuntimeError(f"unexpected statement: {stmt!r}")

    def eval(self, expr: ast.Expression) -> Any:
        return self.env.eval_context(self.env).eval(expr, self)

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
        current: Any = self

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

    def sub_context(self, block: Optional[Block] = None, variables: Optional[Dict[str, Any]] = None) -> "ExecContext":
        sub_ctx = ExecContext(self.env, block or self.block, self)
        sub_ctx.variables.update(variables or {})
        return sub_ctx

    def as_mapping(self) -> Mapping[str, Any]:
        class _Mapping(Mapping[str, Any]):
            def __len__(self) -> int:
                raise NotImplementedError

            def __iter__(self) -> Iterator[str]:
                raise NotImplementedError

            def __getitem__(_self, key: str) -> Any:
                return self.attr_get(ast.Identifier(key))

        return _Mapping()
