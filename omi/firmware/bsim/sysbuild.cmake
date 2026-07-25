if("${SB_CONFIG_NET_CORE_BOARD}" STREQUAL "")
    message(FATAL_ERROR "No simulated nRF5340 network core selected")
endif()

ExternalZephyrProject_Add(
    APPLICATION hci_ipc
    SOURCE_DIR ${ZEPHYR_BASE}/samples/bluetooth/hci_ipc
    BOARD ${SB_CONFIG_NET_CORE_BOARD}
)

set_config_bool(hci_ipc CONFIG_BT_LL_SOFTDEVICE n)
set_config_bool(hci_ipc CONFIG_BT_LL_SW_SPLIT y)

native_simulator_set_child_images(${DEFAULT_IMAGE} hci_ipc)
native_simulator_set_final_executable(${DEFAULT_IMAGE})
