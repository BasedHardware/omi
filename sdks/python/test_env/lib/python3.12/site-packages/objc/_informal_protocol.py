__all__ = ("informal_protocol",)
import objc
import collections


# A mapping from a selector on a list of informal protocols
# implementing that selector.
#
# The current implementation only uses the last informal
# protocol that claims a selector.
_selToProtocolMapping = collections.defaultdict(list)


def _informal_protocol_for_selector(sel):
    if sel in _selToProtocolMapping:
        return _selToProtocolMapping[sel][-1]
    else:
        return None


class informal_protocol:
    __slots__ = ("__name__", "selectors")
    __module__ = "objc"

    def __init__(self, name, selectors):
        if not isinstance(name, str):
            raise TypeError(
                f"informal_protocol() argument 1 must be str, not {type(name).__name__}"
            )

        self.__name__ = name
        self.selectors = tuple(selectors)
        for idx, item in enumerate(self.selectors):
            if not isinstance(item, objc.selector):
                raise TypeError(f"Item {idx} is not a selector")
            if isinstance(item, objc.native_selector):
                raise TypeError(f"Item {idx} is a native selector")
            if item.callable is not None:
                raise TypeError(f"Item {idx} has a callable")

        for item in self.selectors:
            _selToProtocolMapping[item.selector].append(self)

    def __repr__(self):
        return f"<objc.informal_protocol {self.__name__!r} at 0x{hex(id(self))}>"

    def classMethods(self):
        """
        Return a list of all class methods that are part of this protocol
        """
        return [
            {
                "selector": sel.selector,
                "typestr": sel.signature,
                "required": sel.isRequired,
            }
            for sel in self.selectors
            if sel.isClassMethod
        ]

    def instanceMethods(self):
        """
        Return a list of all instance methods that are part of this protocol
        """
        return [
            {
                "selector": sel.selector,
                "typestr": sel.signature,
                "required": sel.isRequired,
            }
            for sel in self.selectors
            if not sel.isClassMethod
        ]
