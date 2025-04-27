/*
 * Copyright (c) 2018, Linaro Limited. and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/*
 * @file	zephyr/cache.h
 * @brief	Zephyr cache operation primitives for libmetal.
 */

#ifndef __METAL_CACHE__H__
#error "Include metal/cache.h instead of metal/zephyr/cache.h"
#endif

#ifndef __METAL_ZEPHYR_CACHE__H__
#define __METAL_ZEPHYR_CACHE__H__

#include <zephyr/cache.h>
#include <metal/utilities.h>

#ifdef __cplusplus
extern "C" {
#endif

static inline void __metal_cache_flush(void *addr, unsigned int len)
{
	sys_cache_data_flush_range(addr, len);
}

static inline void __metal_cache_invalidate(void *addr, unsigned int len)
{
	sys_cache_data_invd_range(addr, len);
}

#ifdef __cplusplus
}
#endif

#endif /* __METAL_ZEPHYR_CACHE__H__ */
