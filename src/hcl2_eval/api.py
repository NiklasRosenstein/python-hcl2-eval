""" Provides the #Configurable base class that allows for evaluating HCL2 configuration code. """

from beartype import beartype
from beartype.typing import Any, Collection, Dict, Iterator, List, Optional, Union, cast
from hcl2_ast.ast import (
    Array,
    Attribute,
    BinaryOp,
    Block,
    Expression,
    FunctionCall,
    GetAttr,
    Identifier,
    Literal,
    Module,
    Object,
    Stmt,
    UnaryOp,
)

from .error import ConfigurationError
from .stanza import CommonStanza, Stanza, StanzaOpener
from .types import Function, PlainType, ValueType


class Context:
    """The context provides all context-relevant data for the evaluation of a HCL2 AST.

    If the context's current :attr:`target` is a :class:`Stanza`, relevant calls will be
    delegated to the Stanza."""

    @staticmethod
    def of(**stanza_openers: StanzaOpener) -> "Context":
        root = CommonStanza()
        root.stanza_openers.update(stanza_openers)
        return Context(root)

    @classmethod
    @beartype
    def stanza(cls, stanza: Stanza, parent: Optional["Context"] = None) -> "Context":
        return cls(stanza, parent)

    def __init__(self, target: Any, parent: Optional["Context"] = None) -> None:
        self.target = target
        self.parent = parent

    def iter_hierarchy_up(self) -> Iterator["Context"]:
        current: Optional[Context] = self
        while current:
            yield current
            current = current.parent

    @beartype
    def attribute_get(self, attr_name: str) -> Union[ValueType, "Context"]:
        exceptions: List[ConfigurationError] = []
        for context in self.iter_hierarchy_up():
            if isinstance(context.target, Stanza):
                try:
                    value = context.target.attribute_get(attr_name)
                except ConfigurationError as exc:
                    exceptions.append(exc)
                else:
                    if isinstance(value, Stanza):
                        return Context.stanza(value, self)
                    return value
        raise ConfigurationError(self.target, f"attribute {attr_name!r} does not exist", exceptions)

    @beartype
    def attribute_set(self, attr_name: str, value: ValueType) -> None:
        if isinstance(self.target, Stanza):
            self.target.attribute_set(attr_name, value)
        else:
            raise ConfigurationError(self.target, f"attribute {attr_name!r} does not exist")

    @beartype
    def function_get(self, func_name: str) -> Function:
        exceptions: List[ConfigurationError] = []
        for context in self.iter_hierarchy_up():
            if isinstance(context.target, Stanza):
                try:
                    return context.target.function_get(func_name)
                except ConfigurationError as exc:
                    exceptions.append(exc)
        raise ConfigurationError(self.target, f"function {func_name!r} does not exist", exceptions)

    @beartype
    def stanza_open(self, stanza_name: str, args: List[ValueType]) -> "Context":
        if isinstance(self.target, Stanza):
            return Context.stanza(self.target.stanza_open(stanza_name, args), self)
        raise ConfigurationError(self.target, f"stanza {stanza_name!r} does not exist")

    def close(self) -> None:
        if isinstance(self.target, Stanza):
            self.target.close()


class Evaluator:
    """Evaluator for expressions."""

    @beartype
    def evaluate(self, expr: Expression, context: Context) -> ValueType:
        method = "_eval_" + type(expr).__name__
        return cast(ValueType, getattr(self, method)(expr, context))

    @beartype
    def _eval_Literal(self, literal: Literal, context: Context) -> PlainType:
        return literal.value

    @beartype
    def _eval_Identifier(self, identifier: Identifier, context: Context) -> Union[ValueType, Context]:
        return context.attribute_get(identifier.name)

    @beartype
    def _eval_Array(self, array: Array, context: Context) -> List[ValueType]:
        return [self.evaluate(value, context) for value in array.values]

    @beartype
    def _eval_Object(self, obj: Object, context: Context) -> Dict[str, ValueType]:
        return {key: self.evaluate(value, context) for key, value in obj.fields.items()}

    @beartype
    def _eval_FunctionCall(self, func: FunctionCall, context: Context) -> ValueType:
        function = context.function_get(func.name)
        args = [self.evaluate(arg, context) for arg in func.args]
        return function(args)

    @beartype
    def _eval_GetAttr(self, get_attr: GetAttr, context: Context) -> Union[ValueType, Context]:
        value = self.evaluate(get_attr.on, context)
        if isinstance(value, Context):
            return value.attribute_get(get_attr.name)  # type: ignore[unreachable]
        return value

    @beartype
    def _eval_UnaryOp(self, unary_op: UnaryOp, context: Context) -> ValueType:
        raise NotImplementedError

    @beartype
    def _eval_BinaryOp(self, binary_op: BinaryOp, context: Context) -> ValueType:
        raise NotImplementedError


class Interpreter:
    @beartype
    def __init__(
        self,
        evaluator: Evaluator,
        enable_blocks: Optional[Collection[str]] = None,
        disable_blocks: Optional[Collection[str]] = None,
    ) -> None:
        self.evaluator = evaluator
        self.enable_blocks = enable_blocks
        self.disable_blocks = disable_blocks

    @beartype
    def execute(self, stmt: Union[Stmt, Module], context: Context) -> None:
        if isinstance(stmt, Module):
            for node in stmt.body:
                self.execute(node, context)
        else:
            method = "_handle_" + type(stmt).__name__
            getattr(self, method)(stmt, context)

    @beartype
    def _handle_Attribute(self, attr: Attribute, context: Context) -> None:
        context.attribute_set(attr.key, self.evaluator.evaluate(attr.value, context))

    @beartype
    def _handle_Block(self, block: Block, context: Context) -> None:
        assert isinstance(context, Context), type(context)
        if self.enable_blocks is not None and block.name not in self.enable_blocks:
            return
        if self.disable_blocks is not None and block.name in self.disable_blocks:
            return
        args = [self.evaluator.evaluate(arg, context) for arg in block.args]
        new_context = context.stanza_open(block.name, args)
        assert isinstance(new_context, Context), type(new_context)
        for stmt in block.body:
            self.execute(stmt, new_context)
        new_context.close()
