from typing import Type

import pytest
from hcl2_ast.ast import Expression, Stmt
from hcl2_eval.eval import EvalContext
from hcl2_eval.exec import ExecContext


@pytest.mark.parametrize("expr_type", Expression.__subclasses__())
def test__EvalContext_has_handler_method_for_all_expression_types(expr_type: Type[Expression]) -> None:
    assert hasattr(EvalContext, f"_eval_{expr_type.__name__}")
