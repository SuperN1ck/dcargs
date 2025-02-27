"""`typing.Literal[]` can be used to restrict inputs to a fixed set of literal choices;
`typing.Union[]` can be used to restrict inputs to a fixed set of types.

Usage:
`python ./06_literals_and_unions.py --help`
"""

import dataclasses
import enum
from typing import Literal, Optional, Tuple, Union

import dcargs


class Color(enum.Enum):
    RED = enum.auto()
    GREEN = enum.auto()
    BLUE = enum.auto()


@dataclasses.dataclass(frozen=True)
class Args:
    # We can use Literal[] to restrict the set of allowable inputs, for example, over
    # enums.
    restricted_enum: Literal[Color.RED, Color.GREEN] = Color.RED

    # Or mix them with other types!
    mixed: Literal[Color.RED, Color.GREEN, "blue"] = "blue"

    # Literals can also be marked Optional.
    integer: Optional[Literal[0, 1, 2, 3]] = None

    # Unions can be used to specify multiple allowable types.
    union_over_types: Union[int, str] = 0
    string_or_enum: Union[Literal["red", "green"], Color] = "red"

    # Unions also work over more complex nested types.
    union_over_tuples: Union[Tuple[int, int], Tuple[str]] = ("1",)

    # And can be nested in other types.
    tuple_of_string_or_enum: Tuple[Union[Literal["red", "green"], Color], ...] = (
        "red",
        Color.RED,
    )


if __name__ == "__main__":
    args = dcargs.cli(Args)
    print(args)
