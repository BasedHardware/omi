import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// Desktop battery info widget with premium minimal design
class DesktopBatteryInfoWidget extends StatelessWidget {
  const DesktopBatteryInfoWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Consumer<DeviceProvider>(
      builder: (context, provider, child) {
        BtDevice? device = provider.connectedDevice;

        if (device == null || !provider.isConnected) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: ResponsiveHelper.backgroundQuaternary,
                width: 1,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.bluetooth_disabled,
                  color: ResponsiveHelper.textTertiary,
                  size: responsive.iconSize(baseSize: 16),
                ),
                const SizedBox(width: 6),
                Text(
                  'Disconnected',
                  style: TextStyle(
                    fontSize: responsive.responsiveFontSize(baseFontSize: 12),
                    fontWeight: FontWeight.w500,
                    color: ResponsiveHelper.textTertiary,
                  ),
                ),
              ],
            ),
          );
        }

        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: ResponsiveHelper.backgroundQuaternary,
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Battery icon
              Container(
                width: 16,
                height: 10,
                decoration: BoxDecoration(
                  border: Border.all(
                    color: _getBatteryColor(provider.batteryLevel),
                    width: 1,
                  ),
                  borderRadius: BorderRadius.circular(2),
                ),
                child: Stack(
                  children: [
                    // Battery fill
                    FractionallySizedBox(
                      widthFactor: provider.batteryLevel / 100,
                      child: Container(
                        decoration: BoxDecoration(
                          color: _getBatteryColor(provider.batteryLevel),
                          borderRadius: BorderRadius.circular(1),
                        ),
                      ),
                    ),
                    // Battery terminal
                    Positioned(
                      right: -2,
                      top: 2,
                      child: Container(
                        width: 2,
                        height: 6,
                        decoration: BoxDecoration(
                          color: _getBatteryColor(provider.batteryLevel),
                          borderRadius: const BorderRadius.only(
                            topRight: Radius.circular(1),
                            bottomRight: Radius.circular(1),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(width: 8),

              // Battery percentage
              Text(
                '${provider.batteryLevel}%',
                style: TextStyle(
                  fontSize: responsive.responsiveFontSize(baseFontSize: 12),
                  fontWeight: FontWeight.w600,
                  color: _getBatteryColor(provider.batteryLevel),
                ),
              ),

              const SizedBox(width: 8),

              // Connection indicator
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: ResponsiveHelper.successColor,
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Color _getBatteryColor(int batteryLevel) {
    if (batteryLevel > 50) {
      return ResponsiveHelper.successColor;
    } else if (batteryLevel > 20) {
      return ResponsiveHelper.warningColor;
    } else {
      return ResponsiveHelper.errorColor;
    }
  }
}
