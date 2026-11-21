#ifndef CV1_SOURCE_BINDING_H
#define CV1_SOURCE_BINDING_H
#include "secure_services.h"
#include "storage_adapter.h"
/* Fixed trusted bank, context remains Secure/immutable through the lease. */
struct cv1_storage_binding {
    struct cv1_storage *storage;
    unsigned bank;
};
struct cv1_source cv1_bound_source(struct cv1_storage_binding *);
#endif
