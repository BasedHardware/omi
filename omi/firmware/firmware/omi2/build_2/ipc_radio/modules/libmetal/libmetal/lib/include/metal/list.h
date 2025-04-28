/*
 * Copyright (c) 2015, Xilinx Inc. and Contributors. All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/*
 * @file	list.h
 * @brief	List primitives for libmetal.
 */

#ifndef __METAL_LIST__H__
#define __METAL_LIST__H__

#include <stdbool.h>
#include <stdlib.h>

#ifdef __cplusplus
extern "C" {
#endif

/** \defgroup list List Primitives
 *  @{
 */

struct metal_list {
	struct metal_list *next, *prev;
};

/*
 * METAL_INIT_LIST - used for initializing an list element in a static struct
 * or global
 */
#define METAL_INIT_LIST(name) { .next = &name, .prev = &name }
/*
 * METAL_DECLARE_LIST - used for defining and initializing a global or
 * static singleton list
 */
#define METAL_DECLARE_LIST(name)			\
	struct metal_list name = METAL_INIT_LIST(name)

static inline void metal_list_init(struct metal_list *list)
{
	list->prev = list;
	list->next = list;
}

static inline void metal_list_add_before(struct metal_list *node,
					 struct metal_list *new_node)
{
	new_node->prev = node->prev;
	new_node->next = node;
	new_node->next->prev = new_node;
	new_node->prev->next = new_node;
}

static inline void metal_list_add_after(struct metal_list *node,
					struct metal_list *new_node)
{
	new_node->prev = node;
	new_node->next = node->next;
	new_node->next->prev = new_node;
	new_node->prev->next = new_node;
}

static inline void metal_list_add_head(struct metal_list *list,
				       struct metal_list *node)
{
	metal_list_add_after(list, node);
}

static inline void metal_list_add_tail(struct metal_list *list,
				       struct metal_list *node)
{
	metal_list_add_before(list, node);
}

static inline int metal_list_is_empty(struct metal_list *list)
{
	return list->next == list;
}

static inline void metal_list_del(struct metal_list *node)
{
	node->next->prev = node->prev;
	node->prev->next = node->next;
	node->prev = node;
	node->next = node;
}

static inline struct metal_list *metal_list_first(struct metal_list *list)
{
	return metal_list_is_empty(list) ? NULL : list->next;
}

/**
 * @brief	Used for iterating over a list
 *
 * @param	list	Pointer to the head node of the list
 * @param	node	Pointer to each node in the list during iteration
 */
#define metal_list_for_each(list, node)		\
	for ((node) = (list)->next;		\
	     (node) != (list);			\
	     (node) = (node)->next)

/**
 * @brief	Used for iterating over a list safely
 *
 * @param	list	Pointer to the head node of the list
 * @param	temp	Pointer to the next node's address during iteration
 * @param	node	Pointer to each node in the list during iteration
 */
#define metal_list_for_each_safe(list, temp, node)		\
	for ((node) = (list)->next, (temp) = (node)->next;	\
	     (node) != (list);					\
	     (node) = (temp), (temp) = (node)->next)

static inline bool metal_list_find_node(struct metal_list *list,
					struct metal_list *node)
{
	struct metal_list *n;

	metal_list_for_each(list, n) {
		if (n == node)
			return true;
	}
	return false;
}
/** @} */

#ifdef __cplusplus
}
#endif

#endif /* __METAL_LIST__H__ */
