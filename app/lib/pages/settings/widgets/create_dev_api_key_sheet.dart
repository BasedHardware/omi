import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/widgets/dev_api_key_created_dialog.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class CreateDevApiKeySheet extends StatefulWidget {
  const CreateDevApiKeySheet({super.key});

  static Future<void> show(BuildContext context, DevApiKeyProvider provider) {
    return showOmiSheet(
      context: context,
      title: context.l10n.createApiKey,
      builder: (ctx) => ChangeNotifierProvider.value(value: provider, child: const CreateDevApiKeySheet()),
    );
  }

  @override
  State<CreateDevApiKeySheet> createState() => _CreateDevApiKeySheetState();
}

class _CreateDevApiKeySheetState extends State<CreateDevApiKeySheet> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  bool _isCreating = false;

  final Map<String, bool> _scopes = {
    'conversations:read': false,
    'conversations:write': false,
    'memories:read': false,
    'memories:write': false,
    'action_items:read': false,
    'action_items:write': false,
    'goals:read': false,
    'goals:write': false,
  };

  List<String> get _selectedScopes {
    return _scopes.entries.where((e) => e.value).map((e) => e.key).toList();
  }

  void _toggleScope(String scope) {
    setState(() {
      _scopes[scope] = !_scopes[scope]!;
    });
  }

  void _selectReadOnly() {
    setState(() {
      _scopes.updateAll((key, value) => false);
      _scopes['conversations:read'] = true;
      _scopes['memories:read'] = true;
      _scopes['action_items:read'] = true;
      _scopes['goals:read'] = true;
    });
  }

  void _selectFullAccess() {
    setState(() {
      _scopes.updateAll((key, value) => true);
    });
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _createKey() async {
    if (_formKey.currentState!.validate()) {
      setState(() => _isCreating = true);
      final provider = Provider.of<DevApiKeyProvider>(context, listen: false);
      final selectedScopes = _selectedScopes.isEmpty ? null : _selectedScopes;
      final newKey = await provider.createKey(_nameController.text.trim(), scopes: selectedScopes);

      if (mounted) {
        Navigator.of(context).pop();
        if (newKey != null) {
          DevApiKeyCreatedSheet.show(context, newKey);
        } else {
          final error = provider.error;
          OmiFeedback.error(
            context,
            error != null ? context.l10n.failedToCreateKeyWithError(error) : context.l10n.failedToCreateKeyTryAgain,
          );
        }
      }
    }
  }

  bool get _isReadOnly {
    return _scopes['conversations:read'] == true &&
        _scopes['memories:read'] == true &&
        _scopes['action_items:read'] == true &&
        _scopes['goals:read'] == true &&
        _scopes['conversations:write'] == false &&
        _scopes['memories:write'] == false &&
        _scopes['action_items:write'] == false &&
        _scopes['goals:write'] == false;
  }

  bool get _isFullAccess {
    return _scopes.values.every((v) => v);
  }

  Widget _buildLabel(String text) {
    return Text(
      text,
      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600, letterSpacing: 0.5),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return SingleChildScrollView(
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(l10n.accessDataProgrammatically, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
            const SizedBox(height: OmiSpacing.xl),
            // Name input
            _buildLabel(l10n.keyNameLabel),
            const SizedBox(height: 10),
            TextFormField(
              controller: _nameController,
              autofocus: false,
              enabled: !_isCreating,
              style: OmiType.body,
              decoration: InputDecoration(
                hintText: l10n.keyNamePlaceholder,
                hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
                filled: true,
                fillColor: OmiColors.surface2,
                border: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
                enabledBorder: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
                focusedBorder: const OutlineInputBorder(
                  borderRadius: OmiRadius.mdAll,
                  borderSide: BorderSide(color: OmiColors.textSecondary, width: 1.5),
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: OmiSpacing.md),
              ),
              validator: (value) {
                if (value == null || value.trim().isEmpty) {
                  return l10n.pleaseEnterAName;
                }
                return null;
              },
            ),
            const SizedBox(height: OmiSpacing.xl),
            // Permissions section
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: OmiSpacing.xs,
              runSpacing: OmiSpacing.xs,
              children: [
                _buildLabel(l10n.permissionsLabel),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _ScopeChoice(label: l10n.readOnlyScope, selected: _isReadOnly, onTap: _selectReadOnly),
                    const SizedBox(width: OmiSpacing.xs),
                    _ScopeChoice(label: l10n.fullAccessScope, selected: _isFullAccess, onTap: _selectFullAccess),
                  ],
                ),
              ],
            ),
            const SizedBox(height: OmiSpacing.md),
            // Permission rows
            OmiSettingsGroup(
              children: [
                _buildPermissionRow(
                    l10n.conversations, 'conversations:read', 'conversations:write', Icons.chat_bubble_outline),
                _buildPermissionRow(l10n.memories, 'memories:read', 'memories:write', Icons.psychology_outlined),
                _buildPermissionRow(
                    l10n.actionItems, 'action_items:read', 'action_items:write', Icons.task_alt_outlined),
                _buildPermissionRow(l10n.goals, 'goals:read', 'goals:write', Icons.flag_outlined),
              ],
            ),
            const SizedBox(height: OmiSpacing.sm),
            // Info note
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.info_outline, color: OmiColors.textTertiary, size: 16),
                const SizedBox(width: OmiSpacing.xs),
                Expanded(
                  child:
                      Text(l10n.permissionsInfoNote, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                ),
              ],
            ),
            const SizedBox(height: OmiSpacing.xl),
            OmiButton(label: l10n.createKey, expand: true, isLoading: _isCreating, onPressed: _createKey),
            const SizedBox(height: OmiSpacing.md),
          ],
        ),
      ),
    );
  }

  Widget _buildPermissionRow(String resource, String readScope, String writeScope, IconData icon) {
    return OmiSettingsRow(
      leading: Icon(icon),
      title: resource,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ScopeChoice(
            label: context.l10n.readScope,
            selected: _scopes[readScope] ?? false,
            onTap: () => _toggleScope(readScope),
          ),
          const SizedBox(width: OmiSpacing.xxs),
          _ScopeChoice(
            label: context.l10n.writeScope,
            selected: _scopes[writeScope] ?? false,
            onTap: () => _toggleScope(writeScope),
          ),
        ],
      ),
    );
  }
}

/// A selectable pill for a scope or scope preset: white when on (INV-UI-1), 44pt tall target.
class _ScopeChoice extends StatelessWidget {
  const _ScopeChoice({required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      toggled: selected,
      child: InkWell(
        onTap: onTap,
        borderRadius: OmiRadius.pillAll,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Center(
            widthFactor: 1,
            child: AnimatedContainer(
              duration: OmiMotion.of(context).quick,
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
              decoration: BoxDecoration(
                borderRadius: OmiRadius.pillAll,
                color: selected ? OmiColors.accent : OmiColors.surface3,
              ),
              child: Text(
                label,
                style: OmiType.footnote.copyWith(
                  color: selected ? OmiColors.onAccent : OmiColors.textSecondary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
