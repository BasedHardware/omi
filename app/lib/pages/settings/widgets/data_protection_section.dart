import 'package:flutter/material.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';

// Re-defining enum and extension here to keep this widget self-contained.
enum DataProtectionLevel { standard, enhanced, e2ee }

extension StringExtension on String {
  String capitalize() {
    if (isEmpty) {
      return this;
    }
    return "${this[0].toUpperCase()}${substring(1)}";
  }
}

class DataProtectionSection extends StatelessWidget {
  const DataProtectionSection({super.key});

  DataProtectionLevel _levelFromString(String level) {
    switch (level) {
      case 'enhanced':
        return DataProtectionLevel.enhanced;
      case 'e2ee':
        return DataProtectionLevel.e2ee;
      case 'standard':
      default:
        return DataProtectionLevel.standard;
    }
  }

  String _levelToString(DataProtectionLevel level) {
    return level.toString().split('.').last;
  }

  void _onLevelChanged(BuildContext context, DataProtectionLevel? value) {
    final provider = Provider.of<UserProvider>(context, listen: false);
    if (value == null || _levelFromString(provider.dataProtectionLevel) == value || provider.isMigrating) return;

    showDialog(
      context: context,
      builder: (ctx) => getDialog(
        context,
        () => Navigator.of(ctx).pop(),
        () async {
          Navigator.of(ctx).pop();
          try {
            await provider.updateDataProtectionLevel(_levelToString(value));
          } catch (e) {
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Failed to start migration: $e')),
              );
            }
          }
        },
        "Confirm Change",
        "This will migrate all your existing data to the new protection level. This may take a few minutes. Are you sure you want to continue?",
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UserProvider>(
      builder: (context, provider, child) {
        final isMigrating = provider.isMigrating;
        final selectedLevel = _levelFromString(provider.dataProtectionLevel);

        final options = {
          DataProtectionLevel.standard: {
            'title': 'Level 1: Standard',
            'subtitle':
                'Your data is encrypted on our secure cloud. To improve Omi, authorized personnel may access data for support and diagnostics. We never use it for training.',
          },
          DataProtectionLevel.enhanced: {
            'title': 'Level 2: Enhanced',
            'subtitle':
                'Your data is encrypted with a key unique to you. This prevents Omi staff from accessing your conversation content. We never use it for training.',
          },
          DataProtectionLevel.e2ee: {
            'title': 'Level 3: Maximum (E2EE)',
            'subtitle':
                'End-to-end encrypted. Only you can access your data. Some features like app integrations are disabled, and data is unrecoverable if you lose access.',
          },
        };

        final selectedOptionData = options[selectedLevel]!;

        final allOptionsWidgets = DataProtectionLevel.values.map((level) {
          if (level == DataProtectionLevel.enhanced) {
            return _EnhancedProtectionOption(
              enabled: !isMigrating,
              currentLevel: selectedLevel,
              onChanged: (l) => _onLevelChanged(context, l),
              title: options[level]!['title'] as String,
              subtitle: options[level]!['subtitle'] as String,
            );
          }
          return _buildOption(
            context: context,
            level: level,
            title: options[level]!['title'] as String,
            subtitle: options[level]!['subtitle'] as String,
            currentLevel: selectedLevel,
            enabled: level == DataProtectionLevel.e2ee ? false : !isMigrating,
          );
        }).toList();

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (isMigrating)
              Container(
                padding: const EdgeInsets.all(16),
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: Colors.grey.shade800.withOpacity(0.5),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    RichText(
                      text: TextSpan(
                        style: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
                        children: [
                          const TextSpan(text: 'Migrating from '),
                          TextSpan(
                            text: provider.sourceLevel.capitalize(),
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          const TextSpan(text: ' to '),
                          TextSpan(
                            text: provider.targetLevel.capitalize(),
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          child: LinearProgressIndicator(
                            value: provider.migrationTotalCount > 0
                                ? provider.migrationProcessedCount / provider.migrationTotalCount
                                : 0.0,
                            backgroundColor: Colors.grey.shade700,
                            color: Colors.deepPurple,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Text(
                          provider.migrationTotalCount > 0
                              ? '${(provider.migrationProcessedCount / provider.migrationTotalCount * 100).toInt()}%'
                              : '0%',
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          provider.migrationETA,
                          style: const TextStyle(color: Colors.grey, fontSize: 12),
                        ),
                        Text(
                          '${provider.migrationProcessedCount} / ${provider.migrationTotalCount} objects',
                          style: const TextStyle(color: Colors.grey, fontSize: 12),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1A),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.grey.shade700, width: 1),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(10.5),
                child: ExpansionTile(
                  iconColor: Colors.white,
                  collapsedIconColor: Colors.white,
                  backgroundColor: const Color(0xFF1A1A1A),
                  collapsedBackgroundColor: const Color(0xFF1A1A1A),
                  title: Text(
                    selectedOptionData['title'] as String,
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  children: allOptionsWidgets,
                ),
              ),
            ),
            const SizedBox(height: 12),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 0.0),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.shield_outlined, color: Colors.grey, size: 16),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      selectedOptionData['subtitle'] as String,
                      style: const TextStyle(color: Colors.grey, fontSize: 14),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 0.0),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.lock_outline, color: Colors.grey, size: 16),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Regardless of the level, your data is always encrypted at rest and in transit.',
                      style: TextStyle(color: Colors.grey, fontSize: 14),
                    ),
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildOption({
    required BuildContext context,
    required DataProtectionLevel level,
    required String title,
    required String subtitle,
    required DataProtectionLevel currentLevel,
    bool enabled = true,
  }) {
    final bool isSelected = currentLevel == level;
    return Opacity(
      opacity: enabled ? 1.0 : 0.5,
      child: Container(
        color: isSelected ? Colors.deepPurple.withOpacity(0.2) : Colors.transparent,
        child: RadioListTile<DataProtectionLevel>(
          value: level,
          groupValue: currentLevel,
          onChanged: enabled ? (value) => _onLevelChanged(context, value) : null,
          title: Row(
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              if (!enabled && level != DataProtectionLevel.e2ee)
                const Padding(
                  padding: EdgeInsets.only(left: 8.0),
                  child: Text(
                    '(Migrating...)',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey,
                    ),
                  ),
                ),
              if (!enabled && level == DataProtectionLevel.e2ee)
                const Padding(
                  padding: EdgeInsets.only(left: 8.0),
                  child: Text(
                    '(Coming Soon)',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey,
                    ),
                  ),
                ),
            ],
          ),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 4.0),
            child: Text(
              subtitle,
              style: const TextStyle(color: Colors.grey),
            ),
          ),
          activeColor: Colors.white,
          controlAffinity: ListTileControlAffinity.trailing,
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        ),
      ),
    );
  }
}

class _EnhancedProtectionOption extends StatefulWidget {
  final bool enabled;
  final DataProtectionLevel currentLevel;
  final Function(DataProtectionLevel?) onChanged;
  final String title;
  final String subtitle;

  const _EnhancedProtectionOption(
      {required this.enabled,
      required this.currentLevel,
      required this.onChanged,
      required this.title,
      required this.subtitle});

  @override
  State<_EnhancedProtectionOption> createState() => _EnhancedProtectionOptionState();
}

class _EnhancedProtectionOptionState extends State<_EnhancedProtectionOption> {
  int? _migrationCount;
  bool _isLoadingCount = false;

  @override
  void initState() {
    super.initState();
    _fetchMigrationCount();
  }

  void _fetchMigrationCount() {
    if (mounted) {
      setState(() => _isLoadingCount = true);
      context.read<UserProvider>().getMigrationCountFor('enhanced').then((count) {
        if (mounted) {
          setState(() {
            _migrationCount = count;
            _isLoadingCount = false;
          });
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isSelected = widget.currentLevel == DataProtectionLevel.enhanced;

    Widget? additionalInfoWidget;
    if (widget.currentLevel == DataProtectionLevel.standard) {
      if (_isLoadingCount) {
        additionalInfoWidget = const Text(
          'Checking for data to protect...',
          style: TextStyle(color: Colors.grey, fontStyle: FontStyle.italic),
        );
      } else if (_migrationCount != null && _migrationCount! > 0) {
        additionalInfoWidget = Text(
          'This will encrypt all $_migrationCount of your conversations and memories.',
          style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.bold),
        );
      }
    }

    return Opacity(
      opacity: widget.enabled ? 1.0 : 0.5,
      child: Container(
        color: isSelected ? Colors.deepPurple.withOpacity(0.2) : Colors.transparent,
        child: RadioListTile<DataProtectionLevel>(
          value: DataProtectionLevel.enhanced,
          groupValue: widget.currentLevel,
          onChanged: widget.enabled ? (value) => widget.onChanged(value) : null,
          title: Row(
            children: [
              Text(
                widget.title,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
            ],
          ),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 4.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.subtitle,
                  style: const TextStyle(color: Colors.grey),
                ),
                if (additionalInfoWidget != null) ...[
                  const SizedBox(height: 8),
                  additionalInfoWidget,
                ],
              ],
            ),
          ),
          activeColor: Colors.white,
          controlAffinity: ListTileControlAffinity.trailing,
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        ),
      ),
    );
  }
}
