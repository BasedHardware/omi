/*
 * Copyright (c) 2015, Xilinx Inc. and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/*
 * @file	cpu.h
 * @brief	CPU primitives for libmetal.
 */

#ifndef __METAL_CPU__H__
#define __METAL_CPU__H__

#include <metal/config.h>

#if defined(HAVE_PROCESSOR_CPU_H)
# include <metal/processor/arm/cpu.h>
#else
# include <metal/processor/generic/cpu.h>
#endif

#endif /* __METAL_CPU__H__ */
