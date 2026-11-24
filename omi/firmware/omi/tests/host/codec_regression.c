#include <limits.h>
#include <stdio.h>

#include "source/lib/core/codec.c"
static void reset(int size)
{
    required_size = size;
    size_calls = init_calls = ctl_calls = init_result = fail_ctl = 0;
    thread_calls = ring_init_calls = err_logs = warn_logs = 0;
}
int main(void)
{
    const int good[] = {1, 7180, 10915, 10916};
    for (size_t i = 0; i < sizeof(good) / sizeof(*good); i++) {
        reset(good[i]);
        assert(codec_start() == 0);
        assert(size_calls == 1 && init_calls == 1 && ctl_calls == 9 && thread_calls == 1 && ring_init_calls == 1 &&
               err_logs == 0);
        printf("PASS size %d\n", good[i]);
    }
    const int bad[] = {INT_MIN, -1, 0, 10917, INT_MAX};
    for (size_t i = 0; i < sizeof(bad) / sizeof(*bad); i++) {
        reset(bad[i]);
        assert(codec_start() == -1);
        assert(size_calls == 1 && init_calls == 0 && ctl_calls == 0 && thread_calls == 0 && ring_init_calls == 0 &&
               err_logs == 1);
        printf("PASS rejected size %d before init/thread\n", bad[i]);
    }
    reset(7180);
    init_result = -3;
    assert(codec_start() == -1);
    assert(init_calls == 1 && ctl_calls == 0 && thread_calls == 0 && last_error_value == 0);
    puts("PASS init error abort; candidate init evaluated once");
    for (int i = 1; i <= 9; i++) {
        reset(7180);
        fail_ctl = i;
        assert(codec_start() == -1);
        assert(ctl_calls == i && thread_calls == 0 && ring_init_calls == 0 && last_error_value == 0);
        printf("PASS ctl %d abort; candidate ctl evaluated once\n", i);
    }
    for (int i = -7; i <= 0; i++) {
        encode_result = i;
        assert(execute_codec() == 0);
    }
    encode_result = 80;
    assert(execute_codec() == 80);
    encode_result = 160;
    assert(execute_codec() == 160);
    puts("PASS encoder errors/zero/positive lengths (stubbed Opus)");
    puts("ALL HOST CHECKS PASSED; not NCS, real Opus, hardware or full integration qualification");
}
