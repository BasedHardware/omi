from objc import _objc

__all__ = ["protocolNamed", "ProtocolError"]


class ProtocolError(_objc.error):
    __module__ = "objc"


PROTOCOL_CACHE = {}


def protocolNamed(name):
    """
    Returns a Protocol object for the named protocol. This is the
    equivalent of @protocol(name) in Objective-C.
    Raises objc.ProtocolError when the protocol does not exist.
    """
    try:
        return PROTOCOL_CACHE[name]
    except KeyError:
        pass
    for p in _objc.protocolsForProcess():
        pname = p.__name__
        PROTOCOL_CACHE.setdefault(pname, p)
        if pname == name:
            return p
    for cls in _objc.getClassList(True):
        for p in _objc.protocolsForClass(cls):
            pname = p.__name__
            PROTOCOL_CACHE.setdefault(pname, p)
            if pname == name:
                return p
    raise ProtocolError(f"protocol {name!r} does not exist", name)
