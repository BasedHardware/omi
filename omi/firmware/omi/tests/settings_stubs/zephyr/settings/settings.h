#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

typedef int (*settings_read_cb)(void *, void *, size_t);
typedef int (*settings_set_cb)(const char *, size_t, settings_read_cb, void *);

#define SETTINGS_STATIC_HANDLER_DEFINE(id, name, get, set, commit, export)                                             \
    static settings_set_cb registered_settings_set = set

static inline bool settings_name_steq(const char *name, const char *key, const char **next)
{
    *next = NULL;
    return strcmp(name, key) == 0;
}

int settings_subsys_init(void);
int settings_load_subtree(const char *name);
int settings_save_one(const char *name, const void *value, size_t len);
int settings_delete(const char *name);
