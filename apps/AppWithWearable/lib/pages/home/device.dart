import 'package:flutter/material.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class ConnectedDevice extends StatefulWidget {
  // TODO: retrieve this from here instead of params
  final BTDeviceStruct device;
  final int batteryLevel;

  const ConnectedDevice({super.key, required this.device, required this.batteryLevel});

  @override
  State<ConnectedDevice> createState() => _ConnectedDeviceState();
}

class _ConnectedDeviceState extends State<ConnectedDevice> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Connected Device'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: Column(
        children: [
          const SizedBox(height: 32),
          const DeviceAnimationWidget(),
          Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.start,
            children: [
              Text(
                'DEVICE-${widget.device.id.split('-').last.substring(0, 6)}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16.0,
                  fontWeight: FontWeight.w500,
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: 12),
              Container(
                  decoration: BoxDecoration(
                    color: Colors.transparent,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 10,
                        height: 10,
                        decoration: BoxDecoration(
                          color: widget.batteryLevel > 75
                              ? const Color.fromARGB(255, 0, 255, 8)
                              : widget.batteryLevel > 20
                                  ? Colors.yellow.shade700
                                  : Colors.red,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8.0),
                      Text(
                        '${widget.batteryLevel.toString()}% Battery',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ))
            ],
          ),
          const SizedBox(height: 32),
          Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
              decoration: BoxDecoration(
                border: const GradientBoxBorder(
                  gradient: LinearGradient(colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236)
                  ]),
                  width: 2,
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: TextButton(
                  onPressed: () {
                    bleDisconnectDevice(widget.device);
                    Navigator.of(context).pop();
                    SharedPreferencesUtil().deviceId = '';
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('Your Friend is disconnected   😔'),
                    ));
                    MixpanelManager().disconnectFriendClicked();
                  },
                  child: const Text(
                    'Disconnect',
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  )))
        ],
      ),
    );
  }
}
