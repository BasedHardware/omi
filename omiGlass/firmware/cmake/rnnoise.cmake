add_library(rnnoise STATIC
    ${CMAKE_CURRENT_LIST_DIR}/../lib/rnnoise/src/denoise.c
    ${CMAKE_CURRENT_LIST_DIR}/../lib/rnnoise/src/rnn.c
    ${CMAKE_CURRENT_LIST_DIR}/../lib/rnnoise/src/pitch.c
    ${CMAKE_CURRENT_LIST_DIR}/../lib/rnnoise/src/kiss_fft.c
    ${CMAKE_CURRENT_LIST_DIR}/../lib/rnnoise/src/celt_lpc.c
    ${CMAKE_CURRENT_LIST_DIR}/../lib/rnnoise/src/rnn_data.c
)

target_include_directories(rnnoise PUBLIC
    ${CMAKE_CURRENT_LIST_DIR}/../lib/rnnoise/include
    ${CMAKE_CURRENT_LIST_DIR}/../lib/rnnoise/src
)

target_compile_definitions(rnnoise PUBLIC
    OVERRIDE_RNNOISE_ALLOC
    OVERRIDE_RNNOISE_FREE
)

