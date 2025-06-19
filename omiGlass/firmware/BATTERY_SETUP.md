# OpenGlass Battery Indicator Setup

This document explains the battery indicator implementation for OpenGlass devices.

## What's New

The OpenGlass firmware now includes a battery service that provides battery level information to the companion app, just like the regular Omi device.

## Hardware Requirements

The battery indicator requires a proper hardware connection to read the battery voltage:

1. **ADC Pin**: Currently configured to use `A0` (can be changed in firmware)
2. **Voltage Divider**: Required to bring 4.2V battery down to ADC-safe levels

## Hardware Configuration

### Seeed XIAO ESP32S3 Sense

The current configuration:
- ADC Pin: `A0`
- Battery: 3.7V LiPo (3.7V - 4.2V range)
- Voltage divider: R1=169kΩ, R2=110kΩ (2.536:1 ratio)
- ADC Reference: 3.3V

### Voltage Divider Circuit

Your current setup:
```
Battery + ----[R1: 169kΩ]----+----[R2: 110kΩ]---- Battery -
                             |
                           ADC Pin A0
```

**Calculations:**
- Total resistance: 169kΩ + 110kΩ = 279kΩ
- Voltage ratio: 279kΩ / 110kΩ = 2.536
- Max ADC voltage: 4.2V / 2.536 = 1.66V (well within 3.3V ADC limit)
- Battery range at ADC: 1.46V (3.7V) to 1.66V (4.2V)

### Configuration Details

The firmware is configured for your specific resistor values:

```cpp
const int BATTERY_ADC_PIN = A0; // ADC pin
const float BATTERY_MAX_VOLTAGE = 4.2; // Maximum battery voltage
const float BATTERY_MIN_VOLTAGE = 3.7; // Minimum safe battery voltage
voltage *= 2.536; // Voltage divider ratio for R1=169kΩ, R2=110kΩ
```

## Features

- **Standard BLE Battery Service**: Uses UUID `0x180F` for compatibility
- **Real-time Updates**: Battery level updates every 60 seconds
- **Automatic Notifications**: Sends battery level to connected devices
- **Percentage Calculation**: Converts voltage to 0-100% range

## App Integration

The companion app will automatically detect and display the battery indicator once the device is connected. No additional configuration is needed on the app side.

## Testing

To test the battery indicator:

1. Flash the updated firmware to your OpenGlass device
2. Connect to the device using the companion app
3. Check the home screen for the battery indicator
4. Battery level should update periodically

## Troubleshooting

- **Battery shows 0% or 100% constantly**: Check voltage divider resistor values and connections
- **No battery indicator**: Verify ADC pin connection and firmware flash
- **Incorrect readings**: Verify R1=2.2MΩ and R2=560kΩ resistor values
- **Battery percentage seems off**: Check ADC pin A0 connection to voltage divider midpoint
- **Need different range**: Modify resistor values and update voltage multiplier in firmware

## Technical Details

- Battery level is read via ADC every 60 seconds
- Voltage is converted to percentage using linear interpolation
- BLE notifications are sent when battery level changes
- Compatible with existing Omi app battery display logic 