import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/preferences.dart';

class FastTransferSettingsPage extends StatefulWidget {
  const FastTransferSettingsPage({super.key});

  @override
  State<FastTransferSettingsPage> createState() => _FastTransferSettingsPageState();
}

class _FastTransferSettingsPageState extends State<FastTransferSettingsPage> {
  late String _selectedMethod;

  @override
  void initState() {
    super.initState();
    _selectedMethod = SharedPreferencesUtil().preferredSyncMethod;
  }

  void _selectMethod(String method) {
    if (method == 'wifi' && !SharedPreferencesUtil().hasSeenFastTransferIntro) {
      _showFastTransferIntroDialog().then((confirmed) {
        if (confirmed == true) {
          SharedPreferencesUtil().hasSeenFastTransferIntro = true;
          _applyMethod(method);
        }
      });
    } else {
      _applyMethod(method);
    }
  }

  void _applyMethod(String method) {
    setState(() => _selectedMethod = method);
    SharedPreferencesUtil().preferredSyncMethod = method;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(method == 'wifi' ? 'Fast Transfer enabled' : 'Bluetooth sync enabled'),
        backgroundColor: Colors.green,
      ),
    );
  }

  Future<bool?> _showFastTransferIntroDialog() {
    return showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text(
          'Enable Fast Transfer',
          style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Fast Transfer uses WiFi for ~5x faster speeds. Your phone will temporarily connect to your Omi device\'s WiFi network during transfer.',
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.amber.withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Icon(Icons.info_outline, color: Colors.amber.shade300, size: 18),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Internet access is paused during transfer',
                      style: TextStyle(color: Colors.amber.shade300, fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text('Cancel', style: TextStyle(color: Colors.grey.shade500)),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Enable', style: TextStyle(color: Colors.deepPurpleAccent, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }

  Widget _buildFaIcon(IconData icon, {double size = 18, Color color = const Color(0xFF8E8E93)}) {
    return Padding(
      padding: const EdgeInsets.only(left: 2, top: 1),
      child: FaIcon(icon, size: size, color: color),
    );
  }

  Widget _buildMethodCard({
    required String method,
    required String title,
    required String speed,
    required IconData icon,
    required Color iconColor,
    String? badge,
    String? description,
  }) {
    final isSelected = _selectedMethod == method;

    return GestureDetector(
      onTap: () => _selectMethod(method),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? iconColor.withOpacity(0.5) : Colors.transparent,
            width: 2,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: iconColor.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(icon, color: iconColor, size: 22),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(
                            title,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          if (badge != null) ...[
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: iconColor.withOpacity(0.3),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                badge,
                                style: TextStyle(
                                  color: iconColor,
                                  fontSize: 10,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        speed,
                        style: TextStyle(
                          color: Colors.grey.shade500,
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: isSelected ? Colors.green.withOpacity(0.2) : const Color(0xFF2A2A2E),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Text(
                    isSelected ? 'Selected' : 'Select',
                    style: TextStyle(
                      color: isSelected ? Colors.green : Colors.grey.shade400,
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
            if (description != null) ...[
              const SizedBox(height: 16),
              Text(
                description,
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 13,
                  height: 1.5,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        leading: IconButton(
          icon: _buildFaIcon(FontAwesomeIcons.chevronLeft, size: 18, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text(
          'Transfer Method',
          style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Choose how recordings are transferred from your Omi device to your phone.',
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.5),
            ),
            const SizedBox(height: 24),
            _buildMethodCard(
              method: 'wifi',
              title: 'Fast Transfer',
              speed: '~150 KB/s via WiFi',
              icon: Icons.bolt,
              iconColor: Colors.blue,
              badge: '5X FASTER',
              description:
                  'Creates a direct WiFi connection to your Omi device. Your phone temporarily disconnects from your regular WiFi during transfer.',
            ),
            const SizedBox(height: 16),
            _buildMethodCard(
              method: 'ble',
              title: 'Bluetooth',
              speed: '~30 KB/s via BLE',
              icon: Icons.bluetooth,
              iconColor: Colors.deepPurpleAccent,
              description:
                  'Uses standard Bluetooth Low Energy connection. Slower but doesn\'t affect your WiFi connection.',
            ),
          ],
        ),
      ),
    );
  }
}
