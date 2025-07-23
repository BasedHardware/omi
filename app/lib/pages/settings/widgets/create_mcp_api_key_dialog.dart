import 'package:flutter/material.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_created_dialog.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:provider/provider.dart';

class CreateMcpApiKeyDialog extends StatefulWidget {
  const CreateMcpApiKeyDialog({super.key});

  @override
  State<CreateMcpApiKeyDialog> createState() => _CreateMcpApiKeyDialogState();
}

class _CreateMcpApiKeyDialogState extends State<CreateMcpApiKeyDialog> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  bool _isCreating = false;

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _createKey() async {
    if (_formKey.currentState!.validate()) {
      setState(() => _isCreating = true);
      final provider = Provider.of<McpProvider>(context, listen: false);
      final newKey = await provider.createKey(_nameController.text.trim());

      if (mounted) {
        Navigator.of(context).pop(); // Close this dialog
        if (newKey != null) {
          showDialog(
            context: context,
            barrierDismissible: false,
            builder: (context) => McpApiKeyCreatedDialog(apiKey: newKey),
          );
        } else {
          final error = Provider.of<McpProvider>(context, listen: false).error;
          if (error != null) {
            AppSnackbar.showSnackbarError('Failed to create key: $error');
          } else {
            AppSnackbar.showSnackbarError('Failed to create key. Please try again.');
          }
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Create New Key'),
      content: Form(
        key: _formKey,
        child: TextFormField(
          controller: _nameController,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Name',
            hintText: 'e.g., Claude Desktop',
          ),
          validator: (value) {
            if (value == null || value.trim().isEmpty) {
              return 'Please enter a name.';
            }
            return null;
          },
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _isCreating ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: _isCreating ? null : _createKey,
          style: ElevatedButton.styleFrom(
            foregroundColor: Colors.white,
            backgroundColor: Theme.of(context).colorScheme.secondary,
          ),
          child: _isCreating
              ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('Create'),
        ),
      ],
    );
  }
}
