import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/widgets/dev_api_key_created_dialog.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';

class CreateDevApiKeySheet extends StatefulWidget {
  const CreateDevApiKeySheet({super.key});

  static Future<void> show(BuildContext context, DevApiKeyProvider provider) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => ChangeNotifierProvider.value(
        value: provider,
        child: const CreateDevApiKeySheet(),
      ),
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
          showModalBottomSheet(
            context: context,
            isScrollControlled: true,
            backgroundColor: Colors.transparent,
            isDismissible: false,
            enableDrag: false,
            builder: (context) => DevApiKeyCreatedSheet(apiKey: newKey),
          );
        } else {
          final error = Provider.of<DevApiKeyProvider>(context, listen: false).error;
          if (error != null) {
            AppSnackbar.showSnackbarError('Failed to create key: $error');
          } else {
            AppSnackbar.showSnackbarError('Failed to create key. Please try again.');
          }
        }
      }
    }
  }

  bool get _isReadOnly {
    return _scopes['conversations:read'] == true &&
        _scopes['memories:read'] == true &&
        _scopes['action_items:read'] == true &&
        _scopes['conversations:write'] == false &&
        _scopes['memories:write'] == false &&
        _scopes['action_items:write'] == false;
  }

  bool get _isFullAccess {
    return _scopes.values.every((v) => v);
  }

  Widget _buildPresetChip(String label, bool isSelected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          color: isSelected ? const Color(0xFF8B5CF6) : const Color(0xFF252525),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? Colors.white : const Color(0xFFAEAEB2),
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }

  Widget _buildPermissionTile(String resource, String readScope, String writeScope, IconData icon) {
    final hasRead = _scopes[readScope] ?? false;
    final hasWrite = _scopes[writeScope] ?? false;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: const Color(0xFF1A1A1A),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFF252525),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: const Color(0xFF8B5CF6), size: 20),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                resource,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            _buildTogglePill(
              leftLabel: 'R',
              rightLabel: 'W',
              leftSelected: hasRead,
              rightSelected: hasWrite,
              onLeftTap: () => _toggleScope(readScope),
              onRightTap: () => _toggleScope(writeScope),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTogglePill({
    required String leftLabel,
    required String rightLabel,
    required bool leftSelected,
    required bool rightSelected,
    required VoidCallback onLeftTap,
    required VoidCallback onRightTap,
  }) {
    // Determine border radius based on selection state
    final leftRadius = BorderRadius.only(
      topLeft: const Radius.circular(8),
      bottomLeft: const Radius.circular(8),
      topRight: Radius.circular(leftSelected && rightSelected ? 0 : 8),
      bottomRight: Radius.circular(leftSelected && rightSelected ? 0 : 8),
    );
    final rightRadius = BorderRadius.only(
      topRight: const Radius.circular(8),
      bottomRight: const Radius.circular(8),
      topLeft: Radius.circular(leftSelected && rightSelected ? 0 : 8),
      bottomLeft: Radius.circular(leftSelected && rightSelected ? 0 : 8),
    );

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        color: const Color(0xFF252525),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: onLeftTap,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                borderRadius: leftRadius,
                color: leftSelected ? const Color(0xFF3B82F6) : Colors.transparent,
              ),
              child: Text(
                leftLabel,
                style: TextStyle(
                  color: leftSelected ? Colors.white : const Color(0xFF6C6C70),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          GestureDetector(
            onTap: onRightTap,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                borderRadius: rightRadius,
                color: rightSelected ? const Color(0xFF8B5CF6) : Colors.transparent,
              ),
              child: Text(
                rightLabel,
                style: TextStyle(
                  color: rightSelected ? Colors.white : const Color(0xFF6C6C70),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).viewInsets.bottom;

    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF0F0F0F),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Padding(
        padding: EdgeInsets.only(bottom: bottomPadding),
        child: SingleChildScrollView(
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Handle bar
                Center(
                  child: Container(
                    margin: const EdgeInsets.only(top: 12, bottom: 8),
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: const Color(0xFF3C3C43),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                // Header
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [Color(0xFF8B5CF6), Color(0xFF7C3AED)],
                          ),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.key, color: Colors.white, size: 22),
                      ),
                      const SizedBox(width: 14),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Create API Key',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 20,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            SizedBox(height: 2),
                            Text(
                              'Access your data programmatically',
                              style: TextStyle(
                                color: Color(0xFF8E8E93),
                                fontSize: 13,
                              ),
                            ),
                          ],
                        ),
                      ),
                      GestureDetector(
                        onTap: () => Navigator.pop(context),
                        child: Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: const Color(0xFF252525),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Icon(Icons.close, color: Color(0xFF8E8E93), size: 20),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 28),
                // Name input
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'KEY NAME',
                        style: TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.5,
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextFormField(
                        controller: _nameController,
                        autofocus: false,
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                        decoration: InputDecoration(
                          hintText: 'e.g., My App Integration',
                          hintStyle: const TextStyle(color: Color(0xFF6C6C70), fontSize: 16),
                          filled: true,
                          fillColor: const Color(0xFF1A1A1A),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(14),
                            borderSide: const BorderSide(color: Color(0xFF2C2C2E)),
                          ),
                          enabledBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(14),
                            borderSide: const BorderSide(color: Color(0xFF2C2C2E)),
                          ),
                          focusedBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(14),
                            borderSide: const BorderSide(color: Color(0xFF8B5CF6), width: 1.5),
                          ),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                        ),
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return 'Please enter a name';
                          }
                          return null;
                        },
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 28),
                // Permissions section
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'PERMISSIONS',
                        style: TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.5,
                        ),
                      ),
                      Row(
                        children: [
                          _buildPresetChip('Read Only', _isReadOnly, _selectReadOnly),
                          const SizedBox(width: 8),
                          _buildPresetChip('Full Access', _isFullAccess, _selectFullAccess),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                // Permission tiles
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    children: [
                      _buildPermissionTile(
                          'Conversations', 'conversations:read', 'conversations:write', Icons.chat_bubble_outline),
                      _buildPermissionTile('Memories', 'memories:read', 'memories:write', Icons.psychology_outlined),
                      _buildPermissionTile(
                          'Action Items', 'action_items:read', 'action_items:write', Icons.task_alt_outlined),
                    ],
                  ),
                ),
                // Info note
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Row(
                    children: [
                      Icon(Icons.info_outline, color: Colors.amber.shade700, size: 16),
                      const SizedBox(width: 8),
                      const Expanded(
                        child: Text(
                          'R = Read, W = Write. Defaults to read-only if nothing selected.',
                          style: TextStyle(color: Color(0xFF6C6C70), fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                // Create button
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
                  child: SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _isCreating ? null : _createKey,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF8B5CF6),
                        disabledBackgroundColor: const Color(0xFF8B5CF6).withOpacity(0.5),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                        elevation: 0,
                      ),
                      child: _isCreating
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(
                                strokeWidth: 2.5,
                                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              ),
                            )
                          : const Text(
                              'Create Key',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                    ),
                  ),
                ),
                SizedBox(height: MediaQuery.of(context).padding.bottom),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
