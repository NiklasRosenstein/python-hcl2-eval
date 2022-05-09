from typing import Optional

from hcl2_ast import parse_string

from hcl2_eval import ConfigurationError, Context, Evaluator, Interpreter, Stanza, ValueType


class HelloStanza(Stanza):
    def __init__(self) -> None:
        self.name: Optional[str] = None

    def validate(self) -> None:
        if self.name is None:
            raise ConfigurationError(self, 'attribute "name" must be set')

    def say_hello(self) -> None:
        assert self.name is not None
        print(f"Hello, {self.name}!")

    # Stanza

    def attribute_set(self, attr_name: str, value: ValueType) -> None:
        if attr_name == "name":
            if not isinstance(value, str):
                raise ConfigurationError(self, 'attribute "name" must be a str')
            self.name = value
        else:
            super().set_attribute(attr_name, value)

    def close(self) -> None:
        self.validate()
        self.say_hello()


def main():
    module = parse_string(
        """
        hello {
            name = "World"
        }
        """
    )

    context = Context.of(hello=HelloStanza)
    Interpreter(Evaluator()).execute(module, context)


if __name__ == "__main__":
    main()
