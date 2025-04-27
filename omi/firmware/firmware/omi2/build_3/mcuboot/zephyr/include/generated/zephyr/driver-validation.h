#ifndef DRIVER_VALIDATION_GEN_H
#define DRIVER_VALIDATION_GEN_H
#define K_SYSCALL_DRIVER_GEN(ptr, op, driver_lower_case, driver_upper_case) \
		(K_SYSCALL_OBJ(ptr, K_OBJ_DRIVER_##driver_upper_case) || \
		 K_SYSCALL_DRIVER_OP(ptr, driver_lower_case##_driver_api, op))
                
#define K_SYSCALL_DRIVER_FLASH(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, flash, FLASH)

#define K_SYSCALL_DRIVER_GPIO(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, gpio, GPIO)

#define K_SYSCALL_DRIVER_UART(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, uart, UART)

#define K_SYSCALL_DRIVER_SHARED_IRQ(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, shared_irq, SHARED_IRQ)

#define K_SYSCALL_DRIVER_CRYPTO(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, crypto, CRYPTO)

#define K_SYSCALL_DRIVER_ADC(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, adc, ADC)

#define K_SYSCALL_DRIVER_AUXDISPLAY(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, auxdisplay, AUXDISPLAY)

#define K_SYSCALL_DRIVER_BBRAM(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, bbram, BBRAM)

#define K_SYSCALL_DRIVER_BT_HCI(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, bt_hci, BT_HCI)

#define K_SYSCALL_DRIVER_CAN(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, can, CAN)

#define K_SYSCALL_DRIVER_CELLULAR(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, cellular, CELLULAR)

#define K_SYSCALL_DRIVER_CHARGER(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, charger, CHARGER)

#define K_SYSCALL_DRIVER_CLOCK_CONTROL(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, clock_control, CLOCK_CONTROL)

#define K_SYSCALL_DRIVER_COMPARATOR(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, comparator, COMPARATOR)

#define K_SYSCALL_DRIVER_COREDUMP(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, coredump, COREDUMP)

#define K_SYSCALL_DRIVER_COUNTER(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, counter, COUNTER)

#define K_SYSCALL_DRIVER_DAC(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, dac, DAC)

#define K_SYSCALL_DRIVER_DAI(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, dai, DAI)

#define K_SYSCALL_DRIVER_DISPLAY(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, display, DISPLAY)

#define K_SYSCALL_DRIVER_DMA(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, dma, DMA)

#define K_SYSCALL_DRIVER_EDAC(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, edac, EDAC)

#define K_SYSCALL_DRIVER_EEPROM(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, eeprom, EEPROM)

#define K_SYSCALL_DRIVER_EMUL_BBRAM(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, emul_bbram, EMUL_BBRAM)

#define K_SYSCALL_DRIVER_FUEL_GAUGE_EMUL(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, fuel_gauge_emul, FUEL_GAUGE_EMUL)

#define K_SYSCALL_DRIVER_EMUL_SENSOR(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, emul_sensor, EMUL_SENSOR)

#define K_SYSCALL_DRIVER_ENTROPY(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, entropy, ENTROPY)

#define K_SYSCALL_DRIVER_ESPI(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, espi, ESPI)

#define K_SYSCALL_DRIVER_ESPI_SAF(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, espi_saf, ESPI_SAF)

#define K_SYSCALL_DRIVER_FPGA(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, fpga, FPGA)

#define K_SYSCALL_DRIVER_FUEL_GAUGE(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, fuel_gauge, FUEL_GAUGE)

#define K_SYSCALL_DRIVER_GNSS(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, gnss, GNSS)

#define K_SYSCALL_DRIVER_HAPTICS(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, haptics, HAPTICS)

#define K_SYSCALL_DRIVER_HWSPINLOCK(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, hwspinlock, HWSPINLOCK)

#define K_SYSCALL_DRIVER_I2C(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, i2c, I2C)

#define K_SYSCALL_DRIVER_I2C_TARGET(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, i2c_target, I2C_TARGET)

#define K_SYSCALL_DRIVER_I2S(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, i2s, I2S)

#define K_SYSCALL_DRIVER_I3C(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, i3c, I3C)

#define K_SYSCALL_DRIVER_IPM(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, ipm, IPM)

#define K_SYSCALL_DRIVER_KSCAN(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, kscan, KSCAN)

#define K_SYSCALL_DRIVER_LED(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, led, LED)

#define K_SYSCALL_DRIVER_LED_STRIP(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, led_strip, LED_STRIP)

#define K_SYSCALL_DRIVER_LORA(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, lora, LORA)

#define K_SYSCALL_DRIVER_MBOX(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, mbox, MBOX)

#define K_SYSCALL_DRIVER_MDIO(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, mdio, MDIO)

#define K_SYSCALL_DRIVER_MIPI_DBI(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, mipi_dbi, MIPI_DBI)

#define K_SYSCALL_DRIVER_MIPI_DSI(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, mipi_dsi, MIPI_DSI)

#define K_SYSCALL_DRIVER_MSPI(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, mspi, MSPI)

#define K_SYSCALL_DRIVER_PECI(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, peci, PECI)

#define K_SYSCALL_DRIVER_PS2(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, ps2, PS2)

#define K_SYSCALL_DRIVER_PTP_CLOCK(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, ptp_clock, PTP_CLOCK)

#define K_SYSCALL_DRIVER_PWM(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, pwm, PWM)

#define K_SYSCALL_DRIVER_REGULATOR_PARENT(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, regulator_parent, REGULATOR_PARENT)

#define K_SYSCALL_DRIVER_REGULATOR(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, regulator, REGULATOR)

#define K_SYSCALL_DRIVER_RESET(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, reset, RESET)

#define K_SYSCALL_DRIVER_RETAINED_MEM(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, retained_mem, RETAINED_MEM)

#define K_SYSCALL_DRIVER_RTC(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, rtc, RTC)

#define K_SYSCALL_DRIVER_SDHC(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, sdhc, SDHC)

#define K_SYSCALL_DRIVER_SENSOR(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, sensor, SENSOR)

#define K_SYSCALL_DRIVER_SMBUS(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, smbus, SMBUS)

#define K_SYSCALL_DRIVER_SPI(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, spi, SPI)

#define K_SYSCALL_DRIVER_STEPPER(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, stepper, STEPPER)

#define K_SYSCALL_DRIVER_SYSCON(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, syscon, SYSCON)

#define K_SYSCALL_DRIVER_TEE(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, tee, TEE)

#define K_SYSCALL_DRIVER_VIDEO(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, video, VIDEO)

#define K_SYSCALL_DRIVER_W1(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, w1, W1)

#define K_SYSCALL_DRIVER_WDT(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, wdt, WDT)

#define K_SYSCALL_DRIVER_CAN_TRANSCEIVER(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, can_transceiver, CAN_TRANSCEIVER)

#define K_SYSCALL_DRIVER_NRF_CLOCK_CONTROL(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, nrf_clock_control, NRF_CLOCK_CONTROL)

#define K_SYSCALL_DRIVER_I3C_TARGET(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, i3c_target, I3C_TARGET)

#define K_SYSCALL_DRIVER_ITS(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, its, ITS)

#define K_SYSCALL_DRIVER_VTD(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, vtd, VTD)

#define K_SYSCALL_DRIVER_TGPIO(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, tgpio, TGPIO)

#define K_SYSCALL_DRIVER_PCIE_CTRL(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, pcie_ctrl, PCIE_CTRL)

#define K_SYSCALL_DRIVER_PCIE_EP(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, pcie_ep, PCIE_EP)

#define K_SYSCALL_DRIVER_SVC(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, svc, SVC)

#define K_SYSCALL_DRIVER_BC12_EMUL(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, bc12_emul, BC12_EMUL)

#define K_SYSCALL_DRIVER_BC12(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, bc12, BC12)

#define K_SYSCALL_DRIVER_USBC_PPC(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, usbc_ppc, USBC_PPC)

#define K_SYSCALL_DRIVER_TCPC(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, tcpc, TCPC)

#define K_SYSCALL_DRIVER_USBC_VBUS(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, usbc_vbus, USBC_VBUS)

#define K_SYSCALL_DRIVER_IVSHMEM(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, ivshmem, IVSHMEM)

#define K_SYSCALL_DRIVER_ETHPHY(ptr, op) K_SYSCALL_DRIVER_GEN(ptr, op, ethphy, ETHPHY)
#endif /* DRIVER_VALIDATION_GEN_H */
