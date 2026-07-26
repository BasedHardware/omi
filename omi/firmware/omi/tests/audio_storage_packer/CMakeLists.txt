cmake_minimum_required(VERSION 3.20)
project(audio_storage_packer_tests C)

enable_testing()

add_executable(audio_storage_packer_tests
    test_audio_storage_packer.c
    ../../src/lib/core/audio_storage_packer.c
    ../../src/lib/core/ring_transfer_integrity.c
    ../../src/lib/core/rtc_elapsed_recovery.c
    ../../src/lib/core/rtc_time_state.c
    ../../src/lib/core/sd_ring_durability.c
    ../../src/lib/core/sd_ring_recovery.c
    ../../src/lib/core/sd_write_recovery.c
    ../../src/lib/core/storage_readiness.c
)
target_compile_options(audio_storage_packer_tests PRIVATE -Wall -Wextra -Werror)

add_test(NAME audio_storage_packer_tests COMMAND audio_storage_packer_tests)
