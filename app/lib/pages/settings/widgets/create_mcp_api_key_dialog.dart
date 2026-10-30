import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/widgets/mcp_api_key_created_dialog.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Names and creates an MCP key. Shown with `showDialog(builder: (_) => const CreateMcpApiKeyDialog())`.
class CreateMcpApiKeyDialog extends StatefulWidget {
  const CreateMcpApiKeyDialog({super.key});

  @override
  State<CreateMcpApiKeyDialog> createState() => _CreateMcpApiKeyDialogState();
}

class _CreateMcpApiKeyDialogState extends State<CreateMcpApiKeyDialog> {
  final _nameController = TextEditingController();
  bool _isCreating = false;

  @override
  void initState() {
    super.initState();
    _nameController.addListener(_onNameChanged);
  }

  @override
  void dispose() {
    _nameController.removeListener(_onNameChanged);
    _nameController.dispose();
    super.dispose();
  }

  void _onNameChanged() => setState(() {});

  bool get _canCreate => !_isCreating && _nameController.text.trim().isNotEmpty;

  Future<void> _createKey() async {
    if (!_canCreate) return;
    setState(() => _isCreating = true);
    final provider = Provider.of<McpProvider>(context, listen: false);
    final newKey = await provider.createKey(_nameController.text.trim());

    if (!mounted) return;
    Navigator.of(context).pop(); // Close this dialog
    if (newKey != null) {
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => McpApiKeyCreatedDialog(apiKey: newKey),
      );
    } else {
      final error = provider.error;
      OmiFeedback.error(
        context,
        error != null ? context.l10n.failedToCreateKeyWithError(error) : context.l10n.failedToCreateKeyTryAgain,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return OmiAlertDialog(
      title: context.l10n.createNewKey,
      // The Cupertino dialog has no Material ancestor; the text field needs one.
      content: Material(
        type: MaterialType.transparency,
        child: TextField(
          controller: _nameController,
          autofocus: true,
          enabled: !_isCreating,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => _createKey(),
          style: OmiType.body,
          decoration: InputDecoration(
            labelText: context.l10n.name,
            hintText: context.l10n.keyNameHint,
            hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
            filled: true,
            fillColor: OmiColors.surface2,
            isDense: true,
            border: const OutlineInputBorder(borderRadius: OmiRadius.smAll, borderSide: BorderSide.none),
          ),
        ),
      ),
      actions: [
        OmiDialogAction(
          label: context.l10n.cancel,
          onPressed: _isCreating ? null : () => Navigator.of(context).pop(),
        ),
        OmiDialogAction(
          label: _isCreating ? context.l10n.creating : context.l10n.create,
          isDefault: true,
          onPressed: _canCreate ? _createKey : null,
        ),
      ],
    );
  }
}
