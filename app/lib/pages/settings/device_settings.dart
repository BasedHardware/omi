import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
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
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

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

  Widget _buildSectionHeader(String title, {String? subtitle}) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, right: 4, bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(
              subtitle,
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 14,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildProfileStyleItem({
    required IconData icon,
    required String title,
    String? chipValue,
    String? copyValue,
    VoidCallback? onTap,
    bool showChevron = true,
  }) {
    final content = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      child: Row(
        children: [
          SizedBox(
            width: 24,
            height: 24,
            child: FaIcon(icon, color: const Color(0xFF8E8E93), size: 20),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 17,
                fontWeight: FontWeight.w400,
              ),
            ),
          ),
          if (chipValue != null) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                chipValue,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            if (showChevron) const SizedBox(width: 8),
          ],
          if (showChevron)
            const Icon(
              Icons.chevron_right,
              color: Color(0xFF3C3C43),
              size: 20,
            ),
        ],
      ),
    );

    if (copyValue != null) {
      return GestureDetector(
        onTap: () {
          Clipboard.setData(ClipboardData(text: copyValue));
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('$title copied to clipboard')),
          );
        },
        child: content,
      );
    }

    if (onTap != null) {
      return GestureDetector(onTap: onTap, child: content);
    }
    return content;
  }

  Widget _buildDeviceInfoSection(BtDevice? device, DeviceProvider provider) {
    final deviceName = device?.name ?? 'Omi DevKit';
    final deviceId = device?.id ?? '12AB34CD:56EF78GH';

    String truncateId(String id) {
      if (id.length > 10) {
        return '${id.substring(0, 4)}•••${id.substring(id.length - 4)}';
      }
      return id;
    }

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.microchip,
            title: 'Device Name',
            chipValue: deviceName,
            copyValue: deviceName,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.fingerprint,
            title: 'Device ID',
            chipValue: truncateId(deviceId),
            copyValue: deviceId,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.download,
            title: 'Firmware',
            chipValue: device?.firmwareRevision ?? '1.0.2',
            onTap: () => routeToPage(context, FirmwareUpdate(device: device)),
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.sdCard,
            title: 'SD Card Sync',
            onTap: () {
              if (!provider.isDeviceStorageSupport) {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () => Navigator.of(context).pop(),
                    () {},
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
          ),
        ],
      ),
    );
  }

  Widget _buildHardwareInfoSection(BtDevice? device) {
    final hardwareRevision = device?.hardwareRevision ?? 'XIAO';
    final modelNumber = device?.modelNumber ?? 'Omi DevKit';
    final manufacturer = device?.manufacturerName ?? 'Based Hardware';

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.gears,
            title: 'Hardware Revision',
            chipValue: hardwareRevision,
            copyValue: hardwareRevision,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.hashtag,
            title: 'Model Number',
            chipValue: modelNumber,
            copyValue: modelNumber,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.industry,
            title: 'Manufacturer',
            chipValue: manufacturer,
            copyValue: manufacturer,
            showChevron: false,
          ),
        ],
      ),
    );
  }

  String _getDoubleTapActionLabel(int action) {
    switch (action) {
      case 0:
        return 'End Conversation';
      case 1:
        return 'Pause/Resume';
      case 2:
        return 'Star Conversation';
      default:
        return 'End Conversation';
    }
  }

  void _showDoubleTapActionSheet() {
    int currentAction = SharedPreferencesUtil().doubleTapAction;

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return SafeArea(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    margin: const EdgeInsets.only(top: 12, bottom: 16),
                    width: 36,
                    height: 4,
                    decoration: BoxDecoration(
                      color: const Color(0xFF3C3C43),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  const Text(
                    'Double Tap Action',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Choose what happens when you double tap',
                    style: TextStyle(
                      color: Colors.grey.shade500,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 16),
                  ListTile(
                    title: const Text(
                      'End & Process Conversation',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    trailing: currentAction == 0 ? const Icon(Icons.check, color: Colors.white, size: 20) : null,
                    onTap: () {
                      setState(() => SharedPreferencesUtil().doubleTapAction = 0);
                      Navigator.pop(sheetContext);
                    },
                  ),
                  ListTile(
                    title: const Text(
                      'Pause/Resume Recording',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    trailing: currentAction == 1 ? const Icon(Icons.check, color: Colors.white, size: 20) : null,
                    onTap: () {
                      setState(() => SharedPreferencesUtil().doubleTapAction = 1);
                      Navigator.pop(sheetContext);
                    },
                  ),
                  ListTile(
                    title: const Text(
                      'Star Ongoing Conversation',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    subtitle: Text(
                      'Mark to star when conversation ends',
                      style: TextStyle(
                        color: Colors.grey.shade500,
                        fontSize: 12,
                      ),
                    ),
                    trailing: currentAction == 2 ? const Icon(Icons.check, color: Colors.white, size: 20) : null,
                    onTap: () {
                      setState(() => SharedPreferencesUtil().doubleTapAction = 2);
                      Navigator.pop(sheetContext);
                    },
                  ),
                  const SizedBox(height: 16),
                ],
              ),
            );
          },
        );
      },
    );
  }

  void _showBrightnessSheet() {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      margin: const EdgeInsets.only(bottom: 16),
                      width: 36,
                      height: 4,
                      decoration: BoxDecoration(
                        color: const Color(0xFF3C3C43),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'LED Brightness',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          '${_dimRatio.round()}%',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    SliderTheme(
                      data: SliderThemeData(
                        activeTrackColor: Colors.white,
                        inactiveTrackColor: Colors.grey.shade800,
                        thumbColor: Colors.white,
                        overlayColor: Colors.white.withOpacity(0.1),
                        thumbShape: const RoundSliderThumbShape(
                          enabledThumbRadius: 12,
                          elevation: 2,
                        ),
                        overlayShape: const RoundSliderOverlayShape(overlayRadius: 24),
                        trackHeight: 6,
                      ),
                      child: Slider(
                        value: _dimRatio,
                        min: 0,
                        max: 100,
                        divisions: 100,
                        onChanged: (double value) {
                          setSheetState(() {});
                          setState(() {
                            _dimRatio = value;
                          });
                          if (!(_debounce?.isActive ?? false)) {
                            _debounce = Timer(const Duration(milliseconds: 300), () {
                              _updateDimRatio(value);
                            });
                          }
                        },
                        onChangeEnd: (double value) {
                          _debounce?.cancel();
                          _updateDimRatio(value);
                        },
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Off', style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                        Text('Max', style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                      ],
                    ),
                    const SizedBox(height: 16),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  void _showMicGainSheet() {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            String getGainLabel(int level) {
              const labels = ['Mute', '-20dB', '-10dB', '+0dB', '+6dB', '+10dB', '+20dB', '+30dB', '+40dB'];
              return level >= 0 && level < labels.length ? labels[level] : '';
            }

            String getGainDescription(int level) {
              const descriptions = [
                'Microphone is muted',
                'Very quiet - for loud environments',
                'Quiet - for moderate noise',
                'Neutral - balanced recording',
                'Slightly boosted - normal use',
                'Boosted - for quiet environments',
                'High - for distant or soft voices',
                'Very high - for very quiet sources',
                'Maximum - use with caution',
              ];
              return level >= 0 && level < descriptions.length ? descriptions[level] : '';
            }

            final currentLevel = _micGain.round();

            return SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      margin: const EdgeInsets.only(bottom: 16),
                      width: 36,
                      height: 4,
                      decoration: BoxDecoration(
                        color: const Color(0xFF3C3C43),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Mic Gain',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          getGainLabel(currentLevel),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      getGainDescription(currentLevel),
                      style: TextStyle(
                        color: Colors.grey.shade500,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(height: 24),
                    SliderTheme(
                      data: SliderThemeData(
                        activeTrackColor: Colors.white,
                        inactiveTrackColor: Colors.grey.shade800,
                        thumbColor: Colors.white,
                        overlayColor: Colors.white.withOpacity(0.1),
                        thumbShape: const RoundSliderThumbShape(
                          enabledThumbRadius: 12,
                          elevation: 2,
                        ),
                        overlayShape: const RoundSliderOverlayShape(overlayRadius: 24),
                        trackHeight: 6,
                      ),
                      child: Slider(
                        value: _micGain,
                        min: 0,
                        max: 8,
                        divisions: 8,
                        onChanged: (double value) {
                          setSheetState(() {});
                          setState(() {
                            _micGain = value;
                          });
                          if (!(_micGainDebounce?.isActive ?? false)) {
                            _micGainDebounce = Timer(const Duration(milliseconds: 300), () {
                              _updateMicGain(value);
                            });
                          }
                        },
                        onChangeEnd: (double value) {
                          _micGainDebounce?.cancel();
                          _updateMicGain(value);
                        },
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Mute', style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                        Text('Max', style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                      ],
                    ),
                    const SizedBox(height: 20),
                    Row(
                      children: [
                        Expanded(
                          child: _buildPresetButton('Quiet', 2, currentLevel, () {
                            setSheetState(() {});
                            setState(() => _micGain = 2.0);
                            _updateMicGain(2.0);
                          }),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _buildPresetButton('Normal', 4, currentLevel, () {
                            setSheetState(() {});
                            setState(() => _micGain = 4.0);
                            _updateMicGain(4.0);
                          }),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _buildPresetButton('High', 6, currentLevel, () {
                            setSheetState(() {});
                            setState(() => _micGain = 6.0);
                            _updateMicGain(6.0);
                          }),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildPresetButton(String label, int level, int currentLevel, VoidCallback onTap) {
    final isSelected = level == currentLevel;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white.withOpacity(0.1) : const Color(0xFF2A2A2E),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: isSelected ? Colors.white.withOpacity(0.5) : Colors.transparent,
            width: 1,
          ),
        ),
        child: Center(
          child: Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
              color: isSelected ? Colors.white : Colors.grey.shade400,
            ),
          ),
        ),
      ),
    );
  }

  String _getMicGainLabel(int level) {
    const labels = ['Mute', '-20dB', '-10dB', '+0dB', '+6dB', '+10dB', '+20dB', '+30dB', '+40dB'];
    return level >= 0 && level < labels.length ? labels[level] : '';
  }

  Widget _buildCustomizationSection() {
    final doubleTapAction = SharedPreferencesUtil().doubleTapAction;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          // Double Tap
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.handPointer,
            title: 'Double Tap',
            chipValue: _getDoubleTapActionLabel(doubleTapAction),
            onTap: _showDoubleTapActionSheet,
          ),
          // LED Brightness
          if (_isDimRatioLoaded && _hasDimmingFeature == true) ...[
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            _buildProfileStyleItem(
              icon: FontAwesomeIcons.lightbulb,
              title: 'LED Brightness',
              chipValue: '${_dimRatio.round()}%',
              onTap: _showBrightnessSheet,
            ),
          ],
          // Mic Gain
          if (_isMicGainLoaded && _hasMicGainFeature == true) ...[
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            _buildProfileStyleItem(
              icon: FontAwesomeIcons.microphone,
              title: 'Mic Gain',
              chipValue: _getMicGainLabel(_micGain.round()),
              onTap: _showMicGainSheet,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildActionsSection(DeviceProvider provider) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          // Charging Help
          GestureDetector(
            onTap: () async {
              if (PlatformService.isIntercomSupported) {
                await IntercomManager().displayChargingArticle(provider.pairedDevice?.name ?? 'DevKit1');
              } else {
                // Fallback to web URL for desktop platforms
                final deviceName = provider.pairedDevice?.name ?? 'DevKit1';
                String url;
                if (deviceName == 'Omi DevKit 2') {
                  url = 'https://www.omi.me/pages/charging-devkit2';
                } else if (deviceName == 'Omi') {
                  url = 'https://www.omi.me/pages/charging-omi';
                } else {
                  url = 'https://www.omi.me/pages/charging';
                }
                final uri = Uri.parse(url);
                if (await canLaunchUrl(uri)) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                }
              }
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
              child: Row(
                children: [
                  const SizedBox(
                    width: 24,
                    height: 24,
                    child: FaIcon(FontAwesomeIcons.circleQuestion, color: Color(0xFF8E8E93), size: 20),
                  ),
                  const SizedBox(width: 16),
                  const Expanded(
                    child: Text(
                      'Charging Issues',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right,
                    color: Color(0xFF3C3C43),
                    size: 20,
                  ),
                ],
              ),
            ),
          ),
          if (provider.isConnected) ...[
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            // Disconnect
            GestureDetector(
              onTap: () async {
                await SharedPreferencesUtil().btDeviceSet(BtDevice(id: '', name: '', type: DeviceType.omi, rssi: 0));
                SharedPreferencesUtil().deviceName = '';
                if (provider.connectedDevice != null) {
                  await _bleDisconnectDevice(provider.connectedDevice!);
                }
                provider.setIsConnected(false);
                provider.setConnectedDevice(null);
                provider.updateConnectingStatus(false);
                MixpanelManager().disconnectFriendClicked();
                if (context.mounted) {
                  Navigator.of(context).pop();
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Your Omi has been disconnected 😔')),
                  );
                }
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
                child: Row(
                  children: [
                    const SizedBox(
                      width: 24,
                      height: 24,
                      child: FaIcon(FontAwesomeIcons.linkSlash, color: Colors.redAccent, size: 20),
                    ),
                    const SizedBox(width: 16),
                    Text(
                      provider.connectedDevice == null ? 'Unpair Device' : 'Disconnect Device',
                      style: const TextStyle(
                        color: Colors.redAccent,
                        fontSize: 17,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildDisconnectedOverlay() {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: const Color(0xFF2A2A2E),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Center(
              child: FaIcon(FontAwesomeIcons.linkSlash, color: Colors.grey.shade500, size: 24),
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'Device Not Connected',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Connect your Omi device to access\ndevice settings and customization',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.grey.shade500,
              fontSize: 14,
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: const Color(0xFF0D0D0D),
        appBar: AppBar(
          backgroundColor: const Color(0xFF0D0D0D),
          elevation: 0,
          leading: IconButton(
            icon: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: const Text(
            'Device Settings',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          centerTitle: true,
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (!provider.isConnected) ...[
                const SizedBox(height: 16),
                _buildDisconnectedOverlay(),
                const SizedBox(height: 32),
              ],
              if (provider.isConnected) ...[
                const SizedBox(height: 16),
                _buildSectionHeader('Device Information'),
                _buildDeviceInfoSection(provider.pairedDevice, provider),
                const SizedBox(height: 32),
                _buildSectionHeader('Customization'),
                _buildCustomizationSection(),
                const SizedBox(height: 32),
                _buildSectionHeader('Hardware'),
                _buildHardwareInfoSection(provider.pairedDevice),
                const SizedBox(height: 32),
              ],
              _buildActionsSection(provider),
              const SizedBox(height: 48),
            ],
          ),
        ),
      );
    });
  }
}
