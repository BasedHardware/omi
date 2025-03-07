import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
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
  bool _showNewKey = false;
  String? _newKeySecret;
  String? _newKeyId;
  String? _newKeyLabel;
  DateTime? _newKeyCreatedAt;

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
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _createApiKey() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final result = await Provider.of<AddAppProvider>(context, listen: false).createApiKey(widget.appId);
      setState(() {
        _showNewKey = true;
        _newKeySecret = result['secret'];
        _newKeyId = result['id'];
        _newKeyLabel = result['label'];
        _newKeyCreatedAt = DateTime.parse(result['created_at']);
      });
    } catch (e) {
      AppSnackbar.showSnackbarError('Failed to create API key: ${e.toString()}');
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _deleteApiKey(String keyId) async {
    setState(() {
      _isLoading = true;
    });

    try {
      await Provider.of<AddAppProvider>(context, listen: false).deleteApiKey(widget.appId, keyId);
      AppSnackbar.showSnackbarSuccess('API key revoked successfully');
    } catch (e) {
      AppSnackbar.showSnackbarError('Failed to revoke API key: ${e.toString()}');
    } finally {
      setState(() {
        _isLoading = false;
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
                Text(
                  'API Keys',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (!_isLoading && !_showNewKey)
                  ElevatedButton.icon(
                    onPressed: _createApiKey,
                    icon: const Icon(Icons.add, size: 16),
                    label: const Text('Create Key'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Theme.of(context).colorScheme.secondary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
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
          if (_showNewKey && _newKeySecret != null) _buildNewKeyDisplay(),
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

  Widget _buildNewKeyDisplay() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.amber.shade700, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.warning_amber_rounded, color: Colors.amber),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Save this API key now! You won\'t be able to see it again.',
                  style: TextStyle(
                    color: Colors.amber.shade300,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            'API Key:',
            style: Theme.of(context).textTheme.labelMedium,
          ),
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.primary,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _newKeySecret!,
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 14,
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.copy, size: 18),
                  onPressed: () => _copyToClipboard(_newKeySecret!),
                  tooltip: 'Copy to clipboard',
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Text(
                'Created: ${DateFormat('MMM d, yyyy HH:mm').format(_newKeyCreatedAt!)}',
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ],
          ),
          const SizedBox(height: 16),
          Center(
            child: ElevatedButton(
              onPressed: () {
                setState(() {
                  _showNewKey = false;
                  _newKeySecret = null;
                });
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.secondary,
              ),
              child: const Text('Done', style: TextStyle(color: Colors.white)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildKeysList(AddAppProvider provider) {
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: provider.apiKeys.length,
      separatorBuilder: (context, index) => Divider(height: 1, color: Theme.of(context).dividerColor),
      itemBuilder: (context, index) {
        final key = provider.apiKeys[index];
        return ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          title: Text(
            key['label'] ?? 'API Key',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          subtitle: Text(
            '${DateFormat('MMM d, yyyy HH:mm').format(DateTime.parse(key['created_at']))}',
            style: Theme.of(context).textTheme.labelMedium,
          ),
          trailing: IconButton(
            icon: const Icon(Icons.delete_outline, color: Colors.red),
            onPressed: () => _showDeleteConfirmation(key['id']),
            tooltip: 'Revoke key',
          ),
        );
      },
    );
  }

  void _showDeleteConfirmation(String keyId) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Theme.of(context).colorScheme.surface,
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
