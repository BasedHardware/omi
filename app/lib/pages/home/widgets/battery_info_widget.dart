import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/capture/connect.dart';
import 'package:friend_private/pages/home/device.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
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
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: Colors.transparent,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        color: Colors.grey,
                        width: 1,
                      ),
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
                        isMemoriesPage
                            ? Text(
                                deviceProvider.connectedDevice?.name ?? SharedPreferencesUtil().deviceName,
                                style: const TextStyle(color: Colors.white, fontSize: 14),
                              )
                            : const SizedBox.shrink(),
                        isMemoriesPage ? const SizedBox(width: 8) : const SizedBox.shrink(),
                        Text(
                          deviceProvider.batteryLevel > 0 ? '${deviceProvider.batteryLevel.toString()}%' : "",
                          style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                        ),
                      ],
                    )),
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
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  // backgroundColor: Colors.transparent,
                  decoration: BoxDecoration(
                    color: Colors.transparent,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: Colors.grey, width: 1),
                  ),
                  child: Row(
                    children: [
                      Image.asset(
                        'assets/images/logo_transparent.png',
                        width: MediaQuery.sizeOf(context).width * 0.05,
                        height: MediaQuery.sizeOf(context).width * 0.05,
                      ),
                      isMemoriesPage ? const SizedBox(width: 8) : const SizedBox.shrink(),
                      deviceProvider.isConnecting && isMemoriesPage
                          ? Text(
                              "Connecting",
                              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                            )
                          : isMemoriesPage
                              ? Text(
                                  "No device found",
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
