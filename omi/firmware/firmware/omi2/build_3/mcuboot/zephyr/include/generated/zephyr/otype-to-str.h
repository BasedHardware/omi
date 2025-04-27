/* Core kernel objects */
case K_OBJ_MEM_SLAB: ret = "k_mem_slab"; break;
case K_OBJ_MSGQ: ret = "k_msgq"; break;
case K_OBJ_MUTEX: ret = "k_mutex"; break;
case K_OBJ_PIPE: ret = "k_pipe"; break;
case K_OBJ_QUEUE: ret = "k_queue"; break;
case K_OBJ_POLL_SIGNAL: ret = "k_poll_signal"; break;
case K_OBJ_SEM: ret = "k_sem"; break;
case K_OBJ_STACK: ret = "k_stack"; break;
case K_OBJ_THREAD: ret = "k_thread"; break;
case K_OBJ_TIMER: ret = "k_timer"; break;
case K_OBJ_THREAD_STACK_ELEMENT: ret = "z_thread_stack_element"; break;
case K_OBJ_NET_SOCKET: ret = "NET_SOCKET"; break;
case K_OBJ_NET_IF: ret = "net_if"; break;
case K_OBJ_SYS_MUTEX: ret = "sys_mutex"; break;
case K_OBJ_FUTEX: ret = "k_futex"; break;
case K_OBJ_CONDVAR: ret = "k_condvar"; break;
#ifdef CONFIG_EVENTS
case K_OBJ_EVENT: ret = "k_event"; break;
#endif
#ifdef CONFIG_ZTEST
case K_OBJ_ZTEST_SUITE_NODE: ret = "ztest_suite_node"; break;
#endif
#ifdef CONFIG_ZTEST
case K_OBJ_ZTEST_SUITE_STATS: ret = "ztest_suite_stats"; break;
#endif
#ifdef CONFIG_ZTEST
case K_OBJ_ZTEST_UNIT_TEST: ret = "ztest_unit_test"; break;
#endif
#ifdef CONFIG_ZTEST
case K_OBJ_ZTEST_TEST_RULE: ret = "ztest_test_rule"; break;
#endif
#ifdef CONFIG_RTIO
case K_OBJ_RTIO: ret = "rtio"; break;
#endif
#ifdef CONFIG_RTIO
case K_OBJ_RTIO_IODEV: ret = "rtio_iodev"; break;
#endif
#ifdef CONFIG_SENSOR_ASYNC_API
case K_OBJ_SENSOR_DECODER_API: ret = "sensor_decoder_api"; break;
#endif
/* Driver subsystems */
case K_OBJ_DRIVER_FLASH: ret = "flash driver"; break;
case K_OBJ_DRIVER_GPIO: ret = "gpio driver"; break;
case K_OBJ_DRIVER_UART: ret = "uart driver"; break;
case K_OBJ_DRIVER_SHARED_IRQ: ret = "shared_irq driver"; break;
case K_OBJ_DRIVER_CRYPTO: ret = "crypto driver"; break;
case K_OBJ_DRIVER_ADC: ret = "adc driver"; break;
case K_OBJ_DRIVER_AUXDISPLAY: ret = "auxdisplay driver"; break;
case K_OBJ_DRIVER_BBRAM: ret = "bbram driver"; break;
case K_OBJ_DRIVER_BT_HCI: ret = "bt_hci driver"; break;
case K_OBJ_DRIVER_CAN: ret = "can driver"; break;
case K_OBJ_DRIVER_CELLULAR: ret = "cellular driver"; break;
case K_OBJ_DRIVER_CHARGER: ret = "charger driver"; break;
case K_OBJ_DRIVER_CLOCK_CONTROL: ret = "clock_control driver"; break;
case K_OBJ_DRIVER_COMPARATOR: ret = "comparator driver"; break;
case K_OBJ_DRIVER_COREDUMP: ret = "coredump driver"; break;
case K_OBJ_DRIVER_COUNTER: ret = "counter driver"; break;
case K_OBJ_DRIVER_DAC: ret = "dac driver"; break;
case K_OBJ_DRIVER_DAI: ret = "dai driver"; break;
case K_OBJ_DRIVER_DISPLAY: ret = "display driver"; break;
case K_OBJ_DRIVER_DMA: ret = "dma driver"; break;
case K_OBJ_DRIVER_EDAC: ret = "edac driver"; break;
case K_OBJ_DRIVER_EEPROM: ret = "eeprom driver"; break;
case K_OBJ_DRIVER_EMUL_BBRAM: ret = "emul_bbram driver"; break;
case K_OBJ_DRIVER_FUEL_GAUGE_EMUL: ret = "fuel_gauge_emul driver"; break;
case K_OBJ_DRIVER_EMUL_SENSOR: ret = "emul_sensor driver"; break;
case K_OBJ_DRIVER_ENTROPY: ret = "entropy driver"; break;
case K_OBJ_DRIVER_ESPI: ret = "espi driver"; break;
case K_OBJ_DRIVER_ESPI_SAF: ret = "espi_saf driver"; break;
case K_OBJ_DRIVER_FPGA: ret = "fpga driver"; break;
case K_OBJ_DRIVER_FUEL_GAUGE: ret = "fuel_gauge driver"; break;
case K_OBJ_DRIVER_GNSS: ret = "gnss driver"; break;
case K_OBJ_DRIVER_HAPTICS: ret = "haptics driver"; break;
case K_OBJ_DRIVER_HWSPINLOCK: ret = "hwspinlock driver"; break;
case K_OBJ_DRIVER_I2C: ret = "i2c driver"; break;
case K_OBJ_DRIVER_I2C_TARGET: ret = "i2c_target driver"; break;
case K_OBJ_DRIVER_I2S: ret = "i2s driver"; break;
case K_OBJ_DRIVER_I3C: ret = "i3c driver"; break;
case K_OBJ_DRIVER_IPM: ret = "ipm driver"; break;
case K_OBJ_DRIVER_KSCAN: ret = "kscan driver"; break;
case K_OBJ_DRIVER_LED: ret = "led driver"; break;
case K_OBJ_DRIVER_LED_STRIP: ret = "led_strip driver"; break;
case K_OBJ_DRIVER_LORA: ret = "lora driver"; break;
case K_OBJ_DRIVER_MBOX: ret = "mbox driver"; break;
case K_OBJ_DRIVER_MDIO: ret = "mdio driver"; break;
case K_OBJ_DRIVER_MIPI_DBI: ret = "mipi_dbi driver"; break;
case K_OBJ_DRIVER_MIPI_DSI: ret = "mipi_dsi driver"; break;
case K_OBJ_DRIVER_MSPI: ret = "mspi driver"; break;
case K_OBJ_DRIVER_PECI: ret = "peci driver"; break;
case K_OBJ_DRIVER_PS2: ret = "ps2 driver"; break;
case K_OBJ_DRIVER_PTP_CLOCK: ret = "ptp_clock driver"; break;
case K_OBJ_DRIVER_PWM: ret = "pwm driver"; break;
case K_OBJ_DRIVER_REGULATOR_PARENT: ret = "regulator_parent driver"; break;
case K_OBJ_DRIVER_REGULATOR: ret = "regulator driver"; break;
case K_OBJ_DRIVER_RESET: ret = "reset driver"; break;
case K_OBJ_DRIVER_RETAINED_MEM: ret = "retained_mem driver"; break;
case K_OBJ_DRIVER_RTC: ret = "rtc driver"; break;
case K_OBJ_DRIVER_SDHC: ret = "sdhc driver"; break;
case K_OBJ_DRIVER_SENSOR: ret = "sensor driver"; break;
case K_OBJ_DRIVER_SMBUS: ret = "smbus driver"; break;
case K_OBJ_DRIVER_SPI: ret = "spi driver"; break;
case K_OBJ_DRIVER_STEPPER: ret = "stepper driver"; break;
case K_OBJ_DRIVER_SYSCON: ret = "syscon driver"; break;
case K_OBJ_DRIVER_TEE: ret = "tee driver"; break;
case K_OBJ_DRIVER_VIDEO: ret = "video driver"; break;
case K_OBJ_DRIVER_W1: ret = "w1 driver"; break;
case K_OBJ_DRIVER_WDT: ret = "wdt driver"; break;
case K_OBJ_DRIVER_CAN_TRANSCEIVER: ret = "can_transceiver driver"; break;
case K_OBJ_DRIVER_NRF_CLOCK_CONTROL: ret = "nrf_clock_control driver"; break;
case K_OBJ_DRIVER_I3C_TARGET: ret = "i3c_target driver"; break;
case K_OBJ_DRIVER_ITS: ret = "its driver"; break;
case K_OBJ_DRIVER_VTD: ret = "vtd driver"; break;
case K_OBJ_DRIVER_TGPIO: ret = "tgpio driver"; break;
case K_OBJ_DRIVER_PCIE_CTRL: ret = "pcie_ctrl driver"; break;
case K_OBJ_DRIVER_PCIE_EP: ret = "pcie_ep driver"; break;
case K_OBJ_DRIVER_SVC: ret = "svc driver"; break;
case K_OBJ_DRIVER_BC12_EMUL: ret = "bc12_emul driver"; break;
case K_OBJ_DRIVER_BC12: ret = "bc12 driver"; break;
case K_OBJ_DRIVER_USBC_PPC: ret = "usbc_ppc driver"; break;
case K_OBJ_DRIVER_TCPC: ret = "tcpc driver"; break;
case K_OBJ_DRIVER_USBC_VBUS: ret = "usbc_vbus driver"; break;
case K_OBJ_DRIVER_IVSHMEM: ret = "ivshmem driver"; break;
case K_OBJ_DRIVER_ETHPHY: ret = "ethphy driver"; break;
