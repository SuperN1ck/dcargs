"""Rules for taking high-level field definitions and lowering them into inputs for
argparse's `add_argument()`."""
from __future__ import annotations

import argparse
import dataclasses
import enum
import functools
import itertools
import shlex
from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import termcolor

from . import _fields, _instantiators, _resolver, _strings
from .conf import _markers

try:
    # Python >=3.8.
    from functools import cached_property
except ImportError:
    # Python 3.7.
    from backports.cached_property import cached_property  # type: ignore


class _PatchedList(list):
    """Custom tuple type, for avoiding "default not in choices" errors when the default
    is set to MISSING_NONPROP.

    This solves a choices error raised by argparse in a very specific edge case:
    literals in containers as positional arguments."""

    def __init__(self, li):
        super(_PatchedList, self).__init__(li)

    def __contains__(self, x: Any) -> bool:
        return list.__contains__(self, x) or x is _fields.MISSING_NONPROP


@dataclasses.dataclass(frozen=True)
class ArgumentDefinition:
    """Structure containing everything needed to define an argument."""

    prefix: str  # Prefix for nesting.
    field: _fields.FieldDefinition
    type_from_typevar: Dict[TypeVar, Type]

    def add_argument(
        self, parser: Union[argparse.ArgumentParser, argparse._ArgumentGroup]
    ) -> None:
        """Add a defined argument to a parser."""

        # Get keyword arguments, with None values removed.
        kwargs = dataclasses.asdict(self.lowered)
        kwargs.pop("instantiator")
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        name_or_flag = kwargs.pop("name_or_flag")
        if len(name_or_flag) == 0:
            name_or_flag = _strings.dummy_field_name

        # We're actually going to skip the default field: if an argument is unset, the
        # MISSING value will be detected in _calling.py and the field default will
        # directly be used. This helps reduce the likelihood of issues with converting
        # the field default to a string format, then back to the desired type.
        kwargs["default"] = _fields.MISSING_NONPROP

        if "choices" in kwargs:
            kwargs["choices"] = _PatchedList(kwargs["choices"])

        # Note that the name must be passed in as a position argument.
        parser.add_argument(name_or_flag, **kwargs)

    @cached_property
    def lowered(self) -> LoweredArgumentDefinition:
        """Lowered argument definition, generated by applying a sequence of rules."""
        rules = (
            _rule_handle_defaults,
            _rule_handle_boolean_flags,
            _rule_recursive_instantiator_from_type,
            _rule_convert_defaults_to_strings,
            _rule_generate_helptext,
            _rule_set_name_or_flag,
            _rule_positional_special_handling,
        )
        return functools.reduce(
            lambda lowered, rule: rule(self, lowered),
            rules,
            LoweredArgumentDefinition(),
        )


@dataclasses.dataclass(frozen=True)
class LoweredArgumentDefinition:
    """Contains fields meant to be passed directly into argparse."""

    # Action that is called on parsed arguments. This handles conversions from strings
    # to our desired types.
    #
    # The main reason we use this instead of the standard 'type' argument is to enable
    # mixed-type tuples.
    instantiator: Optional[_instantiators.Instantiator] = None

    def is_fixed(self) -> bool:
        """If the instantiator is set to `None`, even after all argument
        transformations, it means that we don't have a valid instantiator for an
        argument. We then mark the argument as 'fixed', with a value always equal to the
        field default."""
        return self.instantiator is None

    # From here on out, all fields correspond 1:1 to inputs to argparse's
    # add_argument() method.
    name_or_flag: str = ""
    default: Optional[Any] = None
    dest: Optional[str] = None
    required: bool = False
    action: Optional[str] = None
    nargs: Optional[Union[int, str]] = None
    choices: Optional[Set[Any]] = None
    # Note: unlike in vanilla argparse, our metavar is always a string. We handle
    # sequences, multiple arguments, etc, manually.
    metavar: Optional[str] = None
    help: Optional[str] = None


def _rule_handle_defaults(
    arg: ArgumentDefinition,
    lowered: LoweredArgumentDefinition,
) -> LoweredArgumentDefinition:
    """Set `required=True` if a default value is set."""

    # Mark lowered as required if a default is set.
    if arg.field.default in _fields.MISSING_SINGLETONS:
        return dataclasses.replace(lowered, default=None, required=True)

    return dataclasses.replace(lowered, default=arg.field.default)


def _rule_handle_boolean_flags(
    arg: ArgumentDefinition,
    lowered: LoweredArgumentDefinition,
) -> LoweredArgumentDefinition:
    if _resolver.apply_type_from_typevar(arg.field.typ, arg.type_from_typevar) is not bool:  # type: ignore
        return lowered

    if (
        arg.field.default in _fields.MISSING_SINGLETONS
        or arg.field.is_positional()
        or _markers.FLAG_CONVERSION_OFF in arg.field.markers
    ):
        # Treat bools as a normal parameter.
        return lowered
    elif arg.field.default is False:
        # Default `False` => --flag passed in flips to `True`.
        return dataclasses.replace(
            lowered,
            action="store_true",
            instantiator=lambda x: x,  # argparse will directly give us a bool!
        )
    elif arg.field.default is True:
        # Default `True` => --no-flag passed in flips to `False`.
        return dataclasses.replace(
            lowered,
            action="store_false",
            instantiator=lambda x: x,  # argparse will directly give us a bool!
        )

    assert False, (
        "Expected a boolean as a default for {arg.field.name}, but got"
        " {lowered.default}."
    )


def _rule_recursive_instantiator_from_type(
    arg: ArgumentDefinition,
    lowered: LoweredArgumentDefinition,
) -> LoweredArgumentDefinition:
    """The bulkiest bit: recursively analyze the type annotation and use it to determine
    how to instantiate it given some string from the commandline.

    Important: as far as argparse is concerned, all inputs are strings.

    Conversions from strings to our desired types happen in the instantiator; this is a
    bit more flexible, and lets us handle more complex types like enums and multi-type
    tuples."""
    if _markers.FIXED in arg.field.markers:
        return dataclasses.replace(
            lowered,
            instantiator=None,
            metavar=termcolor.colored("{fixed}", color="red"),
            required=False,
            default=_fields.MISSING_PROP,
        )
    if lowered.instantiator is not None:
        return lowered
    try:
        instantiator, metadata = _instantiators.instantiator_from_type(
            arg.field.typ,  # type: ignore
            arg.type_from_typevar,
        )
    except _instantiators.UnsupportedTypeAnnotationError as e:
        if arg.field.default in _fields.MISSING_SINGLETONS:
            raise _instantiators.UnsupportedTypeAnnotationError(
                "Unsupported type annotation for the field"
                f" {_strings.make_field_name([arg.prefix, arg.field.name])}. To"
                " suppress this error, assign the field a default value."
            ) from e
        else:
            # For fields with a default, we'll get by even if there's no instantiator
            # available.
            return dataclasses.replace(
                lowered,
                metavar=termcolor.colored("{fixed}", color="red"),
                required=False,
                default=_fields.MISSING_PROP,
            )

    return dataclasses.replace(
        lowered,
        instantiator=instantiator,
        choices=metadata.choices,
        nargs=metadata.nargs,
        metavar=metadata.metavar,
    )


def _rule_convert_defaults_to_strings(
    arg: ArgumentDefinition,
    lowered: LoweredArgumentDefinition,
) -> LoweredArgumentDefinition:
    """Sets all default values to strings, as required as input to our instantiator
    functions. Special-cased for enums."""

    def as_str(x: Any) -> Tuple[str, ...]:
        if isinstance(x, str):
            return (x,)
        elif isinstance(x, enum.Enum):
            return (x.name,)
        elif isinstance(x, Mapping):
            return tuple(itertools.chain(*map(as_str, itertools.chain(*x.items()))))
        elif isinstance(x, Sequence):
            return tuple(itertools.chain(*map(as_str, x)))
        else:
            return (str(x),)

    if (
        lowered.default is None
        or lowered.default in _fields.MISSING_SINGLETONS
        or lowered.action is not None
    ):
        return lowered
    else:
        return dataclasses.replace(lowered, default=as_str(lowered.default))


def _rule_generate_helptext(
    arg: ArgumentDefinition,
    lowered: LoweredArgumentDefinition,
) -> LoweredArgumentDefinition:
    """Generate helptext from docstring, argument name, default values."""

    # If the suppress marker is attached, hide the argument.
    if _markers.SUPPRESS in arg.field.markers:
        return dataclasses.replace(lowered, help=argparse.SUPPRESS)

    help_parts = []

    docstring_help = arg.field.helptext

    if docstring_help is not None and docstring_help != "":
        # Note that the percent symbol needs some extra handling in argparse.
        # https://stackoverflow.com/questions/21168120/python-argparse-errors-with-in-help-string
        docstring_help = docstring_help.replace("%", "%%")
        help_parts.append(docstring_help)

    default = lowered.default
    if lowered.is_fixed():
        # For fixed args, we'll be missing the lowered default. Use field default
        # instead.
        assert default in _fields.MISSING_SINGLETONS
        default = arg.field.default

    if not lowered.required:
        # Include default value in helptext. We intentionally don't use the % template
        # because the types of all arguments are set to strings, which will cause the
        # default to be casted to a string and introduce extra quotation marks.
        if lowered.instantiator is None:
            # Intentionally not quoted via shlex, since this can't actually be passed
            # in via the commandline.
            default_text = f"(fixed to: {str(arg.field.default)})"
        elif lowered.action == "store_true":
            default_text = f"(sets: {arg.field.name}=True)"
        elif lowered.action == "store_false":
            default_text = f"(sets: {arg.field.name}=False)"
        elif arg.field.default is _fields.EXCLUDE_FROM_CALL:
            default_text = "(unset by default)"
        elif lowered.nargs is not None and hasattr(default, "__iter__"):
            # For tuple types, we might have default as (0, 1, 2, 3).
            # For list types, we might have default as [0, 1, 2, 3].
            # For set types, we might have default as {0, 1, 2, 3}.
            #
            # In all cases, we want to display (default: 0 1 2 3), for consistency with
            # the format that argparse expects when we set nargs.
            assert default is not None  # Just for type checker.
            default_parts = map(shlex.quote, map(str, default))
            default_text = f"(default: {' '.join(default_parts)})"
        else:
            default_text = f"(default: {shlex.quote(str(default))})"
        help_parts.append(termcolor.colored(default_text, attrs=["dark"]))
    else:
        help_parts.append(termcolor.colored("(required)", color="red", attrs=["bold"]))

    return dataclasses.replace(lowered, help=" ".join(help_parts))


def _rule_set_name_or_flag(
    arg: ArgumentDefinition,
    lowered: LoweredArgumentDefinition,
) -> LoweredArgumentDefinition:
    if arg.field.is_positional():
        name_or_flag = _strings.make_field_name([arg.prefix, arg.field.name])
    elif lowered.action == "store_false":
        name_or_flag = "--" + _strings.make_field_name(
            [arg.prefix, "no-" + arg.field.name]
        )
    else:
        name_or_flag = "--" + _strings.make_field_name([arg.prefix, arg.field.name])

    return dataclasses.replace(
        lowered,
        name_or_flag=name_or_flag,
        dest=_strings.make_field_name([arg.prefix, arg.field.name]),
    )


def _rule_positional_special_handling(
    arg: ArgumentDefinition,
    lowered: LoweredArgumentDefinition,
) -> LoweredArgumentDefinition:
    if not arg.field.is_positional():
        return lowered

    metavar = lowered.metavar
    if lowered.required:
        nargs = lowered.nargs
    else:
        if metavar is not None:
            metavar = "[" + metavar + "]"
        if lowered.nargs == 1:
            # Optional positional arguments. Note that this needs to be special-cased in
            # _calling.py.
            nargs = "?"
        else:
            # If lowered.nargs is either + or an int.
            nargs = "*"

    return dataclasses.replace(
        lowered,
        dest=None,
        required=None,  # Can't be passed in for positionals.
        metavar=metavar,
        nargs=nargs,
    )
