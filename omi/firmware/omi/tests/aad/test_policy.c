#include <assert.h>
#include <stdio.h>

#include "aad_policy.h"

int main(void)
{
    /* Exhaust the state matrix: sleep must never treat continuous/batch audio
     * as live merely because it uses audio CCC. Charger/flag-off preserve the
     * base policy; transfers retain the veto in all combinations. */
    for (unsigned bits = 0; bits < 128; ++bits) {
        struct aad_policy_inputs in = {
            .retention_enabled = (bits & 64) != 0,
            .connected_quiet_enabled = (bits & 1) != 0,
            .connected = (bits & 2) != 0,
            .subscribed = (bits & 4) != 0,
            .live_mode = (bits & 8) != 0,
            .charging = (bits & 16) != 0,
            .transfer_active = (bits & 32) != 0,
        };
        int64_t hold = aad_policy_timeout(&in, 10000, 120000);
        if (in.transfer_active) {
            assert(hold == 0);
        } else if (!in.connected_quiet_enabled || in.charging || !in.connected) {
            assert(hold == 10000);
        } else if (in.live_mode && (in.subscribed || in.retention_enabled)) {
            assert(hold == 120000);
        } else {
            assert(hold == 0);
        }
    }
    struct aad_policy_inputs live = {
        .connected_quiet_enabled = true, .connected = true, .subscribed = true, .live_mode = true};
    assert(aad_policy_timeout(&live, 10000, 1000) == 1000);
    assert(aad_policy_timeout(&live, 10000, 3600000) == 3600000);
    puts("AAD policy: 128 state combinations passed");
    return 0;
}
