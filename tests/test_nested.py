import dataclasses
from typing import Any, Generic, Mapping, Optional, Tuple, TypeVar, Union

import pytest
from frozendict import frozendict  # type: ignore
from typing_extensions import Annotated

import dcargs


def test_nested():
    @dataclasses.dataclass
    class B:
        y: int

    @dataclasses.dataclass
    class Nested:
        x: int
        b: B

    assert dcargs.cli(Nested, args=["--x", "1", "--b.y", "3"]) == Nested(x=1, b=B(y=3))
    with pytest.raises(SystemExit):
        dcargs.cli(Nested, args=["--x", "1"])


def test_nested_annotated():
    @dataclasses.dataclass
    class B:
        y: int

    @dataclasses.dataclass
    class Nested:
        x: int
        b: Annotated[B, "this should be ignored"]

    assert dcargs.cli(Nested, args=["--x", "1", "--b.y", "3"]) == Nested(x=1, b=B(y=3))
    with pytest.raises(SystemExit):
        dcargs.cli(Nested, args=["--x", "1"])


def test_nested_accidental_underscores():
    @dataclasses.dataclass
    class B:
        arg_name: str

    @dataclasses.dataclass
    class Nested:
        x: int
        child_struct: B

    assert (
        dcargs.cli(Nested, args=["--x", "1", "--child-struct.arg-name", "three_five"])
        == dcargs.cli(
            Nested, args=["--x", "1", "--child_struct.arg_name", "three_five"]
        )
        == dcargs.cli(
            Nested, args=["--x", "1", "--child_struct.arg-name", "three_five"]
        )
        == dcargs.cli(Nested, args=["--x", "1", "--child_struct.arg_name=three_five"])
        == Nested(x=1, child_struct=B(arg_name="three_five"))
    )
    with pytest.raises(SystemExit):
        dcargs.cli(Nested, args=["--x", "1"])


def test_nested_default():
    @dataclasses.dataclass
    class B:
        y: int = 1

    @dataclasses.dataclass
    class Nested:
        x: int = 2
        b: B = B()

    assert dcargs.cli(Nested, args=[], default=Nested(x=1, b=B(y=2))) == Nested(
        x=1, b=B(y=2)
    )


def test_nested_default_alternate():
    @dataclasses.dataclass
    class B:
        y: int = 3

    @dataclasses.dataclass
    class Nested:
        x: int
        b: B

    assert (
        Nested(x=1, b=B(y=3))
        == dcargs.cli(Nested, args=["--x", "1", "--b.y", "3"])
        == dcargs.cli(Nested, args=[], default=Nested(x=1, b=B(y=3)))
    )
    assert dcargs.cli(Nested, args=["--x", "1"]) == Nested(x=1, b=B(y=3))


def test_default_nested():
    @dataclasses.dataclass(frozen=True)
    class B:
        y: int = 3

    @dataclasses.dataclass(frozen=True)
    class Nested:
        x: int
        b: B = B(y=5)

    assert dcargs.cli(Nested, args=["--x", "1", "--b.y", "3"]) == Nested(x=1, b=B(y=3))
    assert dcargs.cli(Nested, args=["--x", "1"]) == Nested(x=1, b=B(y=5))


def test_double_default_nested():
    @dataclasses.dataclass(frozen=True)
    class Child:
        y: int

    @dataclasses.dataclass(frozen=True)
    class Parent:
        c: Child

    @dataclasses.dataclass(frozen=True)
    class Grandparent:
        x: int
        b: Parent = Parent(Child(y=5))

    assert dcargs.cli(Grandparent, args=["--x", "1", "--b.c.y", "3"]) == Grandparent(
        x=1, b=Parent(Child(y=3))
    )
    assert dcargs.cli(Grandparent, args=["--x", "1"]) == Grandparent(
        x=1, b=Parent(Child(y=5))
    )


def test_default_factory_nested():
    @dataclasses.dataclass
    class B:
        y: int = 3

    @dataclasses.dataclass
    class Nested:
        x: int
        b: B = dataclasses.field(default_factory=lambda: B(y=5))

    assert dcargs.cli(Nested, args=["--x", "1", "--b.y", "3"]) == Nested(x=1, b=B(y=3))
    assert dcargs.cli(Nested, args=["--x", "1"]) == Nested(x=1, b=B(y=5))


def test_optional_nested():
    @dataclasses.dataclass
    class OptionalNestedChild:
        y: int
        z: int

    @dataclasses.dataclass
    class OptionalNested:
        x: int
        b: Optional[OptionalNestedChild] = None

    assert dcargs.cli(OptionalNested, args=["--x", "1"]) == OptionalNested(x=1, b=None)
    with pytest.raises(SystemExit):
        dcargs.cli(
            OptionalNested, args=["--x", "1", "b:optional-nested-child", "--b.y", "3"]
        )
    with pytest.raises(SystemExit):
        dcargs.cli(
            OptionalNested, args=["--x", "1", "b:optional-nested-child", "--b.z", "3"]
        )

    assert dcargs.cli(
        OptionalNested,
        args=["--x", "1", "b:optional-nested-child", "--b.y", "2", "--b.z", "3"],
    ) == OptionalNested(x=1, b=OptionalNestedChild(y=2, z=3))


def test_subparser():
    @dataclasses.dataclass
    class HTTPServer:
        y: int

    @dataclasses.dataclass
    class SMTPServer:
        z: int

    @dataclasses.dataclass
    class Subparser:
        x: int
        bc: Union[HTTPServer, SMTPServer]

    assert dcargs.cli(
        Subparser, args=["--x", "1", "bc:http-server", "--bc.y", "3"]
    ) == Subparser(x=1, bc=HTTPServer(y=3))
    assert dcargs.cli(
        Subparser, args=["--x", "1", "bc:smtp-server", "--bc.z", "3"]
    ) == Subparser(x=1, bc=SMTPServer(z=3))

    with pytest.raises(SystemExit):
        # Missing subcommand.
        dcargs.cli(Subparser, args=["--x", "1"])
    with pytest.raises(SystemExit):
        # Wrong field.
        dcargs.cli(Subparser, args=["--x", "1", "bc:http-server", "--bc.z", "3"])
    with pytest.raises(SystemExit):
        # Wrong field.
        dcargs.cli(Subparser, args=["--x", "1", "bc:smtp-server", "--bc.y", "3"])


def test_subparser_root():
    @dataclasses.dataclass
    class HTTPServer:
        y: int

    @dataclasses.dataclass
    class SMTPServer:
        z: int

    @dataclasses.dataclass
    class Subparser:
        x: int
        bc: Union[HTTPServer, SMTPServer]

    assert dcargs.cli(
        Union[HTTPServer, SMTPServer], args=["http-server", "--y", "3"]  # type: ignore
    ) == HTTPServer(y=3)


def test_subparser_with_default():
    @dataclasses.dataclass
    class DefaultHTTPServer:
        y: int

    @dataclasses.dataclass
    class DefaultSMTPServer:
        z: int

    @dataclasses.dataclass
    class DefaultSubparser:
        x: int
        bc: Union[DefaultHTTPServer, DefaultSMTPServer] = dataclasses.field(
            default_factory=lambda: DefaultHTTPServer(5)
        )

    assert (
        dcargs.cli(
            DefaultSubparser, args=["--x", "1", "bc:default-http-server", "--bc.y", "5"]
        )
        == dcargs.cli(DefaultSubparser, args=["--x", "1"])
        == DefaultSubparser(x=1, bc=DefaultHTTPServer(y=5))
    )
    assert dcargs.cli(
        DefaultSubparser, args=["--x", "1", "bc:default-smtp-server", "--bc.z", "3"]
    ) == DefaultSubparser(x=1, bc=DefaultSMTPServer(z=3))
    assert (
        dcargs.cli(
            DefaultSubparser, args=["--x", "1", "bc:default-http-server", "--bc.y", "8"]
        )
        == dcargs.cli(
            DefaultSubparser,
            args=[],
            default=DefaultSubparser(x=1, bc=DefaultHTTPServer(y=8)),
        )
        == DefaultSubparser(x=1, bc=DefaultHTTPServer(y=8))
    )

    with pytest.raises(SystemExit):
        dcargs.cli(DefaultSubparser, args=["--x", "1", "b", "--bc.z", "3"])
    with pytest.raises(SystemExit):
        dcargs.cli(DefaultSubparser, args=["--x", "1", "c", "--bc.y", "3"])


def test_subparser_with_default_alternate():
    @dataclasses.dataclass
    class DefaultInstanceHTTPServer:
        y: int = 0

    @dataclasses.dataclass
    class DefaultInstanceSMTPServer:
        z: int = 0

    @dataclasses.dataclass
    class DefaultInstanceSubparser:
        x: int
        bc: Union[DefaultInstanceHTTPServer, DefaultInstanceSMTPServer]

    assert (
        dcargs.cli(
            DefaultInstanceSubparser,
            args=["--x", "1", "bc:default-instance-http-server", "--bc.y", "5"],
        )
        == dcargs.cli(
            DefaultInstanceSubparser,
            args=[],
            default=DefaultInstanceSubparser(x=1, bc=DefaultInstanceHTTPServer(y=5)),
        )
        == dcargs.cli(
            DefaultInstanceSubparser,
            args=["bc:default-instance-http-server"],
            default=DefaultInstanceSubparser(x=1, bc=DefaultInstanceHTTPServer(y=5)),
        )
        == DefaultInstanceSubparser(x=1, bc=DefaultInstanceHTTPServer(y=5))
    )
    assert dcargs.cli(
        DefaultInstanceSubparser,
        args=["bc:default-instance-smtp-server", "--bc.z", "3"],
        default=DefaultInstanceSubparser(x=1, bc=DefaultInstanceHTTPServer(y=5)),
    ) == DefaultInstanceSubparser(x=1, bc=DefaultInstanceSMTPServer(z=3))
    assert (
        dcargs.cli(
            DefaultInstanceSubparser,
            args=["--x", "1", "bc:default-instance-http-server", "--bc.y", "8"],
        )
        == dcargs.cli(
            DefaultInstanceSubparser,
            args=[],
            default=DefaultInstanceSubparser(x=1, bc=DefaultInstanceHTTPServer(y=8)),
        )
        == DefaultInstanceSubparser(x=1, bc=DefaultInstanceHTTPServer(y=8))
    )

    with pytest.raises(SystemExit):
        dcargs.cli(DefaultInstanceSubparser, args=["--x", "1", "b", "--bc.z", "3"])
    with pytest.raises(SystemExit):
        dcargs.cli(DefaultInstanceSubparser, args=["--x", "1", "c", "--bc.y", "3"])


def test_optional_subparser():
    @dataclasses.dataclass
    class OptionalHTTPServer:
        y: int

    @dataclasses.dataclass
    class OptionalSMTPServer:
        z: int

    @dataclasses.dataclass
    class OptionalSubparser:
        x: int
        bc: Optional[Union[OptionalHTTPServer, OptionalSMTPServer]]

    assert dcargs.cli(
        OptionalSubparser, args=["--x", "1", "bc:optional-http-server", "--bc.y", "3"]
    ) == OptionalSubparser(x=1, bc=OptionalHTTPServer(y=3))
    assert dcargs.cli(
        OptionalSubparser, args=["--x", "1", "bc:optional-smtp-server", "--bc.z", "3"]
    ) == OptionalSubparser(x=1, bc=OptionalSMTPServer(z=3))
    assert dcargs.cli(
        OptionalSubparser, args=["--x", "1", "bc:None"]
    ) == OptionalSubparser(x=1, bc=None)

    with pytest.raises(SystemExit):
        # Wrong field.
        dcargs.cli(
            OptionalSubparser,
            args=["--x", "1", "bc:optional-http-server", "--bc.z", "3"],
        )
    with pytest.raises(SystemExit):
        # Wrong field.
        dcargs.cli(
            OptionalSubparser,
            args=["--x", "1", "bc:optional-smtp-server", "--bc.y", "3"],
        )


def test_post_init_default():
    @dataclasses.dataclass
    class DataclassWithDynamicDefault:
        x: int = 3
        y: Optional[int] = None

        def __post_init__(self):
            # If unspecified, set y = x.
            if self.y is None:
                self.y = self.x

    @dataclasses.dataclass
    class NoDefaultPostInitArgs:
        inner: DataclassWithDynamicDefault

    @dataclasses.dataclass
    class DefaultFactoryPostInitArgs:
        inner: DataclassWithDynamicDefault = dataclasses.field(
            default_factory=DataclassWithDynamicDefault
        )

    assert (
        dcargs.cli(NoDefaultPostInitArgs, args=["--inner.x", "5"]).inner
        == dcargs.cli(DefaultFactoryPostInitArgs, args=["--inner.x", "5"]).inner
        == DataclassWithDynamicDefault(x=5, y=5)
    )


def test_multiple_subparsers():
    @dataclasses.dataclass
    class Subcommand1:
        x: int = 0

    @dataclasses.dataclass
    class Subcommand2:
        y: int = 1

    @dataclasses.dataclass
    class Subcommand3:
        z: int = 2

    @dataclasses.dataclass
    class MultipleSubparsers:
        a: Union[Subcommand1, Subcommand2, Subcommand3]
        b: Union[Subcommand1, Subcommand2, Subcommand3]
        c: Union[Subcommand1, Subcommand2, Subcommand3]

    with pytest.raises(SystemExit):
        dcargs.cli(MultipleSubparsers, args=[])

    assert dcargs.cli(
        MultipleSubparsers, args="a:subcommand1 b:subcommand2 c:subcommand3".split(" ")
    ) == MultipleSubparsers(Subcommand1(), Subcommand2(), Subcommand3())

    assert dcargs.cli(
        MultipleSubparsers,
        args="a:subcommand1 --a.x 5 b:subcommand2 --b.y 7 c:subcommand3 --c.z 3".split(
            " "
        ),
    ) == MultipleSubparsers(Subcommand1(x=5), Subcommand2(y=7), Subcommand3(z=3))

    assert dcargs.cli(
        MultipleSubparsers,
        args="a:subcommand2 --a.y 5 b:subcommand1 --b.x 7 c:subcommand3 --c.z 3".split(
            " "
        ),
    ) == MultipleSubparsers(Subcommand2(y=5), Subcommand1(x=7), Subcommand3(z=3))

    assert dcargs.cli(
        MultipleSubparsers,
        args="a:subcommand3 --a.z 5 b:subcommand1 --b.x 7 c:subcommand3 --c.z 3".split(
            " "
        ),
    ) == MultipleSubparsers(Subcommand3(z=5), Subcommand1(x=7), Subcommand3(z=3))


def test_multiple_subparsers_with_default():
    @dataclasses.dataclass(frozen=True)
    class Subcommand1:
        x: int = 0

    @dataclasses.dataclass(frozen=True)
    class Subcommand2:
        y: int = 1

    @dataclasses.dataclass(frozen=True)
    class Subcommand3:
        z: int = 2

    @dataclasses.dataclass
    class MultipleSubparsers:
        a: Union[Subcommand1, Subcommand2, Subcommand3] = Subcommand1(dcargs.MISSING)
        b: Union[Subcommand1, Subcommand2, Subcommand3] = Subcommand2(7)
        c: Union[Subcommand1, Subcommand2, Subcommand3] = Subcommand3(3)

    with pytest.raises(SystemExit):
        dcargs.cli(
            MultipleSubparsers,
            args=[],
        )

    assert dcargs.cli(
        MultipleSubparsers,
        args=["a:subcommand1", "--a.x", "5"],
    ) == MultipleSubparsers(Subcommand1(x=5), Subcommand2(y=7), Subcommand3(z=3))

    assert dcargs.cli(
        MultipleSubparsers,
        args="a:subcommand1 --a.x 3".split(" "),
    ) == MultipleSubparsers(Subcommand1(x=3), Subcommand2(y=7), Subcommand3(z=3))

    with pytest.raises(SystemExit):
        dcargs.cli(
            MultipleSubparsers,
            args=[],
            default=MultipleSubparsers(
                Subcommand1(),
                Subcommand2(),
                Subcommand3(dcargs.MISSING),
            ),
        )
    with pytest.raises(SystemExit):
        dcargs.cli(
            MultipleSubparsers,
            args=[
                "a:subcommand1",
            ],
            default=MultipleSubparsers(
                Subcommand1(),
                Subcommand2(),
                Subcommand3(dcargs.MISSING),
            ),
        )
    with pytest.raises(SystemExit):
        dcargs.cli(
            MultipleSubparsers,
            args=["a:subcommand1", "b:subcommand2"],
            default=MultipleSubparsers(
                Subcommand1(),
                Subcommand2(),
                Subcommand3(dcargs.MISSING),
            ),
        )
    with pytest.raises(SystemExit):
        dcargs.cli(
            MultipleSubparsers,
            args=["a:subcommand1", "b:subcommand2", "c:subcommand3"],
            default=MultipleSubparsers(
                Subcommand1(),
                Subcommand2(),
                Subcommand3(dcargs.MISSING),
            ),
        )
    assert dcargs.cli(
        MultipleSubparsers,
        args=["a:subcommand1", "b:subcommand2", "c:subcommand3", "--c.z", "3"],
        default=MultipleSubparsers(
            Subcommand1(),
            Subcommand2(),
            Subcommand3(dcargs.MISSING),
        ),
    ) == MultipleSubparsers(Subcommand1(x=0), Subcommand2(y=1), Subcommand3(z=3))
    assert dcargs.cli(
        MultipleSubparsers,
        args=["a:subcommand1", "b:subcommand2", "c:subcommand2"],
        default=MultipleSubparsers(
            Subcommand1(),
            Subcommand2(),
            Subcommand3(dcargs.MISSING),
        ),
    ) == MultipleSubparsers(Subcommand1(x=0), Subcommand2(y=1), Subcommand2(y=1))


def test_nested_subparsers_with_default():
    @dataclasses.dataclass(frozen=True)
    class Subcommand1:
        x: int = 0

    @dataclasses.dataclass(frozen=True)
    class Subcommand3:
        z: int = 2

    @dataclasses.dataclass(frozen=True)
    class Subcommand2:
        y: Union[Subcommand1, Subcommand3]

    @dataclasses.dataclass(frozen=True)
    class MultipleSubparsers:
        a: Union[Subcommand1, Subcommand2] = Subcommand2(Subcommand1(dcargs.MISSING))

    with pytest.raises(SystemExit):
        dcargs.cli(MultipleSubparsers, args=[])
    with pytest.raises(SystemExit):
        dcargs.cli(MultipleSubparsers, args=["a:subcommand2"])

    assert dcargs.cli(
        MultipleSubparsers, args="a:subcommand1 --a.x 3".split(" ")
    ) == MultipleSubparsers(Subcommand1(3))
    assert dcargs.cli(
        MultipleSubparsers, args="a:subcommand2 a.y:subcommand3 --a.y.z 2".split(" ")
    ) == MultipleSubparsers(Subcommand2(Subcommand3()))
    assert dcargs.cli(
        MultipleSubparsers, args="a:subcommand2 a.y:subcommand3 --a.y.z 7".split(" ")
    ) == MultipleSubparsers(Subcommand2(Subcommand3(7)))
    assert dcargs.cli(
        MultipleSubparsers, args="a:subcommand2 a.y:subcommand1 --a.y.x 7".split(" ")
    ) == MultipleSubparsers(Subcommand2(Subcommand1(7)))


def test_nested_subparsers_multiple():
    @dataclasses.dataclass(frozen=True)
    class Subcommand1:
        x: int = 0

    @dataclasses.dataclass(frozen=True)
    class Subcommand3:
        z: int = 2

    @dataclasses.dataclass(frozen=True)
    class Subcommand2:
        y: Union[Subcommand1, Subcommand3]

    @dataclasses.dataclass(frozen=True)
    class MultipleSubparsers:
        a: Union[Subcommand1, Subcommand2]
        b: Union[Subcommand1, Subcommand2]

    with pytest.raises(SystemExit):
        dcargs.cli(MultipleSubparsers, args=[])
    assert dcargs.cli(
        MultipleSubparsers, args="a:subcommand1 b:subcommand1".split(" ")
    ) == MultipleSubparsers(Subcommand1(), Subcommand1())
    assert dcargs.cli(
        MultipleSubparsers,
        args="a:subcommand1 b:subcommand2 b.y:subcommand1".split(" "),
    ) == MultipleSubparsers(Subcommand1(), Subcommand2(Subcommand1()))
    assert dcargs.cli(
        MultipleSubparsers,
        args="a:subcommand2 a.y:subcommand1 b:subcommand2 b.y:subcommand1".split(" "),
    ) == MultipleSubparsers(Subcommand2(Subcommand1()), Subcommand2(Subcommand1()))
    assert dcargs.cli(
        MultipleSubparsers,
        args=(
            "a:subcommand2 a.y:subcommand1 --a.y.x 3 b:subcommand2 b.y:subcommand1"
            " --b.y.x 7".split(" ")
        ),
    ) == MultipleSubparsers(Subcommand2(Subcommand1(3)), Subcommand2(Subcommand1(7)))


def test_tuple_nesting():
    @dataclasses.dataclass(frozen=True)
    class Color:
        r: int
        g: int
        b: int

    @dataclasses.dataclass(frozen=True)
    class Location:
        x: float
        y: float
        z: float

    def main(x: Tuple[Tuple[Color], Location, float]):
        return x

    assert dcargs.cli(
        main,
        args=(
            "--x.0.0.r 255 --x.0.0.g 0 --x.0.0.b 0 --x.1.x 5.0 --x.1.y 0.0"
            " --x.1.z 2.0 --x.2 4.0".split(" ")
        ),
    ) == ((Color(255, 0, 0),), Location(5.0, 0.0, 2.0), 4.0)


def test_generic_subparsers():
    T = TypeVar("T")

    @dataclasses.dataclass
    class A(Generic[T]):
        x: T

    def main(x: Union[A[int], A[float]]) -> Any:
        return x

    assert dcargs.cli(main, args="x:a-float --x.x 3.2".split(" ")) == A(3.2)
    assert dcargs.cli(main, args="x:a-int --x.x 3".split(" ")) == A(3)

    def main_with_default(x: Union[A[int], A[float]] = A(5)) -> Any:
        return x

    with pytest.raises(dcargs.UnsupportedTypeAnnotationError):
        dcargs.cli(main_with_default, args=[])


def test_generic_inherited():
    class UnrelatedParentClass:
        pass

    T = TypeVar("T")

    @dataclasses.dataclass
    class ActualParentClass(Generic[T]):
        x: T  # Documentation 1

        # Documentation 2
        y: T

        z: T = 3  # type: ignore
        """Documentation 3"""

    @dataclasses.dataclass
    class ChildClass(UnrelatedParentClass, ActualParentClass[int]):
        pass

    assert dcargs.cli(
        ChildClass, args=["--x", "1", "--y", "2", "--z", "3"]
    ) == ChildClass(x=1, y=2, z=3)


def test_subparser_in_nested():
    @dataclasses.dataclass
    class A:
        a: int

    @dataclasses.dataclass
    class B:
        b: int

    @dataclasses.dataclass
    class Nested2:
        subcommand: Union[A, B]

    @dataclasses.dataclass
    class Nested1:
        nested2: Nested2

    @dataclasses.dataclass
    class Parent:
        nested1: Nested1

    assert dcargs.cli(
        Parent,
        args="nested1.nested2.subcommand:a --nested1.nested2.subcommand.a 3".split(" "),
    ) == Parent(Nested1(Nested2(A(3))))
    assert dcargs.cli(
        Parent,
        args="nested1.nested2.subcommand:b --nested1.nested2.subcommand.b 7".split(" "),
    ) == Parent(Nested1(Nested2(B(7))))


def test_frozen_dict():
    def main(
        x: Mapping[str, float] = frozendict(
            {
                "num_epochs": 20,
                "batch_size": 64,
            }
        )
    ):
        return x

    assert hash(dcargs.cli(main, args="--x.num-epochs 10".split(" "))) == hash(
        frozendict({"num_epochs": 10, "batch_size": 64})
    )


def test_nested_in_subparser():
    # https://github.com/brentyi/dcargs/issues/9
    @dataclasses.dataclass(frozen=True)
    class Subtype:
        data: int = 1

    @dataclasses.dataclass(frozen=True)
    class TypeA:
        subtype: Subtype = Subtype(1)

    @dataclasses.dataclass(frozen=True)
    class TypeB:
        subtype: Subtype = Subtype(2)

    @dataclasses.dataclass(frozen=True)
    class Wrapper:
        supertype: Union[TypeA, TypeB] = TypeA()

    assert dcargs.cli(Wrapper, args=[]) == Wrapper()
    assert (
        dcargs.cli(
            Wrapper, args="supertype:type-a --supertype.subtype.data 1".split(" ")
        )
        == Wrapper()
    )
