import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';

class BatteryInfoWidget extends StatelessWidget {
  const BatteryInfoWidget({super.key});

  String _getDeviceImagePath(String? deviceName) {
    if (deviceName != null && deviceName.contains('Glass')) {
      return Assets.images.omiGlass.path;
    }

    if (deviceName != null && deviceName.contains('Omi DevKit')) {
      return Assets.images.omiDevkitWithoutRope.path;
    }

    return Assets.images.omiWithoutRope.path;
  }

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
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1F1F25),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Container(
                          width: 10,
                          height: 10,
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
                        const SizedBox(width: 8.0),
                        // Add device icon
                        Container(
                          width: 20,
                          height: 20,
                          child: Image.asset(
                            _getDeviceImagePath(deviceProvider.connectedDevice?.name),
                            fit: BoxFit.contain,
                          ),
                        ),
                        const SizedBox(width: 8.0),
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
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1F25),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Device icon with slash line
                      Container(
                        width: 20,
                        height: 20,
                        child: Stack(
                          children: [
                            Image.asset(
                              _getDeviceImagePath(SharedPreferencesUtil().btDevice.name),
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
                      const SizedBox(width: 8.0),
                      Text(
                        "Disconnected",
                        style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white70),
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
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1F25),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Row(
                    children: [
                      Image.asset(
                        Assets.images.logoTransparent.path,
                        width: MediaQuery.sizeOf(context).width * 0.05,
                        height: MediaQuery.sizeOf(context).width * 0.05,
                      ),
                      isMemoriesPage ? const SizedBox(width: 8) : const SizedBox.shrink(),
                      deviceProvider.isConnecting && isMemoriesPage
                          ? Text(
                              "Searching",
                              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                            )
                          : isMemoriesPage
                              ? Text(
                                  "Connect Device",
                                  style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
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
