import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:provider/provider.dart';

class LocalStoragePage extends StatefulWidget {
  const LocalStoragePage({super.key});

  @override
  State<LocalStoragePage> createState() => _LocalStoragePageState();
}

class _LocalStoragePageState extends State<LocalStoragePage> {
  bool _isSaving = false;

  Future<void> _toggleLocalStorage(bool value) async {
    if (value) {
      final confirmed = await _showEnableDialog();
      if (confirmed != true) return;
    }

    setState(() => _isSaving = true);
    try {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = value;
      context.read<SyncProvider>().refreshWals();
      setState(() => _isSaving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              value ? 'Local storage enabled' : 'Local storage disabled',
            ),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      setState(() => _isSaving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to update settings: ${e.toString()}'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<bool?> _showEnableDialog() {
    return showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Privacy Notice',
            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Recordings may capture others\' voices. Ensure you have consent from all participants before enabling.',
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
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

  @override
  Widget build(BuildContext context) {
    final isEnabled = SharedPreferencesUtil().unlimitedLocalStorageEnabled;

    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        leading: IconButton(
          icon: _buildFaIcon(FontAwesomeIcons.chevronLeft, size: 18, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text('Store Audio on Phone',
            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      _buildFaIcon(FontAwesomeIcons.mobile, size: 20, color: Colors.deepPurpleAccent),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Text(
                          'Store Audio on Phone',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: isEnabled ? Colors.green.withOpacity(0.2) : const Color(0xFF2A2A2E),
                          borderRadius: BorderRadius.circular(100),
                        ),
                        child: Text(
                          isEnabled ? 'On' : 'Off',
                          style: TextStyle(
                            color: isEnabled ? Colors.green : Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Text(
                    'Keep all audio recordings stored locally on your phone. When disabled, only failed uploads are kept to save storage space.',
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 14,
                      height: 1.5,
                    ),
                  ),
                  const SizedBox(height: 24),
                  const Divider(height: 1, color: Color(0xFF3C3C43)),
                  const SizedBox(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Enable Local Storage',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      Transform.scale(
                        scale: 0.85,
                        child: CupertinoSwitch(
                          value: isEnabled,
                          onChanged: _isSaving ? null : _toggleLocalStorage,
                          activeTrackColor: Colors.deepPurpleAccent,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
