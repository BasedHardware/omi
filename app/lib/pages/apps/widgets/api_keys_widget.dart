import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

class ApiKeysWidget extends StatefulWidget {
  final String appId;

  const ApiKeysWidget({
    Key? key,
    required this.appId,
  }) : super(key: key);

  @override
  State<ApiKeysWidget> createState() => _ApiKeysWidgetState();
}

class _ApiKeysWidgetState extends State<ApiKeysWidget> {
  bool _isLoading = false;
  bool _isCreatingKey = false;
  String? _deletingKeyId;
  AppApiKey? _newKey;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _loadApiKeys();
    });
    super.initState();
  }

  Future<void> _loadApiKeys() async {
    setState(() {
      _isLoading = true;
    });

    try {
      await Provider.of<AddAppProvider>(context, listen: false).loadApiKeys(widget.appId);
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _createApiKey() async {
    setState(() {
      _isCreatingKey = true;
    });

    try {
      final result = await Provider.of<AddAppProvider>(context, listen: false).createApiKey(widget.appId);
      setState(() {
        _newKey = result;
      });

      // Show the dialog with the new key
      if (mounted) {
        _showNewKeyDialog();
      }
    } catch (e) {
      AppSnackbar.showSnackbarError('Failed to create provider API key: ${e.toString()}');
    } finally {
      setState(() {
        _isCreatingKey = false;
      });
    }
  }

  void _showNewKeyDialog() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text('Create a Key', textAlign: TextAlign.center),
        content: _buildNewKeyContent(),
        contentPadding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
        actions: [
          Center(
            child: ElevatedButton(
              onPressed: () {
                Navigator.of(context).pop();
                setState(() {
                  _newKey = null;
                });
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.secondary,
                minimumSize: const Size(120, 40),
              ),
              child: const Text('Done', style: TextStyle(color: Colors.white)),
            ),
          ),
        ],
        actionsPadding: const EdgeInsets.fromLTRB(0, 0, 0, 16),
      ),
    );
  }

  Future<void> _deleteApiKey(String keyId) async {
    setState(() {
      _deletingKeyId = keyId;
    });

    try {
      await Provider.of<AddAppProvider>(context, listen: false).deleteApiKey(widget.appId, keyId);
      AppSnackbar.showSnackbarSuccess('API key revoked successfully');
    } catch (e) {
      AppSnackbar.showSnackbarError('Failed to revoke API key: ${e.toString()}');
    } finally {
      setState(() {
        _deletingKeyId = null;
      });
    }
  }

  void _copyToClipboard(String text) {
    Clipboard.setData(ClipboardData(text: text));
    AppSnackbar.showSnackbarSuccess('Copied to clipboard');
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<AddAppProvider>(context);

    return Container(
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(12.0),
      ),
      padding: const EdgeInsets.all(14.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 8.0, bottom: 12.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Text(
                      'API Keys',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(width: 8),
                    IconButton(
                      icon: Icon(
                        Icons.info_outline,
                        size: 20,
                        color: Colors.grey.shade400,
                      ),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                      onPressed: () {
                        showDialog(
                          context: context,
                          builder: (context) => AlertDialog(
                            backgroundColor: Colors.grey.shade900,
                            title: const Text('Omi API Keys'),
                            content: const Text(
                              'API Keys are used for authentication when your app communicates with the OMI server. They allow your application to create memories and access other OMI services securely.',
                            ),
                            actions: [
                              TextButton(
                                onPressed: () => Navigator.of(context).pop(),
                                style: TextButton.styleFrom(
                                  backgroundColor: Theme.of(context).colorScheme.secondary,
                                  foregroundColor: Colors.white,
                                ),
                                child: const Text(
                                  'Got it',
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                      tooltip: 'About Omi API Keys',
                    ),
                  ],
                ),
                ElevatedButton.icon(
                  onPressed: _isCreatingKey ? null : _createApiKey,
                  icon: _isCreatingKey
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Icon(Icons.add, size: 16),
                  label: Text(_isCreatingKey ? 'Creating...' : 'Create Key'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.secondary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    disabledBackgroundColor: Theme.of(context).colorScheme.secondary.withOpacity(0.7),
                    disabledForegroundColor: Colors.white.withOpacity(0.7),
                  ),
                ),
              ],
            ),
          ),
          if (_isLoading)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(16.0),
                child: CircularProgressIndicator(color: Colors.white),
              ),
            ),
          if (provider.apiKeys.isEmpty)
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Center(
                child: Text(
                  'No API keys yet. Create one to integrate with your app.',
                  style: Theme.of(context).textTheme.bodyMedium,
                  textAlign: TextAlign.center,
                ),
              ),
            )
          else
            _buildKeysList(provider),
        ],
      ),
    );
  }

  Widget _buildNewKeyContent() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Center(
          child: Text(
            'Your new key:',
            style: Theme.of(context).textTheme.labelLarge,
          ),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: Colors.grey.shade800,
            borderRadius: BorderRadius.circular(4),
          ),
          child: Row(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: Text(
                      _newKey!.secret!,
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 14,
                      ),
                    ),
                  ),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.copy, size: 18),
                onPressed: () => _copyToClipboard(_newKey!.secret!),
                tooltip: 'Copy to clipboard',
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        const Row(
          children: [
            Expanded(
              child: Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: 'Please copy it now and write it down somewhere safe. ',
                      style: TextStyle(color: Colors.white),
                    ),
                    TextSpan(
                      text: 'You will not be able to see it again.',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildKeysList(AddAppProvider provider) {
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: provider.apiKeys.length,
      separatorBuilder: (context, index) => SizedBox(height: 12),
      itemBuilder: (context, index) {
        final key = provider.apiKeys[index];
        return Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade800,
            borderRadius: BorderRadius.circular(10.0),
          ),
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
            title: Text(
              key.label,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            subtitle: Text(
              '${DateFormat('MMM d, yyyy HH:mm').format(key.createdAt)}',
              style: Theme.of(context).textTheme.labelMedium,
            ),
            trailing: SizedBox(
              width: 42,
              height: 42,
              child: _deletingKeyId == key.id
                  ? const Center(
                      child: SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          color: Colors.red,
                          strokeWidth: 2,
                        ),
                      ),
                    )
                  : IconButton(
                      icon: const Icon(
                        Icons.delete_outline,
                        color: Colors.red,
                      ),
                      onPressed: () => _showDeleteConfirmation(key.id),
                      tooltip: 'Revoke key',
                    ),
            ),
          ),
        );
      },
    );
  }

  void _showDeleteConfirmation(String keyId) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text('Revoke API Key?'),
        content: const Text(
          'This action cannot be undone. Any applications using this key will no longer be able to access the API.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text('Cancel', style: Theme.of(context).textTheme.bodyMedium),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              _deleteApiKey(keyId);
            },
            child: const Text('Revoke', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
  }
}
