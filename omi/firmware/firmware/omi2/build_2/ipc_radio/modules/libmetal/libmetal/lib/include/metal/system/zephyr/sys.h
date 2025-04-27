/*
 * Copyright (c) 2017, Linaro Limited. and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/*
 * @file	zephyr/sys.h
 * @brief	Zephyr system primitives for libmetal.
 */

#ifndef __METAL_SYS__H__
#error "Include metal/sys.h instead of metal/zephyr/sys.h"
#endif

#ifndef __METAL_ZEPHYR_SYS__H__
#define __METAL_ZEPHYR_SYS__H__

#include <stdlib.h>
#include <zephyr/kernel.h>

#ifdef __cplusplus
extern "C" {
#endif

#define METAL_INIT_DEFAULTS				\
{							\
	.log_handler	= metal_zephyr_log_handler,	\
	.log_level	= METAL_LOG_INFO,		\
}

#ifndef METAL_MAX_DEVICE_REGIONS
#define METAL_MAX_DEVICE_REGIONS 1
#endif

/** Structure of zephyr libmetal runtime state. */
struct metal_state {

	/** Common (system independent) data. */
	struct metal_common_state common;
};

static inline void metal_wait_usec(uint32_t usec_to_wait)
{
	k_busy_wait(usec_to_wait);
}

#ifdef __cplusplus
}
#endif

#endif /* __METAL_ZEPHYR_SYS__H__ */
