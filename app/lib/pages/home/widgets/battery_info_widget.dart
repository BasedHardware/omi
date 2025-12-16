import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';

class BatteryInfoWidget extends StatelessWidget {
  const BatteryInfoWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Selector<HomeProvider, bool>(
      selector: (context, state) => state.selectedIndex == 0,
      builder: (context, isMemoriesPage, child) {
        return Consumer<DeviceProvider>(
          builder: (context, deviceProvider, child) {
            if (deviceProvider.connectedDevice != null) {
              return GestureDetector(
                onTap: deviceProvider.connectedDevice == null
                    ? null
                    : () {
                        routeToPage(
                          context,
                          const ConnectedDevice(),
                        );
                        MixpanelManager().batteryIndicatorClicked();
                      },
                child: Container(
                    height: 36,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1F1F25),
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: deviceProvider.batteryLevel > 75
                                ? const Color.fromARGB(255, 0, 255, 8)
                                : deviceProvider.batteryLevel > 20
                                    ? Colors.yellow.shade700
                                    : deviceProvider.batteryLevel > 0
                                        ? Colors.red
                                        : Colors.grey,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 6.0),
                        // Add device icon
                        SizedBox(
                          width: 16,
                          height: 16,
                          child: Image.asset(
                            DeviceUtils.getDeviceImagePath(
                              deviceType: deviceProvider.connectedDevice?.type,
                              modelNumber: deviceProvider.connectedDevice?.modelNumber,
                              deviceName: deviceProvider.connectedDevice?.name,
                            ),
                            fit: BoxFit.contain,
                          ),
                        ),
                        const SizedBox(width: 6.0),
                        Text(
                          deviceProvider.batteryLevel > 0 ? '${deviceProvider.batteryLevel.toString()}%' : "",
                          style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                        ),
                      ],
                    )),
              );
            } else if (SharedPreferencesUtil().btDevice.id.isNotEmpty) {
              // Device is paired but disconnected
              return GestureDetector(
                onTap: () async {
                  await routeToPage(context, const ConnectedDevice());
                },
                child: Container(
                  height: 36,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1F25),
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Device icon with slash line
                      SizedBox(
                        width: 16,
                        height: 16,
                        child: Stack(
                          children: [
                            Image.asset(
                              DeviceUtils.getDeviceImageFromBtDevice(SharedPreferencesUtil().btDevice),
                              fit: BoxFit.contain,
                            ),
                            // Slash line across the image
                            Positioned.fill(
                              child: CustomPaint(
                                painter: SlashLinePainter(),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 6.0),
                      Text(
                        "Disconnected",
                        style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white70, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              );
            } else {
              return GestureDetector(
                onTap: () async {
                  if (SharedPreferencesUtil().btDevice.id.isEmpty) {
                    routeToPage(context, const ConnectDevicePage());
                    MixpanelManager().connectFriendClicked();
                  } else {
                    await routeToPage(context, const ConnectedDevice());
                  }
                },
                child: Container(
                  height: 36,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1F25),
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Image.asset(
                        Assets.images.logoTransparent.path,
                        width: 16,
                        height: 16,
                      ),
                      isMemoriesPage ? const SizedBox(width: 6) : const SizedBox.shrink(),
                      deviceProvider.isConnecting && isMemoriesPage
                          ? Text(
                              "Searching",
                              style:
                                  Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white, fontSize: 12),
                            )
                          : isMemoriesPage
                              ? Text(
                                  "Connect Device",
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodyMedium!
                                      .copyWith(color: Colors.white, fontSize: 12),
                                )
                              : const SizedBox.shrink(),
                    ],
                  ),
                ),
              );
            }
          },
        );
      },
    );
  }
}

class SlashLinePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.red
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    // Position the cross at the bottom right
    final crossSize = size.width * 0.2; // Size of the cross
    final centerX = size.width - crossSize / 2 - 2; // Bottom right positioning
    final centerY = size.height - crossSize / 2 - 2;
    final halfCrossSize = crossSize / 2;

    // Draw the X (cross) - two diagonal lines
    canvas.drawLine(
      Offset(centerX - halfCrossSize, centerY - halfCrossSize),
      Offset(centerX + halfCrossSize, centerY + halfCrossSize),
      paint,
    );

    canvas.drawLine(
      Offset(centerX + halfCrossSize, centerY - halfCrossSize),
      Offset(centerX - halfCrossSize, centerY + halfCrossSize),
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
