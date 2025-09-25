import 'package:flutter/material.dart';
import '../../../utils/platform/auto_start_service.dart';

class AutostartSettingsPage extends StatefulWidget {
  const AutostartSettingsPage({super.key});

  @override
  State<AutostartSettingsPage> createState() => _AutostartSettingsPageState();
}

class _AutostartSettingsPageState extends State<AutostartSettingsPage> {
  bool _isAutoStartEnabled = false;
  StartupBehavior _startupBehavior = StartupBehavior.showMainWindow;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final isEnabled = await AutoStartService.isAutoStartEnabled();
    final behavior = await AutoStartService.getStartupBehavior();
    if (mounted) {
      setState(() {
        _isAutoStartEnabled = isEnabled;
        _startupBehavior = behavior;
        _isLoading = false;
      });
    }
  }

  Future<void> _updateAutoStart(bool value) async {
    setState(() {
      _isAutoStartEnabled = value;
    });
    await AutoStartService.setAutoStart(value);
  }

  Future<void> _updateStartupBehavior(StartupBehavior? value) async {
    if (value == null) return;
    setState(() {
      _startupBehavior = value;
    });
    await AutoStartService.setStartupBehavior(value);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Auto-start Settings'),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16.0),
              children: [
                SwitchListTile(
                  title: const Text('Start Omi on system login'),
                  value: _isAutoStartEnabled,
                  onChanged: _updateAutoStart,
                ),
                if (_isAutoStartEnabled)
                  ListTile(
                    title: const Text('On startup, show:'),
                    trailing: DropdownButton<StartupBehavior>(
                      value: _startupBehavior,
                      onChanged: _updateStartupBehavior,
                      items: const [
                        DropdownMenuItem(
                          value: StartupBehavior.showMainWindow,
                          child: Text('Main Window'),
                        ),
                        DropdownMenuItem(
                          value: StartupBehavior.showFloatingButton,
                          child: Text('Floating Button'),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }
}
