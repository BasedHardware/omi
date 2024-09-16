import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

import 'device_settings.dart';

class ConnectedDevice extends StatefulWidget {
  // TODO: retrieve this from here instead of params
  final BTDeviceStruct? device;
  final int batteryLevel;

  const ConnectedDevice({super.key, required this.device, required this.batteryLevel});

  @override
  State<ConnectedDevice> createState() => _ConnectedDeviceState();
}

class _ConnectedDeviceState extends State<ConnectedDevice> {
  // TODO: thinh, use connection directly
  Future _bleDisconnectDevice(BTDeviceStruct btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

  Future<DeviceInfo> _getDeviceInfo(String? deviceId) async {
    if (deviceId == null) {
      return DeviceInfo.getDeviceInfo(null, null);
    }

    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return DeviceInfo.getDeviceInfo(null, null);
    }
    return await DeviceInfo.getDeviceInfo(connection.device, connection);
  }

  @override
  Widget build(BuildContext context) {
    var deviceName = widget.device?.name ?? SharedPreferencesUtil().deviceName;
    var deviceConnected = widget.device != null;

    return FutureBuilder<DeviceInfo>(
      future: _getDeviceInfo(widget.device?.id),
      builder: (BuildContext context, AsyncSnapshot<DeviceInfo> snapshot) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            title: Text(deviceConnected ? 'Connected Device' : 'Paired Device'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            actions: [
              IconButton(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => DeviceSettings(
                        device: widget.device,
                        deviceInfo: snapshot.data,
                        isDeviceConnected: deviceConnected,
                      ),
                    ),
                  );
                },
                icon: const Icon(Icons.settings),
              )
            ],
          ),
          body: Column(
            children: [
              const SizedBox(height: 32),
              const DeviceAnimationWidget(),
              Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [
                  Text(
                    '$deviceName (${widget.device?.getShortId() ?? SharedPreferencesUtil().btDeviceStruct.getShortId()})',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16.0,
                      fontWeight: FontWeight.w500,
                      height: 1.5,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 12),
                  if (snapshot.hasData)
                    Column(
                      children: [
                        Text(
                          '${snapshot.data?.modelNumber}, firmware ${snapshot.data?.firmwareRevision}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10.0,
                            fontWeight: FontWeight.w500,
                            height: 1,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'by ${snapshot.data?.manufacturerName}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10.0,
                            fontWeight: FontWeight.w500,
                            height: 1,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                      ],
                    ),
                  widget.device != null
                      ? Container(
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
                      : const SizedBox.shrink()
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
                  onPressed: () async {
                    await SharedPreferencesUtil().btDeviceStructSet(BTDeviceStruct(id: '', name: ''));
                    SharedPreferencesUtil().deviceName = '';
                    if (widget.device != null) {
                      await _bleDisconnectDevice(widget.device!);
                    }
                    context.read<DeviceProvider>().setIsConnected(false);
                    context.read<DeviceProvider>().setConnectedDevice(null);
                    context.read<DeviceProvider>().updateConnectingStatus(false);
                    Navigator.of(context).pop();
                    MixpanelManager().disconnectFriendClicked();
                  },
                  child: Text(
                    widget.device == null ? "Unpair" : "Disconnect",
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
