import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/atoms/omi_settings_tile.dart';

class ButtonSettingsPage extends StatefulWidget {
  const ButtonSettingsPage({super.key});

  @override
  State<ButtonSettingsPage> createState() => _ButtonSettingsPageState();
}

class _ButtonSettingsPageState extends State<ButtonSettingsPage> {
  final _prefs = SharedPreferencesUtil();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Button Settings'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          OmiSettingsTile(
            title: 'Single Press',
            subtitle: 'Ask Question',
            icon: Icons.touch_app,
            onTap: () => _showActionDialog('singlePress'),
          ),
          OmiSettingsTile(
            title: 'Double Press',
            subtitle: 'Mute/Unmute',
            icon: Icons.double_arrow,
            onTap: () => _showActionDialog('doublePress'),
          ),
          OmiSettingsTile(
            title: 'Long Press',
            subtitle: 'Turn On/Off',
            icon: Icons.power_settings_new,
            onTap: () => _showActionDialog('longPress'),
          ),
          OmiSettingsTile(
            title: 'Triple Press',
            subtitle: 'End Conversation',
            icon: Icons.threesixty,
            onTap: () => _showActionDialog('triplePress'),
          ),
        ],
      ),
    );
  }

  void _showActionDialog(String buttonType) {
    final actions = [
      'ask_question',
      'mute_unmute',
      'turn_on_off',
      'end_conversation',
    ];

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Select Action'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: actions.map((action) => _actionTile(buttonType, action)).toList(),
        ),
      ),
    );
  }

  Widget _actionTile(String buttonType, String action) {
    return ListTile(
      title: Text(_formatAction(action)),
      onTap: () {
        Navigator.pop(context);
        _saveButtonAction(buttonType, action);
        setState(() {});
      },
    );
  }

  String _formatAction(String action) {
    return action.split('_').map((word) => 
      word[0].toUpperCase() + word.substring(1)
    ).join(' ');
  }

  void _saveButtonAction(String buttonType, String action) {
    switch (buttonType) {
      case 'singlePress':
        _prefs.buttonSinglePressAction = action;
        break;
      case 'doublePress':
        _prefs.buttonDoublePressAction = action;
        break;
      case 'longPress':
        _prefs.buttonLongPressAction = action;
        break;
      case 'triplePress':
        _prefs.buttonTriplePressAction = action;
        break;
    }
  }
}
