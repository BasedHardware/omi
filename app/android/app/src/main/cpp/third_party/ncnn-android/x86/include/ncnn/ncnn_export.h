
#ifndef NCNN_EXPORT_H
#define NCNN_EXPORT_H

#ifdef NCNN_STATIC_DEFINE
#  define NCNN_EXPORT
#  define NCNN_NO_EXPORT
#else
#  ifndef NCNN_EXPORT
#    ifdef ncnn_EXPORTS
        /* We are building this library */
#      define NCNN_EXPORT 
#    else
        /* We are using this library */
#      define NCNN_EXPORT 
#    endif
#  endif

#  ifndef NCNN_NO_EXPORT
#    define NCNN_NO_EXPORT 
#  endif
#endif

#ifndef NCNN_DEPRECATED
#  define NCNN_DEPRECATED __attribute__ ((__deprecated__))
#endif

#ifndef NCNN_DEPRECATED_EXPORT
#  define NCNN_DEPRECATED_EXPORT NCNN_EXPORT NCNN_DEPRECATED
#endif

#ifndef NCNN_DEPRECATED_NO_EXPORT
#  define NCNN_DEPRECATED_NO_EXPORT NCNN_NO_EXPORT NCNN_DEPRECATED
#endif

/* NOLINTNEXTLINE(readability-avoid-unconditional-preprocessor-if) */
#if 0 /* DEFINE_NO_DEPRECATED */
#  ifndef NCNN_NO_DEPRECATED
#    define NCNN_NO_DEPRECATED
#  endif
#endif

#endif /* NCNN_EXPORT_H */
