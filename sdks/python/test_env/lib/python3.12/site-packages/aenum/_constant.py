from ._common import *

__all__ = [
       	'NamedConstant', 'Constant',
        ]

# NamedConstant

NamedConstant = None

class NamedConstantDict(dict):
    """Track constant order and ensure names are not reused.

    NamedConstantMeta will use the names found in self._names as the
    Constant names.
    """
    def __init__(self):
        super(NamedConstantDict, self).__init__()
        self._names = []

    def __setitem__(self, key, value):
        """Changes anything not dundered or not a constant descriptor.

        If an constant name is used twice, an error is raised; duplicate
        values are not checked for.

        Single underscore (sunder) names are reserved.
        """
        if is_sunder(key):
            raise ValueError(
                    '_sunder_ names, such as %r, are reserved for future NamedConstant use'
                    % (key, )
                    )
        elif is_dunder(key):
            pass
        elif key in self._names:
            # overwriting an existing constant?
            raise TypeError('attempt to reuse name: %r' % (key, ))
        elif isinstance(value, constant) or not is_descriptor(value):
            if key in self:
                # overwriting a descriptor?
                raise TypeError('%s already defined as: %r' % (key, self[key]))
            self._names.append(key)
        super(NamedConstantDict, self).__setitem__(key, value)


class NamedConstantMeta(type):
    """
    Block attempts to reassign NamedConstant attributes.
    """

    @classmethod
    def __prepare__(metacls, cls, bases, **kwds):
        return NamedConstantDict()

    def __new__(metacls, cls, bases, clsdict):
        if type(clsdict) is dict:
            original_dict = clsdict
            clsdict = NamedConstantDict()
            for k, v in original_dict.items():
                clsdict[k] = v
        newdict = {}
        constants = {}
        for name, obj in clsdict.items():
            if name in clsdict._names:
                constants[name] = obj
                continue
            elif isinstance(obj, nonmember):
                obj = obj.value
            newdict[name] = obj
        newcls = super(NamedConstantMeta, metacls).__new__(metacls, cls, bases, newdict)
        newcls._named_constant_cache_ = {}
        newcls._members_ = {}
        for name, obj in constants.items():
            new_k = newcls.__new__(newcls, name, obj)
            newcls._members_[name] = new_k
        return newcls

    def __bool__(cls):
        return True

    def __delattr__(cls, attr):
        cur_obj = cls.__dict__.get(attr)
        if NamedConstant is not None and isinstance(cur_obj, NamedConstant):
            raise AttributeError('cannot delete constant <%s.%s>' % (cur_obj.__class__.__name__, cur_obj._name_))
        super(NamedConstantMeta, cls).__delattr__(attr)

    def __iter__(cls):
        return (k for k in cls._members_.values())

    def __reversed__(cls):
        return (k for k in reversed(cls._members_.values()))

    def __len__(cls):
        return len(cls._members_)

    __nonzero__ = __bool__

    def __setattr__(cls, name, value):
        """Block attempts to reassign NamedConstants.
        """
        cur_obj = cls.__dict__.get(name)
        if NamedConstant is not None and isinstance(cur_obj, NamedConstant):
            raise AttributeError('cannot rebind constant <%s.%s>' % (cur_obj.__class__.__name__, cur_obj._name_))
        super(NamedConstantMeta, cls).__setattr__(name, value)

constant_dict = _Addendum(
        dict=NamedConstantMeta.__prepare__('NamedConstant', (object, )),
        doc="NamedConstants protection.\n\n    Derive from this class to lock NamedConstants.\n\n",
        ns=globals(),
        )

@constant_dict
def __new__(cls, name, value=None, doc=None):
    if value is None:
        # lookup, name is value
        value = name
        for name, obj in cls.__dict__.items():
            if isinstance(obj, cls) and obj._value_ == value:
                return obj
        else:
            raise ValueError('%r does not exist in %r' % (value, cls.__name__))
    cur_obj = cls.__dict__.get(name)
    if isinstance(cur_obj, NamedConstant):
        raise AttributeError('cannot rebind constant <%s.%s>' % (cur_obj.__class__.__name__, cur_obj._name_))
    elif isinstance(value, constant):
        doc = doc or value.__doc__
        value = value.value
    metacls = cls.__class__
    if isinstance(value, NamedConstant):
        # constants from other classes are reduced to their actual value
        value = value._value_
    actual_type = type(value)
    value_type = cls._named_constant_cache_.get(actual_type)
    if value_type is None:
        value_type = type(cls.__name__, (cls, type(value)), {})
        cls._named_constant_cache_[type(value)] = value_type
    obj = actual_type.__new__(value_type, value)
    obj._name_ = name
    obj._value_ = value
    obj.__doc__ = doc
    cls._members_[name] = obj
    metacls.__setattr__(cls, name, obj)
    return obj

@constant_dict
def __repr__(self):
    return "<%s.%s: %r>" % (
            self.__class__.__name__, self._name_, self._value_)

@constant_dict
def __reduce_ex__(self, proto):
    return getattr, (self.__class__, self._name_)

NamedConstant = NamedConstantMeta('NamedConstant', (object, ), constant_dict.resolve())
Constant = NamedConstant
del constant_dict


