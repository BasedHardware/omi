#ifndef PyObjC_COMPAT_H
#define PyObjC_COMPAT_H

#ifndef NS_ASSUME_NONNULL_BEGIN
/* Old compiler without the Nullability attributes */
#define NS_ASSUME_NONNULL_BEGIN
#define NS_ASSUME_NONNULL_END
#define _Nullable
#define _Nonnull
#endif

NS_ASSUME_NONNULL_BEGIN

/*
 *
 * Start of compiler definitions
 *
 */
#ifndef __has_feature
#define __has_feature(x) 0
#endif
#ifndef __has_extension
#define __has_extension(x) __has_feature(x)
#endif

#if __has_extension(c_static_assert)
#define STATIC_ASSERT(test, message) _Static_assert(test, message)
#else
#define STATIC_ASSERT(test, message)                                                     \
    switch (0) {                                                                         \
    case 0:                                                                              \
    case test:;                                                                          \
    }
#endif

#if !__has_feature(objc_instancetype)
#define instancetype id
#endif

#ifdef __has_attribute
#if __has_attribute(objc_subclassing_restricted)
#define PyObjC_FINAL_CLASS __attribute__((__objc_subclassing_restricted__))
#endif
#endif
#ifndef PyObjC_FINAL_CLASS
#define PyObjC_FINAL_CLASS
#endif

/*
 *
 * Start of compiler support helpers
 *
 * XXX: Are these needed?
 */

#ifdef __GNUC__
#define unlikely(x) __builtin_expect(!!(x), 0)
#define likely(x) __builtin_expect(!!(x), 1)
#else
#define likely(x) x
#define likely(x) x
#endif

/* On some versions of GCC <limits.h> defines LONG_LONG_MAX but not LLONG_MAX, compensate.
 */
#ifndef LLONG_MIN
#ifdef LONG_LONG_MIN
#define LLONG_MIN LONG_LONG_MIN
#define LLONG_MAX LONG_LONG_MAX
#define ULLONG_MAX ULONG_LONG_MAX
#endif
#endif

/*
 *
 * End of compiler support helpers
 *
 * XXX: These two are no longer needed, all supported platforms
 *      are 64-bit
 */

#if __LP64__
#define Py_ARG_NSInteger "l"
#define Py_ARG_NSUInteger "k"
#else
#define Py_ARG_NSInteger "i"
#define Py_ARG_NSUInteger "I"
#endif

#define PyObjC__STR(x) #x
#define PyObjC_STR(x) PyObjC__STR(x)

/*
 *
 * Python version compatibility
 *
 */

#ifndef Py_SET_TYPE
#define Py_SET_TYPE(obj, type)                                                           \
    do {                                                                                 \
        Py_TYPE((obj)) = (type);                                                         \
    } while (0)
#endif

#ifndef Py_SET_SIZE
#define Py_SET_SIZE(obj, size)                                                           \
    do {                                                                                 \
        Py_SIZE((obj)) = (size);                                                         \
    } while (0)
#endif

#ifndef Py_SET_REFCNT
#define Py_SET_REFCNT(obj, count)                                                        \
    do {                                                                                 \
        Py_REFCNT((obj)) = (count);                                                      \
    } while (0)
#endif

#if PY_VERSION_HEX < 0x03090000

/* For use on Python 3.8 and earlier. PyObjC doesn't use the
 * "flag" bit internally.
 */

#ifndef PY_VECTORCALL_ARGUMENTS_OFFSET
#define PY_VECTORCALL_ARGUMENTS_OFFSET ((size_t)1 << (8 * sizeof(size_t) - 1))
#endif

#define PyVectorcall_NARGS(nargsf) ((nargsf) & ~PY_VECTORCALL_ARGUMENTS_OFFSET)

#ifdef OBJC_VERSION
/* Don't use PyObject prefixed symbols in our binaries */
#define PyObject_Vectorcall PyObjC_Vectorcall
#define PyObject_VectorcallMethod PyObjC_VectorcallMethod

extern PyObject* _Nullable PyObject_Vectorcall(PyObject* callable,
                                               PyObject* _Nonnull const* _Nonnull args,
                                               size_t nargsf,
                                               PyObject* _Nullable kwnames);
extern PyObject* _Nullable PyObject_VectorcallMethod(
    PyObject* name, PyObject* _Nonnull const* _Nonnull args, size_t nargsf,
    PyObject* _Nullable kwnames);
#endif

#endif /* Python < 3.9 */

/* Use CLINIC_SEP between the prototype and
 * description in doc strings, to get clean
 * docstrings.
 */
#define CLINIC_SEP "--\n"

extern int PyObjC_Cmp(PyObject* o1, PyObject* o2, int* result);

extern PyObject* _Nullable PyObjCBytes_InternFromString(const char* v);
extern PyObject* _Nullable PyObjCBytes_InternFromStringAndSize(const char* v,
                                                               Py_ssize_t  l);

/*
 * A micro optimization: when using Python 3.3 or later it
 * is possible to access a 'char*' with an ASCII representation
 * of a unicode object without first converting it to a bytes
 * string (if the string can be encoded as ASCII in the first
 * place.
 *
 * This slightly reduces the object allocation rate during
 * attribute access.
 *
 * XXX: Use PyUnicode_AsUTF8 instead.
 */
extern const char* _Nullable PyObjC_Unicode_Fast_Bytes(PyObject* object);

#ifdef __clang__

#ifndef Py_LIMITED_API

static inline PyObject* _Nullable* _Nonnull PyTuple_ITEMS(PyObject* tuple)
{
    return &PyTuple_GET_ITEM(tuple, 0);
}

/* This is a crude hack to disable a otherwise useful warning in the context of
 * PyTuple_SET_ITEM, without disabling it everywhere
 */
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warray-bounds"
static inline void
_PyObjCTuple_SetItem(PyObject* tuple, Py_ssize_t idx, PyObject* _Nullable value)
{
    PyTuple_SET_ITEM(tuple, idx, value);
}
#undef PyTuple_SET_ITEM
#define PyTuple_SET_ITEM(a, b, c) _PyObjCTuple_SetItem(a, b, c)

static inline PyObject*
_PyObjCTuple_GetItem(PyObject* tuple, Py_ssize_t idx)
{
    return PyTuple_GET_ITEM(tuple, idx);
}
#undef PyTuple_GET_ITEM
#define PyTuple_GET_ITEM(a, b) _PyObjCTuple_GetItem(a, b)

#pragma clang diagnostic pop

#endif /* !Py_LIMITED_API */

#endif /* __clang__ */

#define PyObjC_BEGIN_WITH_GIL                                                            \
    {                                                                                    \
        PyGILState_STATE _GILState;                                                      \
        _GILState = PyGILState_Ensure();

#define PyObjC_GIL_FORWARD_EXC()                                                         \
    do {                                                                                 \
        PyObjCErr_ToObjCWithGILState(&_GILState);                                        \
    } while (0)

#define PyObjC_GIL_RETURN(val)                                                           \
    do {                                                                                 \
        PyGILState_Release(_GILState);                                                   \
        return (val);                                                                    \
    } while (0)

#define PyObjC_GIL_RETURNVOID                                                            \
    do {                                                                                 \
        PyGILState_Release(_GILState);                                                   \
        return;                                                                          \
    } while (0)

#define PyObjC_END_WITH_GIL                                                              \
    PyGILState_Release(_GILState);                                                       \
    }

#define PyObjC_LEAVE_GIL                                                                 \
    do {                                                                                 \
        PyGILState_Release(_GILState);                                                   \
    } while (0)

extern PyObject* _Nullable PyObjC_get_tp_dict(PyTypeObject* _Nonnull tp);

NS_ASSUME_NONNULL_END

#endif /* PyObjC_COMPAT_H */
