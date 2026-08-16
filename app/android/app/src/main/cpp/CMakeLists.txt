# Builds libphonemicopus.so — the app-owned JNI shim that bridges Kotlin
# PhoneMicOpusEncoder to libopus (which ships separately via opus_flutter_android).
cmake_minimum_required(VERSION 3.22.1)

project(phonemicopus C)

add_library(phonemicopus SHARED phone_mic_opus_jni.c)

find_library(log-lib log)
target_link_libraries(phonemicopus ${log-lib})

# Require 16 KB page alignment for Android 15+ devices. NDK r28 (this project's NDK)
# already links with 16 KB alignment by default; the flag documents the requirement.
target_link_options(phonemicopus PRIVATE "-Wl,-z,max-page-size=16384")
