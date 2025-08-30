import 'package:flutter/material.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:provider/provider.dart';

class DeviceNameDialog extends StatefulWidget {
  final String currentName;
  final Function(String) onNameChanged;

  const DeviceNameDialog({
    Key? key,
    required this.currentName,
    required this.onNameChanged,
  }) : super(key: key);

  @override
  State<DeviceNameDialog> createState() => _DeviceNameDialogState();
}

class _DeviceNameDialogState extends State<DeviceNameDialog> {
  late TextEditingController _controller;
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.currentName);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _saveDeviceName() async {
    final newName = _controller.text.trim();

    if (newName.isEmpty) {
      setState(() {
        _errorMessage = 'Device name cannot be empty';
      });
      return;
    }

    if (newName.length > 32) {
      setState(() {
        _errorMessage = 'Device name must be 32 characters or less';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final deviceProvider = context.read<DeviceProvider>();
      final success = await deviceProvider.updateDeviceName(newName);

      if (success) {
        // Update the device name locally
        widget.onNameChanged(newName);

        Navigator.of(context).pop();

        // Show success message
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Device name updated successfully'),
            backgroundColor: Colors.green,
          ),
        );
      } else {
        setState(() {
          _errorMessage = 'Failed to update device name. Please check your connection and try again.';
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Error updating device name: $e';
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Change Device Name'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'Enter a new name for your device. This name will be stored on the device and used for identification.',
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _controller,
            decoration: InputDecoration(
              labelText: 'Device Name',
              hintText: 'Enter device name',
              errorText: _errorMessage,
              border: const OutlineInputBorder(),
            ),
            maxLength: 32,
            enabled: !_isLoading,
            onChanged: (value) {
              if (_errorMessage != null) {
                setState(() {
                  _errorMessage = null;
                });
              }
            },
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _isLoading ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: _isLoading ? null : _saveDeviceName,
          child: _isLoading
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Save'),
        ),
      ],
    );
  }
}
