from typing import List, Optional

from hcl2_ast import ast, parse_string

from hcl2_eval.env import Environment
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
            raise ValueError("block hello does not support arguments")
        block = HelloBlock()
        self.hello_blocks.append(block)
        return block


def main():
    module = parse_string(
        """
        matrix "mat1" {
            name = ["yennefer", "gerald"]
            where = ["rivia", "ceris"]
            hello {
                name = "${name} (${where})"
            }
        }
        hello {
            name = mat1__cross(":${name}-${where}")
        }
        """
    )

    env = Environment()
    env.execute(ProjectBlock(), module)


if __name__ == "__main__":
    main()
