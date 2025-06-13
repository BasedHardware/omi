import 'package:flutter/material.dart';
import 'package:omi/providers/user_provider.dart';
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

class DataProtectionSection extends StatefulWidget {
  const DataProtectionSection({super.key});

  @override
  State<DataProtectionSection> createState() => _DataProtectionSectionState();
}

class _DataProtectionSectionState extends State<DataProtectionSection> {
  int? _migrationCount;
  bool _isLoadingCount = false;
  bool _isExpanded = false;

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

  void _onLevelChanged(BuildContext context, DataProtectionLevel value) {
    final provider = Provider.of<UserProvider>(context, listen: false);
    if (_levelFromString(provider.dataProtectionLevel) == value || provider.isMigrating) return;

    if (value == DataProtectionLevel.e2ee) {
      _showComingSoonDialog(context);
    } else {
      _showMigrationConfirmationDialog(context, value);
    }
  }

  void _showComingSoonDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF2c2c2e),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: const Row(
          children: [
            Icon(Icons.timelapse_outlined, color: Colors.white),
            SizedBox(width: 10),
            Text('Coming Soon', style: TextStyle(color: Colors.white)),
          ],
        ),
        content: Text(
          'Maximum (E2EE) protection is not yet available, but we are working hard to bring it to you soon. Stay tuned!',
          style: TextStyle(color: Colors.white.withOpacity(0.8), height: 1.5, fontSize: 15),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('OK', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  void _showMigrationConfirmationDialog(BuildContext context, DataProtectionLevel value) {
    final provider = Provider.of<UserProvider>(context, listen: false);
    final targetLevelStr = _levelToString(value);

    Future<int> getCount() {
      // If migrating to 'enhanced' and we already have the count, use it.
      if (value == DataProtectionLevel.enhanced && _migrationCount != null) {
        return Future.value(_migrationCount);
      }
      // Otherwise, fetch it. This covers migrating to 'standard' or if _migrationCount is null.
      return context.read<UserProvider>().getMigrationCountFor(targetLevelStr);
    }

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF2c2c2e), // Dark, slightly transparent
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: const Row(
          children: [
            Icon(Icons.shield_moon_outlined, color: Colors.white),
            SizedBox(width: 10),
            Text('Confirm Migration', style: TextStyle(color: Colors.white)),
          ],
        ),
        content: FutureBuilder<int>(
          future: getCount(),
          builder: (context, snapshot) {
            Widget content;
            if (snapshot.connectionState == ConnectionState.waiting) {
              content = SizedBox(
                height: 80,
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const CircularProgressIndicator(),
                      const SizedBox(height: 16),
                      Text('Estimating time...', style: TextStyle(color: Colors.white70)),
                    ],
                  ),
                ),
              );
            } else if (snapshot.hasError) {
              content = RichText(
                text: TextSpan(
                  style: TextStyle(color: Colors.white.withOpacity(0.8), height: 1.5, fontSize: 15),
                  children: const [
                    TextSpan(text: 'Could not estimate migration time. '),
                    TextSpan(text: 'This action cannot be undone.\n\nAre you sure you want to continue?'),
                  ],
                ),
              );
            } else {
              final migrationCount = snapshot.data ?? 0;
              String estimatedTimeMessage;
              if (migrationCount == 0) {
                estimatedTimeMessage = 'This should be quick.';
              } else {
                final minutesDouble = migrationCount / 100.0; // 10 minutes per 1000 objects
                if (minutesDouble < 1) {
                  estimatedTimeMessage = 'This process should take less than a minute.';
                } else {
                  final minutes = minutesDouble.ceil();
                  if (minutes == 1) {
                    estimatedTimeMessage = 'This process will take about 1 minute.';
                  } else {
                    estimatedTimeMessage = 'This process will take about $minutes minutes.';
                  }
                }
              }

              content = RichText(
                text: TextSpan(
                  style: TextStyle(color: Colors.white.withOpacity(0.8), height: 1.5, fontSize: 15),
                  children: [
                    const TextSpan(text: 'This will migrate your data to the '),
                    TextSpan(
                      text: '${_levelToString(value).capitalize()} Protection',
                      style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                    ),
                    const TextSpan(text: ' level. '),
                    TextSpan(text: '$estimatedTimeMessage This action cannot be undone.\n\nAre you sure you want to continue?'),
                  ],
                ),
              );
            }
            return content;
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.secondary, // deepPurple
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            onPressed: () async {
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
            child: const Text('Confirm & Migrate', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
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

        Widget? enhancedAdditionalInfo;
        if (selectedLevel == DataProtectionLevel.standard) {
          if (_isLoadingCount) {
            enhancedAdditionalInfo = const Row(
              children: [
                SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
                SizedBox(width: 10),
                Text(
                  'Checking for data to protect...',
                  style: TextStyle(color: Colors.grey, fontStyle: FontStyle.italic),
                ),
              ],
            );
          } else if (_migrationCount != null && _migrationCount! > 0) {
            enhancedAdditionalInfo = Text(
              'This will encrypt all $_migrationCount of your conversations, memories and chat messages.',
              style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.bold),
            );
          }
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (isMigrating) _buildMigrationStatus(provider),
            if (!_isExpanded)
              _buildOption(
                context: context,
                level: selectedLevel,
                title: options[selectedLevel]!['title'] as String,
                subtitle: options[selectedLevel]!['subtitle'] as String,
                currentLevel: selectedLevel,
                enabled: !isMigrating,
                onChanged: (l) {
                  setState(() => _isExpanded = true);
                },
                isCollapsedView: true,
              )
            else ...[
              if (isMigrating)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.only(bottom: 16, left: 8, right: 8),
                  child: Text(
                    'Migration in progress. You cannot change the protection level until it is complete.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.secondary.withOpacity(0.9),
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ),
              ...DataProtectionLevel.values.map((level) {
                bool isEnabled = !isMigrating;
                return _buildOption(
                  context: context,
                  level: level,
                  title: options[level]!['title'] as String,
                  subtitle: options[level]!['subtitle'] as String,
                  currentLevel: selectedLevel,
                  enabled: isEnabled,
                  onChanged: (l) => _onLevelChanged(context, l),
                  additionalInfo: level == DataProtectionLevel.enhanced ? enhancedAdditionalInfo : null,
                );
              }).toList(),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () => setState(() => _isExpanded = false),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text('Show less', style: TextStyle(color: Theme.of(context).colorScheme.secondary)),
                      const SizedBox(width: 4),
                      Icon(Icons.expand_less, color: Theme.of(context).colorScheme.secondary),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: 12),
            _buildInfoRow(
              Icons.lock_outline,
              'Regardless of the level, your data is always encrypted at rest and in transit.',
            ),
          ],
        );
      },
    );
  }

  Widget _buildMigrationStatus(UserProvider provider) {
    return Container(
      padding: const EdgeInsets.all(16),
      margin: const EdgeInsets.only(bottom: 24),
      decoration: BoxDecoration(
        color: Colors.grey.shade800.withOpacity(0.5),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.deepPurple.shade300),
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
                  minHeight: 6,
                  borderRadius: BorderRadius.circular(3),
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
    );
  }

  Widget _buildOption({
    required BuildContext context,
    required DataProtectionLevel level,
    required String title,
    required String subtitle,
    Widget? additionalInfo,
    required DataProtectionLevel currentLevel,
    bool enabled = true,
    required Function(DataProtectionLevel) onChanged,
    bool isCollapsedView = false,
  }) {
    final bool isSelected = currentLevel == level;
    return Opacity(
      opacity: enabled ? 1.0 : 0.5,
      child: GestureDetector(
        onTap: enabled || isCollapsedView ? () => onChanged(level) : null,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(
            color: isSelected && !isCollapsedView ? Colors.deepPurple.withOpacity(0.15) : const Color(0xFF1A1A1A),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isSelected && !isCollapsedView ? Theme.of(context).colorScheme.secondary : Colors.grey.shade800,
              width: isSelected && !isCollapsedView ? 1.5 : 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              title,
                              style: const TextStyle(
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                                fontSize: 16,
                              ),
                            ),
                            if (level == DataProtectionLevel.e2ee)
                              const Padding(
                                padding: EdgeInsets.only(left: 8.0),
                                child: Text(
                                  '(Coming Soon)',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Colors.grey,
                                    fontStyle: FontStyle.italic,
                                  ),
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          subtitle,
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
                        ),
                      ],
                    ),
                  ),
                  if (isCollapsedView)
                    Padding(
                      padding: const EdgeInsets.only(left: 16.0),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            'Change',
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.secondary,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(width: 4),
                          Icon(
                            Icons.expand_more,
                            color: Theme.of(context).colorScheme.secondary,
                          ),
                        ],
                      ),
                    )
                  else
                    SizedBox(
                      height: 24,
                      width: 24,
                      child: Radio<DataProtectionLevel>(
                        value: level,
                        groupValue: currentLevel,
                        onChanged: enabled ? (l) => onChanged(l!) : null,
                        activeColor: Theme.of(context).colorScheme.secondary,
                        fillColor: MaterialStateProperty.resolveWith<Color>((states) {
                          if (states.contains(MaterialState.selected)) {
                            return Theme.of(context).colorScheme.secondary;
                          }
                          return Colors.grey;
                        }),
                      ),
                    ),
                ],
              ),
              if (additionalInfo != null) ...[
                const Divider(height: 24, color: Colors.grey),
                additionalInfo,
              ]
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInfoRow(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4.0, vertical: 4.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: Colors.grey, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(color: Colors.grey, fontSize: 14, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
