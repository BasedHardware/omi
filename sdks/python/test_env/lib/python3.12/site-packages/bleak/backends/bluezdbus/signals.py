# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Coroutine, Dict, Optional

from dbus_fast.aio.message_bus import MessageBus
from dbus_fast.errors import InvalidObjectPathError
from dbus_fast.message import Message
from dbus_fast.validators import (
    assert_interface_name_valid,
    assert_member_name_valid,
    assert_object_path_valid,
)

# TODO: this stuff should be improved and submitted upstream to dbus-next
# https://github.com/altdesktop/python-dbus-next/issues/53

_message_types = ["signal", "method_call", "method_return", "error"]


class InvalidMessageTypeError(TypeError):
    def __init__(self, type: str):
        super().__init__(f"invalid message type: {type}")


def is_message_type_valid(type: str) -> bool:
    """Whether this is a valid message type.

    .. seealso:: https://dbus.freedesktop.org/doc/dbus-specification.html#message-bus-routing-match-rules

    :param type: The message type to validate.
    :type name: str

    :returns: Whether the name is a valid message type.
    :rtype: bool
    """
    return type in _message_types


def assert_bus_name_valid(type: str) -> None:
    """Raise an error if this is not a valid message type.

    .. seealso:: https://dbus.freedesktop.org/doc/dbus-specification.html#message-bus-routing-match-rules

    :param type: The message type to validate.
    :type name: str

    :raises:
        - :class:`InvalidMessageTypeError` - If this is not a valid message type.
    """
    if not is_message_type_valid(type):
        raise InvalidMessageTypeError(type)


class MatchRules:
    """D-Bus signal match rules.

    .. seealso:: https://dbus.freedesktop.org/doc/dbus-specification.html#message-bus-routing-match-rules
    """

    def __init__(
        self,
        type: str = "signal",
        sender: Optional[str] = None,
        interface: Optional[str] = None,
        member: Optional[str] = None,
        path: Optional[str] = None,
        path_namespace: Optional[str] = None,
        destination: Optional[str] = None,
        arg0namespace: Optional[str] = None,
        **kwargs,
    ):
        assert_bus_name_valid(type)
        self.type: str = type

        if sender:
            assert_bus_name_valid(sender)
            self.sender: str = sender
        else:
            self.sender = None

        if interface:
            assert_interface_name_valid(interface)
            self.interface: str = interface
        else:
            self.interface = None

        if member:
            assert_member_name_valid(member)
            self.member: str = member
        else:
            self.member = None

        if path:
            assert_object_path_valid(path)
            self.path: str = path
        else:
            self.path = None

        if path_namespace:
            assert_object_path_valid(path_namespace)
            self.path_namespace: str = path_namespace
        else:
            self.path_namespace = None

        if path and path_namespace:
            raise TypeError(
                "message rules cannot have both 'path' and 'path_namespace' at the same time"
            )

        if destination:
            assert_bus_name_valid(destination)
            self.destination: str = destination
        else:
            self.destination = None

        if arg0namespace:
            assert_bus_name_valid(arg0namespace)
            self.arg0namespace: str = arg0namespace
        else:
            self.arg0namespace = None

        if kwargs:
            for k, v in kwargs.items():
                if re.match(r"^arg\d+$", k):
                    if not isinstance(v, str):
                        raise TypeError(f"kwarg '{k}' must have a str value")
                elif re.match(r"^arg\d+path$", k):
                    if not isinstance(v, str):
                        raise InvalidObjectPathError(v)
                    assert_object_path_valid(v[:-1] if v.endswith("/") else v)
                else:
                    raise ValueError("kwargs must be in the form 'arg0' or 'arg0path'")
            self.args: Dict[str, str] = kwargs
        else:
            self.args = None

    @staticmethod
    def parse(rules: str) -> MatchRules:
        return MatchRules(**dict(r.split("=") for r in rules.split(",")))

    def __str__(self) -> str:
        rules = [f"type={self.type}"]

        if self.sender:
            rules.append(f"sender={self.sender}")

        if self.interface:
            rules.append(f"interface={self.interface}")

        if self.member:
            rules.append(f"member={self.member}")

        if self.path:
            rules.append(f"path={self.path}")

        if self.path_namespace:
            rules.append(f"path_namespace={self.path_namespace}")

        if self.destination:
            rules.append(f"destination={self.destination}")

        if self.args:
            for k, v in self.args.items():
                rules.append(f"{k}={v}")

        if self.arg0namespace:
            rules.append(f"arg0namespace={self.arg0namespace}")

        return ",".join(rules)

    def __repr__(self) -> str:
        return f"MatchRules({self})"


def add_match(bus: MessageBus, rules: MatchRules) -> Coroutine[Any, Any, Message]:
    """Calls org.freedesktop.DBus.AddMatch using ``rules``."""
    return bus.call(
        Message(
            destination="org.freedesktop.DBus",
            interface="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            member="AddMatch",
            signature="s",
            body=[str(rules)],
        )
    )


def remove_match(bus: MessageBus, rules: MatchRules) -> Coroutine[Any, Any, Message]:
    """Calls org.freedesktop.DBus.RemoveMatch using ``rules``."""
    return bus.call(
        Message(
            destination="org.freedesktop.DBus",
            interface="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            member="RemoveMatch",
            signature="s",
            body=[str(rules)],
        )
    )
