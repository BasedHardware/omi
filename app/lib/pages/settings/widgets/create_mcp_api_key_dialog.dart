import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/widgets/mcp_api_key_created_dialog.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
            AppSnackbar.showSnackbarError(context.l10n.failedToCreateKeyWithError(error));
          } else {
            AppSnackbar.showSnackbarError(context.l10n.failedToCreateKeyTryAgain);
          }
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(context.l10n.createNewKey),
      content: Form(
        key: _formKey,
        child: TextFormField(
          controller: _nameController,
          autofocus: true,
          decoration: InputDecoration(
            labelText: context.l10n.name,
            hintText: context.l10n.keyNameHint,
          ),
          validator: (value) {
            if (value == null || value.trim().isEmpty) {
              return context.l10n.pleaseEnterAName;
            }
            return null;
          },
        ),
      ),
      actions: <Widget>[
        TextButton(
          onPressed: _isCreating ? null : () => Navigator.of(context).pop(),
          child: Text(context.l10n.cancel),
        ),
        ElevatedButton(
          onPressed: _isCreating ? null : _createKey,
          style: ElevatedButton.styleFrom(
            foregroundColor: Colors.white,
            backgroundColor: Theme.of(context).colorScheme.secondary,
          ),
          child: _isCreating
              ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
              : Text(context.l10n.create),
        ),
      ],
    );
  }
}
