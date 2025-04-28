/*-
 * Copyright (c) 2020 STMicroelectronics. All rights reserved.
 *
 * Copyright (c) 1982, 1986, 1989, 1993
 *	The Regents of the University of California.  All rights reserved.
 * (c) UNIX System Laboratories, Inc.
 * Copyright 2023 Arm Limited and/or its affiliates <open-source-office@arm.com>
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#ifndef __METAL_ARMCC_ERRNO__H__
#define __METAL_ARMCC_ERRNO__H__

#include <errno.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LIBMETAL_ERR_BASE  100

#ifndef EPERM
#define	EPERM	(LIBMETAL_ERR_BASE + 1)  /* Operation not permitted */
#endif

#ifndef ENOENT
#define	ENOENT	(LIBMETAL_ERR_BASE + 2)  /* No such file or directory */
#endif

#ifndef ESRCH
#define	ESRCH	(LIBMETAL_ERR_BASE + 3)  /* No such process */
#endif

#ifndef EINTR
#define	EINTR	(LIBMETAL_ERR_BASE + 4)  /* Interrupted system call */
#endif

#ifndef EIO
#define	EIO	(LIBMETAL_ERR_BASE + 5)  /* Input/output error */
#endif

#ifndef ENXIO
#define	ENXIO	(LIBMETAL_ERR_BASE + 6)  /* Device not configured */
#endif

#ifndef E2BIG
#define	E2BIG	(LIBMETAL_ERR_BASE + 7)  /* Argument list too long */
#endif

#ifndef ENOEXEC
#define	ENOEXEC	(LIBMETAL_ERR_BASE + 8)  /* Exec format error */
#endif

#ifndef EBADF
#define	EBADF	(LIBMETAL_ERR_BASE + 9)  /* Bad file descriptor */
#endif

#ifndef ECHILD
#define	ECHILD	(LIBMETAL_ERR_BASE + 10) /* No child processes */
#endif

#ifndef EDEADLK
#define	EDEADLK	(LIBMETAL_ERR_BASE + 11) /* Resource deadlock avoided */
#endif

#ifndef EACCES
#define	EACCES	(LIBMETAL_ERR_BASE + 13) /* Permission denied */
#endif

#ifndef EFAULT
#define	EFAULT	(LIBMETAL_ERR_BASE + 14) /* Bad address */
#endif

#ifndef ENOTBLK
#define	ENOTBLK	(LIBMETAL_ERR_BASE + 15) /* Block device required */
#endif

#ifndef EBUSY
#define	EBUSY	(LIBMETAL_ERR_BASE + 16) /* Device busy */
#endif

#ifndef EEXIST
#define	EEXIST	(LIBMETAL_ERR_BASE + 17) /* File exists */
#endif

#ifndef EXDEV
#define	EXDEV	(LIBMETAL_ERR_BASE + 18) /* Cross-device link */
#endif

#ifndef ENODEV
#define	ENODEV	(LIBMETAL_ERR_BASE + 19) /* Operation not supported by device */
#endif

#ifndef ENOTDIR
#define	ENOTDIR	(LIBMETAL_ERR_BASE + 20) /* Not a directory */
#endif

#ifndef EISDIR
#define	EISDIR	(LIBMETAL_ERR_BASE + 21) /* Is a directory */
#endif

#ifndef ENFILE
#define	ENFILE	(LIBMETAL_ERR_BASE + 23) /* Too many open files in system */
#endif

#ifndef EMFILE
#define	EMFILE	(LIBMETAL_ERR_BASE + 24) /* Too many open files */
#endif

#ifndef ENOTTY
#define	ENOTTY	(LIBMETAL_ERR_BASE + 25) /* Inappropriate ioctl for device */
#endif

#ifndef ETXTBSY
#define	ETXTBSY	(LIBMETAL_ERR_BASE + 26) /* Text file busy */
#endif

#ifndef EFBIG
#define	EFBIG	(LIBMETAL_ERR_BASE + 27) /* File too large */
#endif

#ifndef ENOSPC
#define	ENOSPC	(LIBMETAL_ERR_BASE + 28) /* No space left on device */
#endif

#ifndef ESPIPE
#define	ESPIPE	(LIBMETAL_ERR_BASE + 29) /* Illegal seek */
#endif

#ifndef EROFS
#define	EROFS	(LIBMETAL_ERR_BASE + 30) /* Read-only filesystem */
#endif

#ifndef EMLINK
#define	EMLINK	(LIBMETAL_ERR_BASE + 31) /* Too many links */
#endif

#ifndef EPIPE
#define	EPIPE	(LIBMETAL_ERR_BASE + 32) /* Broken pipe */
#endif

#ifndef EAGAIN
#define	EAGAIN	(LIBMETAL_ERR_BASE + 35) /* Resource temporarily unavailable */
#endif

#ifdef __cplusplus
}
#endif

#endif /* __METAL_ARMCC_ERRNO__H__ */
