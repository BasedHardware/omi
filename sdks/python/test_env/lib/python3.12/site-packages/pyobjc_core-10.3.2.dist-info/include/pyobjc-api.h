#ifndef PyObjC_API_H
#define PyObjC_API_H

/*
 * Use this in helper modules for the objc package, and in wrappers
 * for functions that deal with objective-C objects/classes
 *
 * This header defines some utility wrappers for importing and using
 * the core bridge.
 *
 * This is the *only* header file that should be used to access
 * functionality in the core bridge.
 *
 * WARNING: this file is not part of the public interface of PyObjC and
 * might change or be removed without warning or regard for backward
 * compatibility.
 */

#include <objc/objc.h>

#import <Foundation/Foundation.h>

#include "pyobjc-compat.h"

#ifdef Py_LIMITED_API
/*
 * Make sure PyObjC framework wrappers can build using the limited API
 */
typedef void Py_buffer;
#endif

#include <objc/objc-runtime.h>

NS_ASSUME_NONNULL_BEGIN

/* Current API version, increase whenever:
 * - Semantics of current functions change
 * - Functions are removed
 *
 * Do not increase when adding a new function, the struct_len field
 * can be used for detecting if a function has been added.
 */
#ifndef PYOBJC_API_VERSION
#define PYOBJC_API_VERSION 25
#endif

#define PYOBJC_API_NAME "__C_API__"

#ifndef PyObjC_EXPECTED_STRUCT_SIZE
#define PyObjC_EXPECTED_STRUCT_SIZE (sizeof(struct pyobjc_api))
#endif

/*
 * Only add items to the end of this list!
 */
typedef int(RegisterMethodMappingFunctionType)(
    Class, SEL,
    PyObject* _Nullable (*_Nonnull)(PyObject* _Nonnull, PyObject* _Nonnull,
                                    PyObject* _Nonnull const* _Nonnull, size_t),
    IMP _Nullable (*_Nonnull)(PyObject* _Nonnull, PyObject* _Nonnull));

struct pyobjc_api {
    int                                api_version; /* API version */
    size_t                             struct_len;  /* Length of this struct */
    RegisterMethodMappingFunctionType* register_method_mapping;
    id _Nullable (*_Nonnull obj_get_object)(PyObject* _Nonnull);
    Class _Nullable (*_Nonnull cls_get_class)(PyObject* _Nonnull);
    int (*_Nonnull depythonify_python_object)(PyObject* _Nonnull, id _Nullable* _Nonnull);
    PyObject* _Nullable (*_Nonnull id_to_python)(id _Nullable);
    void (*_Nonnull err_objc_to_python)(NSObject* _Nonnull);
    int (*_Nonnull py_to_objc)(const char* _Nonnull, PyObject* _Nonnull, void* _Nonnull);
    PyObject* _Nullable (*_Nonnull objc_to_py)(const char* _Nonnull,
                                               const void* _Nonnull);
    Py_ssize_t (*_Nonnull sizeof_type)(const char* _Nonnull);
    Class _Nullable (*_Nonnull sel_get_class)(PyObject* _Nonnull sel);
    SEL _Nullable (*_Nonnull sel_get_sel)(PyObject* _Nonnull sel);
    int (*_Nonnull register_pointer_wrapper)(
        const char* _Nonnull, const char* _Nonnull,
        PyObject* _Nullable (*_Nonnull pythonify)(void* _Nonnull),
        int (*_Nonnull depythonify)(PyObject* _Nonnull, void* _Nonnull));
    IMP _Nullable (*_Nonnull unsupported_method_imp)(PyObject* _Nonnull,
                                                     PyObject* _Nonnull);
    PyObject* _Nullable (*_Nonnull unsupported_method_caller)(
        PyObject* _Nonnull, PyObject* _Nonnull, PyObject* _Nonnull const* _Nonnull,
        size_t);
    void (*_Nonnull err_python_to_objc_gil)(PyGILState_STATE* _Nonnull state);
    int (*_Nonnull simplify_sig)(const char* signature, char* buf, size_t buflen);
    void (*_Nonnull free_c_array)(int, Py_buffer*);
    int (*_Nonnull py_to_c_array)(BOOL, BOOL, const char* _Nonnull, PyObject* _Nonnull,
                                  void* _Nullable* _Nonnull, Py_ssize_t* _Nullable,
                                  PyObject* _Nonnull* _Nonnull, Py_buffer* _Nonnull);
    PyObject* _Nullable (*_Nonnull c_array_to_py)(const char* _Nonnull,
                                                  const void* _Nonnull, Py_ssize_t);
    PyTypeObject* _Nonnull imp_type;
    IMP _Nullable (*_Nonnull imp_get_imp)(PyObject* _Nonnull);
    SEL _Nullable (*_Nonnull imp_get_sel)(PyObject* _Nonnull);
    PyObject* _Nullable (*_Nonnull newtransient)(id _Nullable objc_object,
                                                 int* _Nonnull cookie);
    void (*_Nonnull releasetransient)(PyObject* _Nonnull proxy, int cookie);
    PyObject* _Nonnull* _Nonnull pyobjc_null;
    int (*_Nonnull dep_c_array_count)(const char* _Nonnull type, Py_ssize_t count,
                                      BOOL strict, PyObject* _Nonnull value,
                                      void* _Nonnull datum, BOOL, BOOL);
    PyObject* _Nullable (*_Nonnull varlistnew)(const char* _Nonnull tp,
                                               void* _Nonnull array);
    int (*_Nonnull pyobjcobject_convert)(PyObject* _Nonnull, void* _Nonnull);
    int (*_Nonnull register_id_alias)(const char* _Nonnull, const char* _Nonnull);
    int (*_Nonnull memview_check)(PyObject* _Nonnull);
    PyObject* _Nullable (*_Nonnull memview_new)(void);
    Py_buffer* _Nullable (*_Nonnull memview_getbuffer)(PyObject* _Nonnull);
    int (*_Nonnull checkargcount)(PyObject* _Nonnull callable, size_t min_args,
                                  size_t max_args, size_t nargsf);
    int (*_Nonnull checknokwnames)(PyObject* _Nonnull callable,
                                   PyObject* _Nullable kwnames);

    PyObject* _Nullable (*_Nonnull createopaquepointertype)(const char*, const char*, const char*);
};

#ifndef PYOBJC_BUILD

#ifndef PYOBJC_METHOD_STUB_IMPL
static struct pyobjc_api* PyObjC_API;
#endif /* PYOBJC_METHOD_STUB_IMPL */

#define PyObjCIMP_Check(obj) PyObject_TypeCheck(obj, PyObjC_API->imp_type)
#define PyObjCObject_GetObject (PyObjC_API->obj_get_object)
#define PyObjCClass_GetClass (PyObjC_API->cls_get_class)
#define PyObjCSelector_GetClass (PyObjC_API->sel_get_class)
#define PyObjCSelector_GetSelector (PyObjC_API->sel_get_sel)
#define depythonify_python_object (PyObjC_API->depythonify_python_object)
#define PyObjC_IdToPython (PyObjC_API->id_to_python)
#define PyObjCErr_FromObjC (PyObjC_API->err_objc_to_python)
#define PyObjCErr_ToObjCWithGILState (PyObjC_API->err_python_to_objc_gil)
#define PyObjC_PythonToObjC (PyObjC_API->py_to_objc)
#define PyObjC_ObjCToPython (PyObjC_API->objc_to_py)
#define PyObjC_RegisterMethodMapping (PyObjC_API->register_method_mapping)
#define PyObjCPointerWrapper_Register (PyObjC_API->register_pointer_wrapper)
#define PyObjCUnsupportedMethod_IMP (PyObjC_API->unsupported_method_imp)
#define PyObjCUnsupportedMethod_Caller (PyObjC_API->unsupported_method_caller)
#define PyObjCRT_SizeOfType (PyObjC_API->sizeof_type)
#define PyObjC_FreeCArray (PyObjC_API->free_c_array)
#define PyObjC_PythonToCArray (PyObjC_API->py_to_c_array)
#define PyObjC_CArrayToPython (PyObjC_API->c_array_to_py)
#define PyObjCIMP_GetIMP (PyObjC_API->imp_get_imp)
#define PyObjCIMP_GetSelector (PyObjC_API->imp_get_sel)
#define PyObjCObject_NewTransient (PyObjC_API->newtransient)
#define PyObjCObject_ReleaseTransient (PyObjC_API->releasetransient)
#define PyObjC_NULL (*(PyObjC_API->pyobjc_null))
#define PyObjC_DepythonifyCArray (PyObjC_API->dep_c_array_count)
#define PyObjCVarList_New (PyObjC_API->varlistnew)
#define PyObjCObject_Convert (PyObjC_API->pyobjcobject_convert)
#define PyObjCPointerWrapper_RegisterID (PyObjC_API->register_id_alias)
#define PyObjCMemView_Check (PyObjC_API->memview_check)
#define PyObjCMemView_New (PyObjC_API->memview_new)
#define PyObjCMemView_GetBuffer (PyObjC_API->memview_getbuffer)
#define PyObjC_CheckArgCount (PyObjC_API->checkargcount)
#define PyObjC_CheckNoKwnames (PyObjC_API->checknokwnames)
#define PyObjCCreateOpaquePointerType (PyObjC_API->createopaquepointertype)

typedef void (*PyObjC_Function_Pointer)(void);
typedef struct PyObjC_function_map {
    const char*             name;
    PyObjC_Function_Pointer function;
} PyObjC_function_map;

#ifndef PYOBJC_METHOD_STUB_IMPL

static inline PyObject*
PyObjC_CreateInlineTab(PyObjC_function_map* map)
{
    return PyCapsule_New(map, "objc.__inline__", NULL);
}

static inline int
PyObjC_ImportAPI(PyObject* calling_module)
{
    PyObjC_API = (struct pyobjc_api*)PyCapsule_Import("objc." PYOBJC_API_NAME, 0);
    if (PyObjC_API == NULL) {
        return -1;
    }
    if (PyObjC_API->api_version != PYOBJC_API_VERSION) {
        PyErr_Format(PyExc_RuntimeError,
                     "Wrong version of PyObjC C API (got %d, expected %d)",
                     (int)PyObjC_API->api_version, (int)PYOBJC_API_VERSION);
        return -1;
    }

    if (PyObjC_API->struct_len < PyObjC_EXPECTED_STRUCT_SIZE) {
        PyErr_Format(PyExc_RuntimeError,
                     "Wrong struct-size of PyObjC C API (got %d, expected %d)",
                     (int)PyObjC_API->struct_len, (int)sizeof(struct pyobjc_api));
        return -1;
    }

    /* Current pyobjc implementation doesn't allow deregistering
     * information, avoid unloading of users of the C-API.
     * (Yes this is ugle, patches to fix this situation are apriciated)
     */
    Py_INCREF(calling_module);

    return 0;
}
#endif /* PYOBJC_METHOD_STUB_IMPL */

#else /* PyObjC_BUILD */

extern struct pyobjc_api objc_api;
extern int               PyObjCAPI_Register(PyObject* module);

#endif /* !PYOBJC_BUILD */

NS_ASSUME_NONNULL_END

#endif /* PyObjC_API_H */
