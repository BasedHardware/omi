__all__ = (
    "object_property",
    "bool_property",
    "array_property",
    "set_property",
    "dict_property",
)

from copy import copy as copy_func

from objc import (
    _C_BOOL,
    _C_ID,
    _C_NSBOOL,
    NULL,
    _C_NSUInteger,
    ivar,
    lookUpClass,
    selector,
)

import collections.abc

NSSet = lookUpClass("NSSet")
NSObject = lookUpClass("NSObject")


def _str(value):
    return value.decode("ascii")


def attrsetter(prop, name, copy):
    if copy:

        def func(self, value):
            if isinstance(value, NSObject):
                setattr(self, name, value.copy())
            else:
                setattr(self, name, copy_func(value))

    else:

        def func(self, value):
            setattr(self, name, value)

    return func


def attrgetter(name):
    def func(self):
        return getattr(self, name)

    return func


def _return_value(value):
    def func(self):
        return value

    return func


def _dynamic_getter(name):
    def getter(an_object):
        m = getattr(an_object.pyobjc_instanceMethods, name)
        return m()

    getter.__name__ = name
    return getter


def _dynamic_setter(name):
    def setter(an_object, value):
        m = getattr(an_object.pyobjc_instanceMethods, name.replace(":", "_"))
        return m(value)

    setter.__name__ = name
    return setter


class object_property:
    def __init__(
        self,
        name=None,
        read_only=False,
        copy=False,
        dynamic=False,
        ivar=None,
        typestr=_C_ID,
        depends_on=None,
    ):
        self.__created = False
        self.__inherit = False
        self._name = name
        self._typestr = typestr
        self._ro = read_only
        self._copy = copy
        self._dynamic = dynamic
        self._ivar = ivar
        self._getter = None
        self._setter = None
        self._validate = None
        if depends_on is None:
            self._depends_on = None
        else:
            self._depends_on = set(depends_on)

        self.__getprop = None
        self.__setprop = None
        self.__parent = None

    def _clone(self):
        if self._depends_on is None:
            depends = None
        else:
            depends = self._depends_on.copy()

        v = type(self)(
            name=self._name,
            read_only=self._ro,
            copy=self._copy,
            dynamic=self._dynamic,
            ivar=self._ivar,
            typestr=self._typestr,
            depends_on=depends,
        )
        v.__inherit = True

        v.__getprop = self.__getprop
        v.__setprop = self.__setprop
        v.__parent = self

        return v

    def __pyobjc_class_setup__(self, name, class_dict, instance_methods, class_methods):
        self.__created = True
        if self._name is None:
            self._name = name

        if self._ivar is not NULL:
            if self._ivar is None:
                ivname = "_" + self._name
            else:
                ivname = self._ivar

            if self.__parent is None:
                ivar_ref = ivar(name=ivname, type=self._typestr)
                class_dict[ivname] = ivar_ref

        if self._ro:
            self._setter = None

        else:
            setterName = (
                b"set"
                + name[0].upper().encode("latin1")
                + name[1:].encode("latin1")
                + b":"
            )
            signature = b"v@:" + self._typestr
            if self._setter is None:
                if self.__inherit:
                    pass

                elif self._dynamic:
                    dynSetterName = "set" + name[0].upper() + name[1:] + "_"
                    self.__setprop = _dynamic_setter(dynSetterName)
                    instance_methods.add(setterName)

                else:
                    if self._ivar is NULL:
                        raise ValueError(
                            "Cannot create default setter for property " "without ivar"
                        )

                    setprop = selector(
                        attrsetter(self._name, ivname, self._copy),
                        selector=setterName,
                        signature=signature,
                        isHidden=True,
                    )
                    instance_methods.add(setprop)

                    # Use dynamic setter to avoid problems when subclassing
                    self.__setprop = _dynamic_setter(_str(setterName))
            else:
                setprop = selector(
                    self._setter,
                    selector=setterName,
                    signature=signature,
                    isHidden=True,
                )
                instance_methods.add(setprop)

                # Use dynamic setter to avoid problems when subclassing
                self.__setprop = _dynamic_setter(_str(setterName))

        if self._typestr in (_C_NSBOOL, _C_BOOL):
            getterName = (
                b"is" + name[0].upper().encode("latin1") + name[1:].encode("latin1")
            )
        else:
            getterName = self._name.encode("latin1")

        if self._getter is None:
            if self.__inherit:
                pass

            elif self._dynamic:
                if self._typestr in (_C_NSBOOL, _C_BOOL):
                    dynGetterName = "is" + name[0].upper() + name[1:]
                else:
                    dynGetterName = self._name

                self.__getprop = _dynamic_getter(dynGetterName)
                instance_methods.add(getterName)

            else:
                if self._ivar is NULL:
                    raise ValueError(
                        "Cannot create default getter for property without ivar"
                    )

                self.__getprop = selector(
                    attrgetter(ivname),
                    selector=getterName,
                    signature=self._typestr + b"@:",
                    isHidden=True,
                )
                instance_methods.add(self.__getprop)

        else:
            self.__getprop = getprop = selector(
                self._getter,
                selector=getterName,
                signature=self._typestr + b"@:",
                isHidden=True,
            )
            instance_methods.add(getprop)
            # self.__getprop = _dynamic_getter(getterName)

        if self._validate is not None:
            selName = (
                b"validate"
                + self._name[0].upper().encode("latin")
                + self._name[1:].encode("latin")
                + b":error:"
            )
            signature = _C_NSBOOL + b"@:N^@o^@"
            validate = selector(self._validate, selector=selName, signature=signature)
            class_dict[validate.selector.decode().replace(":", "_")] = validate
            instance_methods.add(validate)

        if self._depends_on:
            if self.__parent is not None:
                if self.__parent._depends_on:
                    self._depends_on.update(self.__parent._depends_on.copy())

            self._depends_on = self._depends_on

            affecting = selector(
                _return_value(NSSet.setWithArray_(list(self._depends_on))),
                selector=b"keyPathsForValuesAffecting"
                + self._name[0].upper().encode("latin1")
                + self._name[1:].encode("latin1"),
                signature=b"@@:",
                isClassMethod=True,
            )
            class_dict[affecting.selector.decode().replace(":", "_")] = affecting
            class_methods.add(affecting)

    def __get__(self, an_object, owner):
        if an_object is None:
            return self
        return self.__getprop(an_object)

    def __set__(self, an_object, value):
        if self.__setprop is None:
            raise ValueError("setting read-only property " + self._name)

        return self.__setprop(an_object, value)

    def __delete__(self, an_object):
        raise TypeError("cannot delete property " + self._name)

    def depends_on(self, keypath):
        if self._depends_on is None:
            self._depends_on = set()
        self._depends_on.add(keypath)

    def getter(self, function):
        if self.__created:
            v = self._clone()
            v._getter = function
            return v

        self._getter = function
        return self

    def setter(self, function):
        if self.__created:
            v = self._clone()
            v._ro = False
            v._setter = function
            return v

        if self._ro:
            raise ValueError("Defining setter for read-only property")

        self._setter = function
        return self

    def validate(self, function):
        if self._ro:
            raise ValueError("Defining validator for read-only property")

        if self.__created:
            v = self._clone()
            v._validate = function
            return v

        self._validate = function
        return self


class bool_property(object_property):
    def __init__(
        self,
        name=None,
        read_only=False,
        copy=False,
        dynamic=False,
        ivar=None,
        typestr=_C_NSBOOL,
    ):
        super().__init__(name, read_only, copy, dynamic, ivar, typestr)


NSIndexSet = lookUpClass("NSIndexSet")
NSMutableIndexSet = lookUpClass("NSMutableIndexSet")
NSKeyValueChangeSetting = 1
NSKeyValueChangeInsertion = 2
NSKeyValueChangeRemoval = 3
NSKeyValueChangeReplacement = 4


# Helper function for (not) pickling array_proxy instances
# NOTE: Don't remove this function, it can be referenced from
# pickle files.
def _id(value):
    return value


class array_proxy(collections.abc.MutableSequence):
    __slots__ = ("_name", "_parent", "__wrapped", "_ro")

    def __init__(self, name, parent, wrapped, read_only):
        self._name = name
        self._parent = parent
        self._ro = read_only
        self.__wrapped = wrapped

    @property
    def _wrapped(self):
        return self.__wrapped.__getvalue__(self._parent)

    def __indexSetForIndex(self, index):
        if isinstance(index, slice):
            result = NSMutableIndexSet.alloc().init()
            start, stop, step = index.indices(len(self._wrapped))
            for i in range(start, stop, step):
                result.addIndex_(i)

            return result

        elif isinstance(index, int):
            if index < 0:
                v = len(self) + index
                if v < 0:
                    raise IndexError(index)
                return NSIndexSet.alloc().initWithIndex_(v)

            else:
                return NSIndexSet.alloc().initWithIndex_(index)

        else:
            raise TypeError(index)

    def __repr__(self):
        return (
            "<array proxy for property " + self._name + " " + repr(self._wrapped) + ">"
        )

    def __reduce__(self):
        # Ensure that the proxy itself doesn't get stored
        # in pickles.
        return _id, (self._wrapped,)

    def __getattr__(self, name):
        # Default: just defer to wrapped list
        return getattr(self._wrapped, name)

    def __len__(self):
        return self._wrapped.__len__()

    def __getitem__(self, index):
        return self._wrapped[index]

    def __setitem__(self, index, value):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        indexes = self.__indexSetForIndex(index)
        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeSetting, indexes, self._name
        )
        try:
            self._wrapped[index] = value
        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeReplacement, indexes, self._name
            )

    def __delitem__(self, index):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        indexes = self.__indexSetForIndex(index)
        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeRemoval, indexes, self._name
        )
        try:
            del self._wrapped[index]
        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeRemoval, indexes, self._name
            )

    def append(self, value):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        index = len(self)
        indexes = NSIndexSet.alloc().initWithIndex_(index)
        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeInsertion, indexes, self._name
        )
        try:
            self._wrapped.append(value)
        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeInsertion, indexes, self._name
            )

    def insert(self, index, value):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        if isinstance(index, slice):
            raise TypeError("insert argument 1 is a slice")

        indexes = self.__indexSetForIndex(index)
        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeInsertion, indexes, self._name
        )
        try:
            self._wrapped.insert(index, value)
        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeInsertion, indexes, self._name
            )

    def pop(self, index=-1):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        if isinstance(index, slice):
            raise TypeError("pop argument 1 is a slice")

        indexes = self.__indexSetForIndex(index)
        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeRemoval, indexes, self._name
        )
        try:
            return self._wrapped.pop(index)
        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeRemoval, indexes, self._name
            )

    def extend(self, values):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        values = list(values)

        indexes = NSIndexSet.alloc().initWithIndexesInRange_((len(self), len(values)))

        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeInsertion, indexes, self._name
        )
        try:
            self._wrapped.extend(values)

        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeInsertion, indexes, self._name
            )

    def __iadd__(self, values):
        self.extend(values)
        return self

    def __add__(self, values):
        return self._wrapped + values

    def __mul__(self, count):
        return self._wrapped * count

    def __imul__(self, count):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")
        if not isinstance(count, int):
            raise TypeError(count)

        indexes = NSIndexSet.alloc().initWithIndexesInRange_(
            (len(self), len(self) * (count - 1))
        )
        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeInsertion, indexes, self._name
        )
        try:
            self._wrapped.__imul__(count)
        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeInsertion, indexes, self._name
            )

        return self

    def __eq__(self, other):
        if isinstance(other, array_proxy):
            return self._wrapped == other._wrapped

        else:
            return self._wrapped == other

    def __ne__(self, other):
        if isinstance(other, array_proxy):
            return self._wrapped != other._wrapped

        else:
            return self._wrapped != other

    def __lt__(self, other):
        if isinstance(other, array_proxy):
            return self._wrapped < other._wrapped

        else:
            return self._wrapped < other

    def __le__(self, other):
        if isinstance(other, array_proxy):
            return self._wrapped <= other._wrapped

        else:
            return self._wrapped <= other

    def __gt__(self, other):
        if isinstance(other, array_proxy):
            return self._wrapped > other._wrapped

        else:
            return self._wrapped > other

    def __ge__(self, other):
        if isinstance(other, array_proxy):
            return self._wrapped >= other._wrapped

        else:
            return self._wrapped >= other

    def sort(self, key=None, reverse=False):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        indexes = NSIndexSet.alloc().initWithIndexesInRange_((0, len(self._wrapped)))
        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeReplacement, indexes, self._name
        )
        try:
            self._wrapped.sort(key=key, reverse=reverse)
        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeReplacement, indexes, self._name
            )

    def reverse(self):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        indexes = NSIndexSet.alloc().initWithIndexesInRange_((0, len(self._wrapped)))
        self._parent.willChange_valuesAtIndexes_forKey_(
            NSKeyValueChangeReplacement, indexes, self._name
        )
        try:
            self._wrapped.reverse()
        finally:
            self._parent.didChange_valuesAtIndexes_forKey_(
                NSKeyValueChangeReplacement, indexes, self._name
            )


def makeArrayAccessors(name):
    def countOf(self):
        return len(getattr(self, name))

    def objectIn(self, idx):
        return getattr(self, name)[idx]

    def insert(self, value, idx):
        getattr(self, name).insert(idx, value)

    def replace(self, idx, value):
        getattr(self, name)[idx] = value

    def remove(self, idx):
        del getattr(self, name)[idx]

    return countOf, objectIn, insert, remove, replace


class array_property(object_property):
    def __init__(
        self,
        name=None,
        read_only=False,
        copy=True,
        dynamic=False,
        ivar=None,
        depends_on=None,
    ):
        super().__init__(
            name,
            read_only=read_only,
            copy=copy,
            dynamic=dynamic,
            ivar=ivar,
            depends_on=depends_on,
        )

    def __pyobjc_class_setup__(self, name, class_dict, instance_methods, class_methods):
        super().__pyobjc_class_setup__(
            name, class_dict, instance_methods, class_methods
        )

        # Insert (Mutable) Indexed Accessors

        name = self._name
        Name = name[0].upper() + name[1:]

        countOf, objectIn, insert, remove, replace = makeArrayAccessors(self._name)

        countOf = selector(
            countOf,
            selector=(f"countOf{Name}").encode("latin1"),
            signature=_C_NSUInteger + b"@:",
            isHidden=True,
        )
        instance_methods.add(countOf)

        objectIn = selector(
            objectIn,
            selector=(f"objectIn{Name}AtIndex:").encode("latin1"),
            signature=b"@@:" + _C_NSUInteger,
            isHidden=True,
        )
        instance_methods.add(objectIn)

        insert = selector(
            insert,
            selector=(f"insertObject:in{Name}AtIndex:").encode("latin1"),
            signature=b"v@:@" + _C_NSUInteger,
            isHidden=True,
        )
        instance_methods.add(insert)

        remove = selector(
            remove,
            selector=(f"removeObjectFrom{Name}AtIndex:").encode("latin1"),
            signature=b"v@:" + _C_NSUInteger,
            isHidden=True,
        )
        instance_methods.add(remove)

        replace = selector(
            replace,
            selector=(f"replaceObjectIn{Name}AtIndex:withObject:").encode("latin1"),
            signature=b"v@:" + _C_NSUInteger + b"@",
            isHidden=True,
        )
        instance_methods.add(replace)

    def __set__(self, an_object, value):
        if isinstance(value, array_proxy):
            if value._name == self._name and value._parent is an_object:
                # attr.prop = attr.prop
                return

        if isinstance(value, array_proxy):
            value = list(value)

        super().__set__(an_object, value)

    def __get__(self, an_object, owner):
        v = object_property.__get__(self, an_object, owner)
        if v is None:
            v = []
            object_property.__set__(self, an_object, v)
        return array_proxy(self._name, an_object, self, self._ro)

    def __getvalue__(self, an_object):
        v = object_property.__get__(self, an_object, None)
        if v is None:
            v = []
            object_property.__set__(self, an_object, v)
        return v


NSKeyValueUnionSetMutation = 1
NSKeyValueMinusSetMutation = 2
NSKeyValueIntersectSetMutation = 3
NSKeyValueSetSetMutation = 4


class set_proxy(collections.abc.MutableSet):
    __slots__ = ("_name", "__wrapped", "_parent", "_ro")

    def __init__(self, name, parent, wrapped, read_only):
        self._name = name
        self._parent = parent
        self._ro = read_only
        self.__wrapped = wrapped

    def __repr__(self):
        return "<set proxy for property " + self._name + " " + repr(self._wrapped) + ">"

    @property
    def _wrapped(self):
        return self.__wrapped.__getvalue__(self._parent)

    def __reduce__(self):
        # Ensure that the proxy itself doesn't get stored
        # in pickles.
        return _id, (self._wrapped,)

    def __getattr__(self, attr):
        return getattr(self._wrapped, attr)

    def __contains__(self, value):
        return self._wrapped.__contains__(value)

    def __iter__(self):
        return self._wrapped.__iter__()

    def __len__(self):
        return self._wrapped.__len__()

    def __eq__(self, other):
        if isinstance(other, set_proxy):
            return self._wrapped == other._wrapped

        else:
            return self._wrapped == other

    def __ne__(self, other):
        if isinstance(other, set_proxy):
            return self._wrapped != other._wrapped

        else:
            return self._wrapped != other

    def __lt__(self, other):
        if isinstance(other, set_proxy):
            return self._wrapped < other._wrapped

        else:
            return self._wrapped < other

    def __le__(self, other):
        if isinstance(other, set_proxy):
            return self._wrapped <= other._wrapped

        else:
            return self._wrapped <= other

    def __gt__(self, other):
        if isinstance(other, set_proxy):
            return self._wrapped > other._wrapped

        else:
            return self._wrapped > other

    def __ge__(self, other):
        if isinstance(other, set_proxy):
            return self._wrapped >= other._wrapped

        else:
            return self._wrapped >= other

    def add(self, item):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueUnionSetMutation, {item}
        )
        try:
            self._wrapped.add(item)
        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueUnionSetMutation, {item}
            )

    def clear(self):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        current_value = set(self._wrapped)
        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueMinusSetMutation, current_value
        )
        try:
            self._wrapped.clear()
        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueMinusSetMutation, current_value
            )

    def difference_update(self, *others):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        s = set()
        s.update(*others)
        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueMinusSetMutation, s
        )
        try:
            self._wrapped.difference_update(s)

        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueMinusSetMutation, s
            )

    def discard(self, item):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueMinusSetMutation, {item}
        )
        try:
            self._wrapped.discard(item)

        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueMinusSetMutation, {item}
            )

    def intersection_update(self, other):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        other = set(other)

        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueIntersectSetMutation, other
        )
        try:
            self._wrapped.intersection_update(other)

        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueIntersectSetMutation, other
            )

    def pop(self):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        try:
            v = next(iter(self))
        except StopIteration:
            raise KeyError("Empty set")

        self.remove(v)
        return v

    def remove(self, item):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueMinusSetMutation, {item}
        )
        try:
            self._wrapped.remove(item)

        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueMinusSetMutation, {item}
            )

    def symmetric_difference_update(self, other):
        # NOTE: This method does not call the corresponding method
        # of the wrapped set to ensure that we generate the right
        # notifications.
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        other = set(other)

        to_add = set()
        to_remove = set()
        for o in other:
            if o in self:
                to_remove.add(o)
            else:
                to_add.add(o)

        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueMinusSetMutation, to_remove
        )
        try:
            self._wrapped.difference_update(to_remove)

        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueMinusSetMutation, to_remove
            )

        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueUnionSetMutation, to_add
        )
        try:
            self._wrapped.update(to_add)

        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueUnionSetMutation, to_add
            )

    def update(self, *others):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        s = set()
        s.update(*others)

        self._parent.willChangeValueForKey_withSetMutation_usingObjects_(
            self._name, NSKeyValueUnionSetMutation, s
        )
        try:
            self._wrapped.update(s)

        finally:
            self._parent.didChangeValueForKey_withSetMutation_usingObjects_(
                self._name, NSKeyValueUnionSetMutation, s
            )

    def __or__(self, other):
        return self._wrapped | other

    def __and__(self, other):
        return self._wrapped & other

    def __xor__(self, other):
        return self._wrapped ^ other

    def __sub__(self, other):
        return self._wrapped - other

    def __ior__(self, other):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        self.update(other)
        return self

    def __isub__(self, other):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        self.difference_update(other)
        return self

    def __ixor__(self, other):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        self.symmetric_difference_update(other)
        return self

    def __iand__(self, other):
        if self._ro:
            raise ValueError(f"Property '{self._name}' is read-only")

        self.intersection_update(other)
        return self


def makeSetAccessors(name):
    def countOf(self):
        return len(getattr(self, name))

    def enumeratorOf(self):
        return iter(getattr(self, name))

    def memberOf(self, value):
        collection = getattr(self, name)

        for item in collection:
            if item == value:
                return item

        else:
            return None

    def add(self, value):
        getattr(self, name).add(value)

    def remove(self, value):
        getattr(self, name).discard(value)

    return countOf, enumeratorOf, memberOf, add, remove


class set_property(object_property):
    def __init__(
        self,
        name=None,
        read_only=False,
        copy=True,
        dynamic=False,
        ivar=None,
        depends_on=None,
    ):
        super().__init__(
            name,
            read_only=read_only,
            copy=copy,
            dynamic=dynamic,
            ivar=ivar,
            depends_on=depends_on,
        )

    def __get__(self, an_object, owner):
        v = object_property.__get__(self, an_object, owner)
        if v is None:
            v = set()
            object_property.__set__(self, an_object, v)
        return set_proxy(self._name, an_object, self, self._ro)

    def __set__(self, an_object, value):
        if isinstance(value, set_proxy):
            if value._name == self._name and value._parent is an_object:
                # attr.prop = attr.prop
                return

        if isinstance(value, set_proxy):
            value = list(value)

        super().__set__(an_object, value)

    def __getvalue__(self, an_object):
        v = object_property.__get__(self, an_object, None)
        if v is None:
            v = set()
            object_property.__set__(self, an_object, v)
        return v

    def __pyobjc_class_setup__(self, name, class_dict, instance_methods, class_methods):
        super().__pyobjc_class_setup__(
            name, class_dict, instance_methods, class_methods
        )

        # (Mutable) Unordered Accessors

        name = self._name
        Name = name[0].upper() + name[1:]

        countOf, enumeratorOf, memberOf, add, remove = makeSetAccessors(self._name)

        countOf = selector(
            countOf,
            selector=(f"countOf{Name}").encode("latin1"),
            signature=_C_NSUInteger + b"@:",
            isHidden=True,
        )
        instance_methods.add(countOf)

        enumeratorOf = selector(
            enumeratorOf,
            selector=(f"enumeratorOf{Name}").encode("latin1"),
            signature=b"@@:",
            isHidden=True,
        )
        instance_methods.add(enumeratorOf)

        memberOf = selector(
            memberOf,
            selector=(f"memberOf{Name}:").encode("latin"),
            signature=b"@@:@",
            isHidden=True,
        )
        instance_methods.add(memberOf)

        add1 = selector(
            add,
            selector=(f"add{Name}:").encode("latin"),
            signature=b"v@:@",
            isHidden=True,
        )
        instance_methods.add(add1)

        add2 = selector(
            add,
            selector=(f"add{Name}Object:").encode("latin1"),
            signature=b"v@:@",
            isHidden=True,
        )
        instance_methods.add(add2)

        remove1 = selector(
            remove,
            selector=(f"remove{Name}:").encode("latin1"),
            signature=b"v@:@",
            isHidden=True,
        )
        instance_methods.add(remove1)

        remove2 = selector(
            remove,
            selector=(f"remove{Name}Object:").encode("latin"),
            signature=b"v@:@",
            isHidden=True,
        )
        instance_methods.add(remove2)


NSMutableDictionary = lookUpClass("NSMutableDictionary")


class dict_property(object_property):
    def __get__(self, an_object, owner):
        v = object_property.__get__(self, an_object, owner)
        if v is None:
            v = NSMutableDictionary.alloc().init()
            object_property.__set__(self, an_object, v)
        return object_property.__get__(self, an_object, owner)
