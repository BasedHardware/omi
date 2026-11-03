#ifndef TEST_SETTINGS_H
#define TEST_SETTINGS_H
#include <stddef.h>
#include <sys/types.h>
typedef ssize_t (*settings_read_cb)(void *, void *, size_t);
int settings_save_one(const char *, const void *, size_t);
int settings_subsys_init(void);
typedef int (*settings_load_direct_cb)(const char *, size_t, settings_read_cb, void *, void *);
int settings_load_subtree_direct(const char *, settings_load_direct_cb, void *);
#endif
