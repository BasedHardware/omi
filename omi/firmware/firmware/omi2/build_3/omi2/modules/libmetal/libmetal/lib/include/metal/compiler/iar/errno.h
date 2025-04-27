/*-
 * Copyright (c) 2020 STMicroelectronics. All rights reserved.
 *
 * Copyright (c) 1982, 1986, 1989, 1993
 *	The Regents of the University of California.  All rights reserved.
 * (c) UNIX System Laboratories, Inc.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#ifndef __METAL_IAR_ERRNO__H__
#define __METAL_IAR_ERRNO__H__

#include <errno.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LIBMETAL_ERR_BASE  100

#define	EPERM	(LIBMETAL_ERR_BASE + 1)  /* Operation not permitted */
#define	ENOENT	(LIBMETAL_ERR_BASE + 2)  /* No such file or directory */
#define	ESRCH	(LIBMETAL_ERR_BASE + 3)  /* No such process */
#define	EINTR	(LIBMETAL_ERR_BASE + 4)  /* Interrupted system call */
#define	EIO	(LIBMETAL_ERR_BASE + 5)  /* Input/output error */
#define	ENXIO	(LIBMETAL_ERR_BASE + 6)  /* Device not configured */
#define	E2BIG	(LIBMETAL_ERR_BASE + 7)  /* Argument list too long */
#define	ENOEXEC	(LIBMETAL_ERR_BASE + 8)  /* Exec format error */
#define	EBADF	(LIBMETAL_ERR_BASE + 9)  /* Bad file descriptor */
#define	ECHILD	(LIBMETAL_ERR_BASE + 10) /* No child processes */
#define	EDEADLK	(LIBMETAL_ERR_BASE + 11) /* Resource deadlock avoided */
#define	ENOMEM	(LIBMETAL_ERR_BASE + 12) /* Cannot allocate memory */
#define	EACCES	(LIBMETAL_ERR_BASE + 13) /* Permission denied */
#define	EFAULT	(LIBMETAL_ERR_BASE + 14) /* Bad address */
#define	ENOTBLK	(LIBMETAL_ERR_BASE + 15) /* Block device required */
#define	EBUSY	(LIBMETAL_ERR_BASE + 16) /* Device busy */
#define	EEXIST	(LIBMETAL_ERR_BASE + 17) /* File exists */
#define	EXDEV	(LIBMETAL_ERR_BASE + 18) /* Cross-device link */
#define	ENODEV	(LIBMETAL_ERR_BASE + 19) /* Operation not supported by device */
#define	ENOTDIR	(LIBMETAL_ERR_BASE + 20) /* Not a directory */
#define	EISDIR	(LIBMETAL_ERR_BASE + 21) /* Is a directory */
#define	EINVAL	(LIBMETAL_ERR_BASE + 22) /* Invalid argument */
#define	ENFILE	(LIBMETAL_ERR_BASE + 23) /* Too many open files in system */
#define	EMFILE	(LIBMETAL_ERR_BASE + 24) /* Too many open files */
#define	ENOTTY	(LIBMETAL_ERR_BASE + 25) /* Inappropriate ioctl for device */
#define	ETXTBSY	(LIBMETAL_ERR_BASE + 26) /* Text file busy */
#define	EFBIG	(LIBMETAL_ERR_BASE + 27) /* File too large */
#define	ENOSPC	(LIBMETAL_ERR_BASE + 28) /* No space left on device */
#define	ESPIPE	(LIBMETAL_ERR_BASE + 29) /* Illegal seek */
#define	EROFS	(LIBMETAL_ERR_BASE + 30) /* Read-only filesystem */
#define	EMLINK	(LIBMETAL_ERR_BASE + 31) /* Too many links */
#define	EPIPE	(LIBMETAL_ERR_BASE + 32) /* Broken pipe */
#define	EAGAIN	(LIBMETAL_ERR_BASE + 35) /* Resource temporarily unavailable */

#ifdef __cplusplus
}
#endif

#endif /* __METAL_IAR_ERRNO__H__ */
