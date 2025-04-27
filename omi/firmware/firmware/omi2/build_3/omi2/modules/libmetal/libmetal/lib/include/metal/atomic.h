/*
 * Copyright (c) 2015, Xilinx Inc. and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/*
 * @file	atomic.h
 * @brief	Atomic primitives for libmetal.
 */

#ifndef __METAL_ATOMIC__H__
#define __METAL_ATOMIC__H__

#include <metal/config.h>

#if defined(__cplusplus)
# include <cstdint>

/*
 * <atomic> has the same functionality as <stdatomic.h> but all members are only
 * accessible in the std namespace. As the rest of libmetal is pure C, it does
 * not know about namespaces, even when compiled as part of a C++ file. So we
 * just export the members of <atomic> into the global namespace.
 */
# include <atomic>
using std::atomic_flag;
using std::memory_order;
using std::memory_order_relaxed;
using std::memory_order_consume;
using std::memory_order_acquire;
using std::memory_order_release;
using std::memory_order_acq_rel;
using std::memory_order_seq_cst;

using std::atomic_bool;
using std::atomic_char;
using std::atomic_schar;
using std::atomic_uchar;
using std::atomic_short;
using std::atomic_ushort;
using std::atomic_int;
using std::atomic_uint;
using std::atomic_long;
using std::atomic_ulong;
using std::atomic_llong;
using std::atomic_ullong;
using std::atomic_char16_t;
using std::atomic_char32_t;
using std::atomic_wchar_t;
using std::atomic_int_least8_t;
using std::atomic_uint_least8_t;
using std::atomic_int_least16_t;
using std::atomic_uint_least16_t;
using std::atomic_int_least32_t;
using std::atomic_uint_least32_t;
using std::atomic_int_least64_t;
using std::atomic_uint_least64_t;
using std::atomic_int_fast8_t;
using std::atomic_uint_fast8_t;
using std::atomic_int_fast16_t;
using std::atomic_uint_fast16_t;
using std::atomic_int_fast32_t;
using std::atomic_uint_fast32_t;
using std::atomic_int_fast64_t;
using std::atomic_uint_fast64_t;
using std::atomic_intptr_t;
using std::atomic_uintptr_t;
using std::atomic_size_t;
using std::atomic_ptrdiff_t;
using std::atomic_intmax_t;
using std::atomic_uintmax_t;

using std::atomic_flag_test_and_set;
using std::atomic_flag_test_and_set_explicit;
using std::atomic_flag_clear;
using std::atomic_flag_clear_explicit;
using std::atomic_init;
using std::atomic_is_lock_free;
using std::atomic_store;
using std::atomic_store_explicit;
using std::atomic_load;
using std::atomic_load_explicit;
using std::atomic_exchange;
using std::atomic_exchange_explicit;
using std::atomic_compare_exchange_strong;
using std::atomic_compare_exchange_strong_explicit;
using std::atomic_compare_exchange_weak;
using std::atomic_compare_exchange_weak_explicit;
using std::atomic_fetch_add;
using std::atomic_fetch_add_explicit;
using std::atomic_fetch_sub;
using std::atomic_fetch_sub_explicit;
using std::atomic_fetch_or;
using std::atomic_fetch_or_explicit;
using std::atomic_fetch_xor;
using std::atomic_fetch_xor_explicit;
using std::atomic_fetch_and;
using std::atomic_fetch_and_explicit;
using std::atomic_thread_fence;
using std::atomic_signal_fence;

#elif defined(HAVE_STDATOMIC_H) && !defined(__CC_ARM) && !defined(__arm__) && \
      !defined(__STDC_NO_ATOMICS__)
# include <stdint.h>
# include <stdatomic.h>
#elif defined(__GNUC__)
# include <metal/compiler/gcc/atomic.h>
#else
#if defined(HAVE_PROCESSOR_ATOMIC_H)
# include <metal/processor/arm/atomic.h>
#else
# include <metal/processor/generic/atomic.h>
#endif /* defined(HAVE_PROCESSOR_ATOMIC_H) */
#endif

#endif /* __METAL_ATOMIC__H__ */
