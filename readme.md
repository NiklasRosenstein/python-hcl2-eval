# hcl2-eval

Evaluate HCL2 configurations like a programming language. Based on [hcl2-ast][].

  [hcl2-ast]: https://pypi.org/project/hcl2-ast/
## Usage

The evaluation of the HCL2 AST uses three components: A *context*, an *evaluator* an
*interpreter*. The context is responsible for performing attribute reads and writes, looking
up functions as well as opening and closing *stanzas*. The evaluator's responsibility is to
evaluate expressions in the AST to Python values, while the interpreter executes statement nodes.


```py
from hcl2_ast import parse_file
from hcl2_eval import Context, Evaluator, Interpreter, Stanza

class HelloStanza(Stanza):
    ...

module = parse_file(open("hello.hcl"), close=True)
context = Context.of(hello=HelloStanza)
Interpreter(Evaluator()).execute(module, context)
```

Check out the full example at [examples/hello.py](https://github.com/NiklasRosenstein/python-hcl2-eval/blob/develop/examples/hello.py).

## Compatibility

hcl2-eval requires Python 3.6 or higher.
