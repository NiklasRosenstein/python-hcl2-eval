from typing import List, Optional

from hcl2_ast import parse_string
from hcl2_ast import ast
from hcl2_eval.exec import Block, ExecContext, block_opener


class HelloBlock(Block):

    name: str


class ProjectBlock(Block):

    name: Optional[str]
    hello_blocks: List["HelloBlock"]

    def __init__(self) -> None:
        self.hello_blocks = []

    @block_opener()
    def hello(self, ctx: ExecContext, node: ast.Block) -> "HelloBlock":
        if node.args:
            raise ValueError(f"block hello does not support arguments")
        block = HelloBlock()
        self.hello_blocks.append(block)
        return block


def main():
    module = parse_string(
        """
        hello {
            name = "World"
        }
        """
    )

    context = ExecContext(ProjectBlock())
    context.execute(module.body)

    print(context.block)


if __name__ == "__main__":
    main()
