import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';

class DeviceSettings extends StatefulWidget {
  const DeviceSettings({super.key});

  @override
  State<DeviceSettings> createState() => _DeviceSettingsState();
}

class _DeviceSettingsState extends State<DeviceSettings> {
  double _dimRatio = 100.0;
  bool _isDimRatioLoaded = false;
  bool? _hasDimmingFeature;

  double _micGain = 5.0;
  bool _isMicGainLoaded = false;
  bool? _hasMicGainFeature;

  Timer? _debounce;
  Timer? _micGainDebounce;

  // TODO: thinh, use connection directly
  Future _bleDisconnectDevice(BtDevice btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await context.read<DeviceProvider>().getDeviceInfo();
      _loadInitialDimRatio();
    });
    super.initState();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _micGainDebounce?.cancel();
    super.dispose();
  }

  void _loadInitialDimRatio() async {
    final deviceProvider = context.read<DeviceProvider>();
    if (deviceProvider.pairedDevice != null) {
      var connection = await ServiceManager.instance().device.ensureConnection(deviceProvider.pairedDevice!.id);
      if (connection != null) {
        var features = await connection.getFeatures();
        final hasDimming = (features & OmiFeatures.ledDimming) != 0;
        final hasMicGain = (features & OmiFeatures.micGain) != 0;

        if (!mounted) return;
        setState(() {
          _hasDimmingFeature = hasDimming;
          _hasMicGainFeature = hasMicGain;
        });

        if (!hasDimming) {
          setState(() {
            _isDimRatioLoaded = true;
          });
        } else {
          var ratio = await connection.getLedDimRatio();
          if (ratio != null && mounted) {
            setState(() {
              _dimRatio = ratio.toDouble();
              _isDimRatioLoaded = true;
            });
          } else if (mounted) {
            setState(() {
              _isDimRatioLoaded = true; // Loaded, but no value, use default
            });
          }
        }

        if (!hasMicGain) {
          setState(() {
            _isMicGainLoaded = true;
          });
        } else {
          var gain = await connection.getMicGain();
          if (gain != null && mounted) {
            setState(() {
              _micGain = gain.toDouble();
              _isMicGainLoaded = true;
            });
          } else if (mounted) {
            setState(() {
              _isMicGainLoaded = true; // Loaded, but no value, use default
            });
          }
        }
      }
    }
  }

  void _updateDimRatio(double value) async {
    final deviceProvider = context.read<DeviceProvider>();
    if (deviceProvider.pairedDevice != null) {
      var connection = await ServiceManager.instance().device.ensureConnection(deviceProvider.pairedDevice!.id);
      await connection?.setLedDimRatio(value.toInt());
    }
  }

  void _updateMicGain(double value) async {
    final deviceProvider = context.read<DeviceProvider>();
    if (deviceProvider.pairedDevice != null) {
      var connection = await ServiceManager.instance().device.ensureConnection(deviceProvider.pairedDevice!.id);
      await connection?.setMicGain(value.toInt());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          title: const Text('Device Settings'),
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
        body: Padding(
          padding: const EdgeInsets.all(4.0),
          child: ListView(
            children: [
              Stack(
                children: [
                  Column(
                    children: deviceSettingsWidgets(provider.pairedDevice, context),
                  ),
                  if (!provider.isConnected)
                    ClipRRect(
                      child: BackdropFilter(
                        filter: ImageFilter.blur(
                          sigmaX: 3.0,
                          sigmaY: 3.0,
                        ),
                        child: Container(
                          height: 410,
                          width: double.infinity,
                          margin: const EdgeInsets.only(top: 10),
                          decoration: BoxDecoration(
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.1),
                                spreadRadius: 5,
                                blurRadius: 7,
                                offset: const Offset(0, 3),
                              ),
                            ],
                          ),
                          child: const Center(
                            child: Text(
                              'Connect your device to\naccess these settings',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                height: 1.3,
                                fontWeight: FontWeight.w500,
                              ),
                              textAlign: TextAlign.center,
                            ),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
              if (provider.isConnected)
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                      child: Text(
                        'Customization',
                        style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                      ),
                    ),
                    _buildDimmingControl(),
                    _buildMicGainControl(),
                  ],
                ),
              GestureDetector(
                onTap: () async {
                  await IntercomManager().displayChargingArticle(provider.pairedDevice?.name ?? 'DevKit1');
                },
                child: const ListTile(
                  title: Text('Issues charging the device?'),
                  subtitle: Text('Tap to see the guide'),
                ),
              ),
            ],
          ),
        ),
        bottomNavigationBar: provider.isConnected
            ? Padding(
                padding: const EdgeInsets.only(bottom: 70, left: 30, right: 30),
                child: Container(
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
                      await SharedPreferencesUtil()
                          .btDeviceSet(BtDevice(id: '', name: '', type: DeviceType.omi, rssi: 0));
                      SharedPreferencesUtil().deviceName = '';
                      if (provider.connectedDevice != null) {
                        await _bleDisconnectDevice(provider.connectedDevice!);
                      }
                      provider.setIsConnected(false);
                      provider.setConnectedDevice(null);
                      provider.updateConnectingStatus(false);
                      Navigator.of(context).pop();
                      Navigator.of(context).pop();
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content:
                            Text('Your Omi is ${provider.connectedDevice == null ? "unpaired" : "disconnected"}  😔'),
                      ));
                      MixpanelManager().disconnectFriendClicked();
                    },
                    child: Text(
                      provider.connectedDevice == null ? "Unpair" : "Disconnect",
                      style: const TextStyle(color: Colors.white, fontSize: 16),
                    ),
                  ),
                ),
              )
            : const SizedBox(),
      );
    });
  }

  Widget _buildDimmingControl() {
    if (!_isDimRatioLoaded) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_hasDimmingFeature == false) {
      return const ListTile(
        title: Text('Dimming'),
        subtitle: Text('This feature is not available on your device.'),
      );
    }

    return ListTile(
      title: const Text('Dimming'),
      subtitle: Slider(
        value: _dimRatio,
        min: 0,
        max: 100,
        divisions: 100,
        activeColor: Colors.white,
        inactiveColor: Colors.grey,
        label: '${_dimRatio.round()}%',
        onChanged: (double value) {
          if (!(_debounce?.isActive ?? false)) {
            _debounce = Timer(const Duration(milliseconds: 300), () {
              _updateDimRatio(value);
            });
          }
          setState(() {
            _dimRatio = value;
          });
        },
        onChangeEnd: (double value) {
          _debounce?.cancel();
          _updateDimRatio(value);
        },
      ),
    );
  }

  Widget _buildMicGainControl() {
    if (!_isMicGainLoaded) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_hasMicGainFeature == false) {
      return const ListTile(
        title: Text('Mic Gain'),
        subtitle: Text('This feature is not available on your device.'),
      );
    }

    // Map gain level to label and description
    String getGainLabel(int level) {
      const labels = [
        'Mute', // Level 0
        '-20dB', // Level 1
        '-10dB', // Level 2
        '+0dB', // Level 3
        '+6dB', // Level 4
        '+10dB', // Level 5
        '+20dB', // Level 6 (default)
        '+30dB', // Level 7
        '+40dB', // Level 8
      ];
      return level >= 0 && level < labels.length ? labels[level] : '';
    }

    String getGainDescription(int level) {
      const descriptions = [
        'Microphone is muted', // Level 0
        'Very quiet - for loud environments', // Level 1
        'Quiet - for moderate noise', // Level 2
        'Neutral - balanced recording', // Level 3
        'Slightly boosted - normal use', // Level 4
        'Boosted - for quiet environments', // Level 5
        'High - for distant or soft voices', // Level 6 (default)
        'Very high - for very quiet sources', // Level 7
        'Maximum - use with caution', // Level 8
      ];
      return level >= 0 && level < descriptions.length ? descriptions[level] : '';
    }

    final currentLevel = _micGain.round();

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey.shade800, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Mic Gain',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: Colors.white,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      currentLevel == 0 ? Icons.mic_off : Icons.mic,
                      size: 16,
                      color: Colors.grey.shade400,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      getGainLabel(currentLevel),
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: Colors.grey.shade300,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Current level description
          Text(
            getGainDescription(currentLevel),
            style: TextStyle(
              fontSize: 12,
              color: Colors.grey.shade400,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 20),

          // Slider with level markers
          Stack(
            children: [
              // Level markers
              Positioned.fill(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: List.generate(9, (index) {
                    final isActive = index == currentLevel;
                    return Container(
                      width: 2,
                      height: 8,
                      decoration: BoxDecoration(
                        color: isActive ? Colors.white : Colors.grey.shade700,
                        borderRadius: BorderRadius.circular(1),
                      ),
                    );
                  }),
                ),
              ),
              // Slider
              SliderTheme(
                data: SliderThemeData(
                  activeTrackColor: Colors.white,
                  inactiveTrackColor: Colors.grey.shade800,
                  thumbColor: Colors.white,
                  overlayColor: Colors.white.withOpacity(0.1),
                  thumbShape: const RoundSliderThumbShape(
                    enabledThumbRadius: 10,
                    elevation: 2,
                  ),
                  overlayShape: const RoundSliderOverlayShape(overlayRadius: 20),
                  trackHeight: 4,
                ),
                child: Slider(
                  value: _micGain,
                  min: 0,
                  max: 8,
                  divisions: 8,
                  onChanged: (double value) {
                    if (!(_micGainDebounce?.isActive ?? false)) {
                      _micGainDebounce = Timer(const Duration(milliseconds: 300), () {
                        _updateMicGain(value);
                      });
                    }
                    setState(() {
                      _micGain = value;
                    });
                  },
                  onChangeEnd: (double value) {
                    _micGainDebounce?.cancel();
                    _updateMicGain(value);
                  },
                ),
              ),
            ],
          ),

          // Level labels
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Mute',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.grey.shade500,
                  ),
                ),
                Text(
                  '+6dB',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.grey.shade500,
                  ),
                ),
                Text(
                  'Max',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.grey.shade500,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // Quick presets
          Row(
            children: [
              Expanded(
                child: _buildPresetButton('Quiet', 2, currentLevel, () {
                  setState(() => _micGain = 2.0);
                  _updateMicGain(2.0);
                }),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _buildPresetButton('Normal', 4, currentLevel, () {
                  setState(() => _micGain = 4.0);
                  _updateMicGain(4.0);
                }),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _buildPresetButton('High', 6, currentLevel, () {
                  setState(() => _micGain = 6.0);
                  _updateMicGain(6.0);
                }),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPresetButton(String label, int level, int currentLevel, VoidCallback onTap) {
    final isSelected = level == currentLevel;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isSelected ? Colors.white.withOpacity(0.8) : Colors.transparent,
            width: 1.5,
          ),
        ),
        child: Column(
          children: [
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                color: isSelected ? Colors.white : Colors.grey.shade400,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

List<Widget> deviceSettingsWidgets(BtDevice? device, BuildContext context) {
  var provider = Provider.of<DeviceProvider>(context, listen: true);

  return [
    ListTile(
      title: const Text('Device Name'),
      subtitle: Text(device?.name ?? 'Omi DevKit'),
    ),
    ListTile(
      title: const Text('Device ID'),
      subtitle: Text(device?.id ?? '12AB34CD:56EF78GH'),
    ),
    GestureDetector(
      onTap: () {
        routeToPage(context, FirmwareUpdate(device: device));
      },
      child: ListTile(
        title: const Text('Update Latest Version'),
        subtitle: Text('Current: ${device?.firmwareRevision ?? '1.0.2'}'),
        trailing: const Icon(
          Icons.arrow_forward_ios,
          size: 16,
        ),
      ),
    ),
    GestureDetector(
      onTap: () {
        if (!provider.isDeviceStorageSupport) {
          showDialog(
            context: context,
            builder: (c) => getDialog(
              context,
              () => Navigator.of(context).pop(),
              () => {},
              'V2 undetected',
              'We see that you either have a V1 device or your device is not connected. SD Card functionality is available only for V2 devices.',
              singleButton: true,
            ),
          );
        } else {
          var page = const SyncPage();
          routeToPage(context, page);
        }
      },
      child: const ListTile(
        title: Text('SD Card Sync'),
        subtitle: Text('Import audio files from SD Card'),
        trailing: Icon(
          Icons.arrow_forward_ios,
          size: 16,
        ),
      ),
    ),
    ListTile(
      title: const Text('Hardware Revision'),
      subtitle: Text(device?.hardwareRevision ?? 'XIAO'),
    ),
    ListTile(
      title: const Text('Model Number'),
      subtitle: Text(device?.modelNumber ?? 'Omi DevKit'),
    ),
    ListTile(
      title: const Text('Manufacturer Name'),
      subtitle: Text(device?.manufacturerName ?? 'Based Hardware'),
    ),
  ];
}
