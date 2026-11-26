cmake_minimum_required(VERSION 3.22.1)

project(omittsmp3 C)

add_library(omittsmp3 SHARED tts_mp3_decoder_jni.c)

find_library(log-lib log)
target_link_libraries(omittsmp3 ${log-lib})

# Require 16 KB page alignment for Android 15+ devices. NDK r28 (this project's NDK)
# already links with 16 KB alignment by default; the flag documents the requirement.
target_link_options(omittsmp3 PRIVATE "-Wl,-z,max-page-size=16384")
