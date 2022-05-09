from typing import Type

import pytest
from hcl2_ast.ast import Expression, Stmt

from hcl2_eval.api import Evaluator, Interpreter


@pytest.mark.parametrize("expr_type", Expression.__subclasses__())
def test__Evaluator__has_method_for_all_expression_nodes(expr_type: Type[Expression]) -> None:
    assert hasattr(Evaluator, f"_eval_{expr_type.__name__}")


@pytest.mark.parametrize("stmt_type", Stmt.__subclasses__())
def test__Interpreter__has_method_for_all_stmt_nodes(stmt_type: Type[Stmt]) -> None:
    assert hasattr(Interpreter, f"_handle_{stmt_type.__name__}")
