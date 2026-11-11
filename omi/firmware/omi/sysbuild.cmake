# Applied to every CV1 sysbuild, including developer builds. Never edit the SDK.
# Zephyr's zephyr_get() consumes this image-scoped module setting; arbitrary
# CMake project hooks are not automatically forwarded by sysbuild.
list(APPEND mcuboot_EXTRA_ZEPHYR_MODULES "${APP_DIR}/sysbuild/mcuboot-main")
list(REMOVE_DUPLICATES mcuboot_EXTRA_ZEPHYR_MODULES)
set(mcuboot_EXTRA_ZEPHYR_MODULES "${mcuboot_EXTRA_ZEPHYR_MODULES}"
    CACHE STRING "CV1 MCUboot application overlay module" FORCE)
