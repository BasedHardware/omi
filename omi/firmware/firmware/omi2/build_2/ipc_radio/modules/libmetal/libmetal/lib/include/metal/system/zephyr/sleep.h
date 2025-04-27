/*
 * Copyright (c) 2018, Linaro Limited. and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/*
 * @file	zephyr/sleep.h
 * @brief	Zephyr sleep primitives for libmetal.
 */

#ifndef __METAL_SLEEP__H__
#error "Include metal/sleep.h instead of metal/zephyr/sleep.h"
#endif

#ifndef __METAL_ZEPHYR_SLEEP__H__
#define __METAL_ZEPHYR_SLEEP__H__

#include <zephyr/kernel.h>

#ifdef __cplusplus
extern "C" {
#endif

static inline int __metal_sleep_usec(unsigned int usec)
{
	k_sleep(K_USEC(usec));
	return 0;
}

#ifdef __cplusplus
}
#endif

#endif /* __METAL_ZEPHYR_SLEEP__H__ */
