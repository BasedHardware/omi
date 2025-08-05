from ._common import *
from ._constant import NamedConstant
import sys as _sys

__all__ = [
        'TupleSize', 'NamedTuple',
        ]

# NamedTuple

class NamedTupleDict(OrderedDict):
    """Track field order and ensure field names are not reused.

    NamedTupleMeta will use the names found in self._field_names to translate
    to indices.
    """
    def __init__(self, *args, **kwds):
        self._field_names = []
        super(NamedTupleDict, self).__init__(*args, **kwds)

    def __setitem__(self, key, value):
        """Records anything not dundered or not a descriptor.

        If a field name is used twice, an error is raised.

        Single underscore (sunder) names are reserved.
        """
        if is_sunder(key):
            if key not in ('_size_', '_order_', '_fields_', '_review_'):
                raise ValueError(
                        '_sunder_ names, such as %r, are reserved for future NamedTuple use'
                        % (key, )
                        )
        elif is_dunder(key):
            if key == '__order__':
                key = '_order_'
        elif key in self._field_names:
            # overwriting a field?
            raise TypeError('attempt to reuse field name: %r' % (key, ))
        elif not is_descriptor(value):
            if key in self:
                # field overwriting a descriptor?
                raise TypeError('%s already defined as: %r' % (key, self[key]))
            self._field_names.append(key)
        super(NamedTupleDict, self).__setitem__(key, value)


class _TupleAttributeAtIndex(object):

    def __init__(self, name, index, doc, default):
        self.name = name
        self.index = index
        if doc is undefined:
            doc = None
        self.__doc__ = doc
        self.default = default

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if len(instance) <= self.index:
            raise AttributeError('%s instance has no value for %s' % (instance.__class__.__name__, self.name))
        return instance[self.index]

    def __repr__(self):
        return '%s(%d)' % (self.__class__.__name__, self.index)


class undefined(object):
    def __repr__(self):
        return 'undefined'
    def __bool__(self):
        return False
    __nonzero__ = __bool__
undefined = undefined()


class TupleSize(NamedConstant):
    fixed = constant('fixed', 'tuple length is static')
    minimum = constant('minimum', 'tuple must be at least x long (x is calculated during creation')
    variable = constant('variable', 'tuple length can be anything')

class NamedTupleMeta(type):
    """Metaclass for NamedTuple"""

    @classmethod
    def __prepare__(metacls, cls, bases, size=undefined, **kwds):
        return NamedTupleDict()

    def __init__(cls, *args , **kwds):
        super(NamedTupleMeta, cls).__init__(*args)

    def __new__(metacls, cls, bases, clsdict, size=undefined, **kwds):
        if bases == (object, ):
            bases = (tuple, object)
        elif tuple not in bases:
            if object in bases:
                index = bases.index(object)
                bases = bases[:index] + (tuple, ) + bases[index:]
            else:
                bases = bases + (tuple, )
        # include any fields from base classes
        base_dict = NamedTupleDict()
        namedtuple_bases = []
        for base in bases:
            if isinstance(base, NamedTupleMeta):
                namedtuple_bases.append(base)
        i = 0
        if namedtuple_bases:
            for name, index, doc, default in metacls._convert_fields(*namedtuple_bases):
                base_dict[name] = index, doc, default
                i = max(i, index)
        # construct properly ordered dict with normalized indexes
        for k, v in clsdict.items():
            base_dict[k] = v
        original_dict = base_dict
        if size is not undefined and '_size_' in original_dict:
            raise TypeError('_size_ cannot be set if "size" is passed in header')
        add_order = isinstance(clsdict, NamedTupleDict)
        clsdict = NamedTupleDict()
        clsdict.setdefault('_size_', size or TupleSize.fixed)
        unnumbered = OrderedDict()
        numbered = OrderedDict()
        _order_ = original_dict.pop('_order_', [])
        if _order_ :
            _order_ = _order_.replace(',',' ').split()
            add_order = False
        # and process this class
        for k, v in original_dict.items():
            if k not in original_dict._field_names:
                clsdict[k] = v
            else:
                # TODO:normalize v here
                if isinstance(v, baseinteger):
                    # assume an offset
                    v = v, undefined, undefined
                    i = v[0] + 1
                    target = numbered
                elif isinstance(v, basestring):
                    # assume a docstring
                    if add_order:
                        v = i, v, undefined
                        i += 1
                        target = numbered
                    else:
                        v = undefined, v, undefined
                        target = unnumbered
                elif isinstance(v, tuple) and len(v) in (2, 3) and isinstance(v[0], baseinteger) and isinstance(v[1], (basestring, NoneType)):
                    # assume an offset, a docstring, and (maybe) a default
                    if len(v) == 2:
                        v = v + (undefined, )
                    v = v
                    i = v[0] + 1
                    target = numbered
                elif isinstance(v, tuple) and len(v) in (1, 2) and isinstance(v[0], (basestring, NoneType)):
                    # assume a docstring, and (maybe) a default
                    if len(v) == 1:
                        v = v + (undefined, )
                    if add_order:
                        v = (i, ) + v
                        i += 1
                        target = numbered
                    else:
                        v = (undefined, ) + v
                        target = unnumbered
                else:
                    # refuse to guess further
                    raise ValueError('not sure what to do with %s=%r (should be OFFSET [, DOC [, DEFAULT]])' % (k, v))
                target[k] = v
        # all index values have been normalized
        # deal with _order_ (or lack thereof)
        fields = []
        aliases = []
        seen = set()
        max_len = 0
        if not _order_:
            if unnumbered:
                raise ValueError("_order_ not specified and OFFSETs not declared for %r" % (unnumbered.keys(), ))
            for name, (index, doc, default) in sorted(numbered.items(), key=lambda nv: (nv[1][0], nv[0])):
                if index in seen:
                    aliases.append(name)
                else:
                    fields.append(name)
                    seen.add(index)
                    max_len = max(max_len, index + 1)
            offsets = numbered
        else:
            # check if any unnumbered not in _order_
            missing = set(unnumbered) - set(_order_)
            if missing:
                raise ValueError("unable to order fields: %s (use _order_ or specify OFFSET" % missing)
            offsets = OrderedDict()
            # if any unnumbered, number them from their position in _order_
            i = 0
            for k in _order_:
                try:
                    index, doc, default = unnumbered.pop(k, None) or numbered.pop(k)
                except IndexError:
                    raise ValueError('%s (from _order_) not found in %s' % (k, cls))
                if index is not undefined:
                    i = index
                if i in seen:
                    aliases.append(k)
                else:
                    fields.append(k)
                    seen.add(i)
                offsets[k] = i, doc, default
                i += 1
                max_len = max(max_len, i)
            # now handle anything in numbered
            for k, (index, doc, default) in sorted(numbered.items(), key=lambda nv: (nv[1][0], nv[0])):
                if index in seen:
                    aliases.append(k)
                else:
                    fields.append(k)
                    seen.add(index)
                offsets[k] = index, doc, default
                max_len = max(max_len, index+1)

        # at this point fields and aliases should be ordered lists, offsets should be an
        # OrdededDict with each value an int, str or None or undefined, default or None or undefined
        assert len(fields) + len(aliases) == len(offsets), "number of fields + aliases != number of offsets"
        assert set(fields) & set(offsets) == set(fields), "some fields are not in offsets: %s" % set(fields) & set(offsets)
        assert set(aliases) & set(offsets) == set(aliases), "some aliases are not in offsets: %s" % set(aliases) & set(offsets)
        for name, (index, doc, default) in offsets.items():
            assert isinstance(index, baseinteger), "index for %s is not an int (%s:%r)" % (name, type(index), index)
            assert isinstance(doc, (basestring, NoneType)) or doc is undefined, "doc is not a str, None, nor undefined (%s:%r)" % (name, type(doc), doc)

        # create descriptors for fields
        for name, (index, doc, default) in offsets.items():
            clsdict[name] = _TupleAttributeAtIndex(name, index, doc, default)
        clsdict['__slots__'] = ()

        # create our new NamedTuple type
        namedtuple_class = super(NamedTupleMeta, metacls).__new__(metacls, cls, bases, clsdict)
        namedtuple_class._fields_ = fields
        namedtuple_class._aliases_ = aliases
        namedtuple_class._defined_len_ = max_len
        return namedtuple_class

    @staticmethod
    def _convert_fields(*namedtuples):
        "create list of index, doc, default triplets for cls in namedtuples"
        all_fields = []
        for cls in namedtuples:
            base = len(all_fields)
            for field in cls._fields_:
                desc = getattr(cls, field)
                all_fields.append((field, base+desc.index, desc.__doc__, desc.default))
        return all_fields

    def __add__(cls, other):
        "A new NamedTuple is created by concatenating the _fields_ and adjusting the descriptors"
        if not isinstance(other, NamedTupleMeta):
            return NotImplemented
        return NamedTupleMeta('%s%s' % (cls.__name__, other.__name__), (cls, other), {})

    def __call__(cls, *args, **kwds):
        """Creates a new NamedTuple class or an instance of a NamedTuple subclass.

        NamedTuple should have args of (class_name, names, module)

            `names` can be:

                * A string containing member names, separated either with spaces or
                  commas.  Values are auto-numbered from 1.
                * An iterable of member names.  Values are auto-numbered from 1.
                * An iterable of (member name, value) pairs.
                * A mapping of member name -> value.

                `module`, if set, will be stored in the new class' __module__ attribute;

                Note: if `module` is not set this routine will attempt to discover the
                calling module by walking the frame stack; if this is unsuccessful
                the resulting class will not be pickleable.

        subclass should have whatever arguments and/or keywords will be used to create an
        instance of the subclass
        """
        if cls is NamedTuple or cls._defined_len_ == 0:
            original_args = args
            original_kwds = kwds.copy()
            # create a new subclass
            try:
                if 'class_name' in kwds:
                    class_name = kwds.pop('class_name')
                else:
                    class_name, args = args[0], args[1:]
                if 'names' in kwds:
                    names = kwds.pop('names')
                else:
                    names, args = args[0], args[1:]
                if 'module' in kwds:
                    module = kwds.pop('module')
                elif args:
                    module, args = args[0], args[1:]
                else:
                    module = None
                if 'type' in kwds:
                    type = kwds.pop('type')
                elif args:
                    type, args = args[0], args[1:]
                else:
                    type = None

            except IndexError:
                raise TypeError('too few arguments to NamedTuple: %s, %s' % (original_args, original_kwds))
            if args or kwds:
                raise TypeError('too many arguments to NamedTuple: %s, %s' % (original_args, original_kwds))
            if PY2:
                # if class_name is unicode, attempt a conversion to ASCII
                if isinstance(class_name, unicode):
                    try:
                        class_name = class_name.encode('ascii')
                    except UnicodeEncodeError:
                        raise TypeError('%r is not representable in ASCII' % (class_name, ))
            # quick exit if names is a NamedTuple
            if isinstance(names, NamedTupleMeta):
                names.__name__ = class_name
                if type is not None and type not in names.__bases__:
                    names.__bases__ = (type, ) + names.__bases__
                return names

            metacls = cls.__class__
            bases = (cls, )
            clsdict = metacls.__prepare__(class_name, bases)

            # special processing needed for names?
            if isinstance(names, basestring):
                names = names.replace(',', ' ').split()
            if isinstance(names, (tuple, list)) and isinstance(names[0], basestring):
                names = [(e, i) for (i, e) in enumerate(names)]
            # Here, names is either an iterable of (name, index) or (name, index, doc, default) or a mapping.
            item = None  # in case names is empty
            for item in names:
                if isinstance(item, basestring):
                    # mapping
                    field_name, field_index = item, names[item]
                else:
                    # non-mapping
                    if len(item) == 2:
                        field_name, field_index = item
                    else:
                        field_name, field_index = item[0], item[1:]
                clsdict[field_name] = field_index
            if type is not None:
                if not isinstance(type, tuple):
                    type = (type, )
                bases = type + bases
            namedtuple_class = metacls.__new__(metacls, class_name, bases, clsdict)

            # TODO: replace the frame hack if a blessed way to know the calling
            # module is ever developed
            if module is None:
                try:
                    module = _sys._getframe(1).f_globals['__name__']
                except (AttributeError, ValueError, KeyError):
                    pass
            if module is None:
                make_class_unpicklable(namedtuple_class)
            else:
                namedtuple_class.__module__ = module

            return namedtuple_class
        else:
            # instantiate a subclass
            namedtuple_instance = cls.__new__(cls, *args, **kwds)
            if isinstance(namedtuple_instance, cls):
                namedtuple_instance.__init__(*args, **kwds)
            return namedtuple_instance

    @bltin_property
    def __fields__(cls):
        return list(cls._fields_)
    # collections.namedtuple compatibility
    _fields = __fields__

    @bltin_property
    def __aliases__(cls):
        return list(cls._aliases_)

    def __repr__(cls):
        return "<NamedTuple %r>" % (cls.__name__, )

namedtuple_dict = _Addendum(
        dict=NamedTupleMeta.__prepare__('NamedTuple', (object, )),
        doc="NamedTuple base class.\n\n    Derive from this class to define new NamedTuples.\n\n",
        ns=globals(),
        )

@namedtuple_dict
def __new__(cls, *args, **kwds):
    if cls._size_ is TupleSize.fixed and len(args) > cls._defined_len_:
        raise TypeError('%d fields expected, %d received' % (cls._defined_len_, len(args)))
    unknown = set(kwds) - set(cls._fields_) - set(cls._aliases_)
    if unknown:
        raise TypeError('unknown fields: %r' % (unknown, ))
    final_args = list(args) + [undefined] * (len(cls.__fields__) - len(args))
    for field, value in kwds.items():
        index = getattr(cls, field).index
        if final_args[index] != undefined:
            raise TypeError('field %s specified more than once' % field)
        final_args[index] = value
    cls._review_(final_args)
    missing = []
    for index, value in enumerate(final_args):
        if value is undefined:
            # look for default values
            name = cls.__fields__[index]
            default = getattr(cls, name).default
            if default is undefined:
                missing.append(name)
            else:
                final_args[index] = default
    if missing:
        if cls._size_ in (TupleSize.fixed, TupleSize.minimum):
            raise TypeError('values not provided for field(s): %s' % ', '.join(missing))
        while final_args and final_args[-1] is undefined:
            final_args.pop()
            missing.pop()
        if cls._size_ is not TupleSize.variable or undefined in final_args:
            raise TypeError('values not provided for field(s): %s' % ', '.join(missing))
    return tuple.__new__(cls, tuple(final_args))

@namedtuple_dict
def __reduce_ex__(self, proto):
    return self.__class__, tuple(getattr(self, f) for f in self._fields_)

@namedtuple_dict
def __repr__(self):
    if len(self) == len(self._fields_):
        return "%s(%s)" % (
                self.__class__.__name__, ', '.join(['%s=%r' % (f, o) for f, o in zip(self._fields_, self)])
                )
    else:
        return '%s(%s)' % (self.__class__.__name__, ', '.join([repr(o) for o in self]))

@namedtuple_dict
def __str__(self):
    return "%s(%s)" % (
            self.__class__.__name__, ', '.join(['%r' % (getattr(self, f), ) for f in self._fields_])
            )

@namedtuple_dict
@bltin_property
def _fields_(self):
    return list(self.__class__._fields_)

    # compatibility methods with stdlib namedtuple
@namedtuple_dict
@bltin_property
def __aliases__(self):
    return list(self.__class__._aliases_)

@namedtuple_dict
@bltin_property
def _fields(self):
    return list(self.__class__._fields_)

@namedtuple_dict
@classmethod
def _make(cls, iterable, new=None, len=None):
    return cls.__new__(cls, *iterable)

@namedtuple_dict
def _asdict(self):
    return OrderedDict(zip(self._fields_, self))

@namedtuple_dict
def _replace(self, **kwds):
    current = self._asdict()
    current.update(kwds)
    return self.__class__(**current)

@namedtuple_dict
@classmethod
def _review_(cls, final_args):
    pass

NamedTuple = NamedTupleMeta('NamedTuple', (object, ), namedtuple_dict.resolve())
del namedtuple_dict



