if("${SB_CONFIG_NET_CORE_BOARD}" STREQUAL "")
    message(FATAL_ERROR "No simulated nRF5340 network core selected")
endif()

ExternalZephyrProject_Add(
    APPLICATION hci_ipc
    SOURCE_DIR ${ZEPHYR_BASE}/samples/bluetooth/hci_ipc
    BOARD ${SB_CONFIG_NET_CORE_BOARD}
)

native_simulator_set_child_images(${DEFAULT_IMAGE} hci_ipc)
native_simulator_set_final_executable(${DEFAULT_IMAGE})
