import 'package:flutter/material.dart';
import 'package:friend_private/pages/home/device_settings.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/onboarding/find_device/page.dart';
import 'package:friend_private/widgets/device_widget.dart';

class ConnectDevicePage extends StatefulWidget {
  const ConnectDevicePage({super.key});

  @override
  State<ConnectDevicePage> createState() => _ConnectDevicePageState();
}

class _ConnectDevicePageState extends State<ConnectDevicePage> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
        appBar: AppBar(
          title: const Text('Connect Your Friend'),
          backgroundColor: Theme.of(context).colorScheme.primary,
          actions: [
            IconButton(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => const DeviceSettings(
                      isDeviceConnected: false,
                    ),
                  ),
                );
              },
              icon: const Icon(Icons.settings),
            )
          ],
        ),
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: ListView(
          children: [
            const DeviceAnimationWidget(),
            FindDevicesPage(
              goNext: () {
                debugPrint('onConnected');
                Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (c) => const HomePageWrapper()));
              },
              includeSkip: false,
            )
          ],
        ));
  }
}
