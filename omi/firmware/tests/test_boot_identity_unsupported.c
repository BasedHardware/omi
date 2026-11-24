#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../omi/src/boot_identity.h"
int main(void)
{
    uint8_t first[44], second[44];
    omi_boot_identity_snapshot(first);
    assert(first[0] == 1 && first[1] == OMI_BOOT_IDENTITY_NOT_READY);
    for (unsigned i = 12; i < 44; ++i)
        assert(first[i] == 0);
    omi_boot_identity_prepare();
    omi_boot_identity_snapshot(first);
    assert(first[1] == OMI_BOOT_IDENTITY_UNSUPPORTED);
    omi_boot_identity_prepare();
    omi_boot_identity_snapshot(second);
    assert(memcmp(first, second, 44) == 0);
    memset(first, 0xff, 44);
    omi_boot_identity_snapshot(first);
    assert(memcmp(first, second, 44) == 0);
    puts("boot identity unsupported/not-ready/repeated prepare/immutable snapshot PASS");
}
