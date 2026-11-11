# Applied to every CV1 sysbuild, including developer builds. Never edit the SDK.
set(mcuboot_CMAKE_PROJECT_INCLUDE "${APP_DIR}/sysbuild/mcuboot-main.cmake"
    CACHE FILEPATH "CV1 MCUboot application overlay" FORCE)
