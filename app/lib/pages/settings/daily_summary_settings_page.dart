import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

class DailySummarySettingsPage extends StatefulWidget {
  const DailySummarySettingsPage({super.key});

  @override
  State<DailySummarySettingsPage> createState() => _DailySummarySettingsPageState();
}

class _DailySummarySettingsPageState extends State<DailySummarySettingsPage> {
  bool _isLoading = true;
  bool _enabled = true;
  int _selectedHour = 22; // Default to 10 PM

  @override
  void initState() {
    super.initState();
    _loadSettings();
    MixpanelManager().dailySummarySettingsOpened();
  }

  Future<void> _loadSettings() async {
    final settings = await getDailySummarySettings();
    if (settings != null && mounted) {
      setState(() {
        _enabled = settings.enabled;
        _selectedHour = settings.hour;
        _isLoading = false;
      });
    } else if (mounted) {
      setState(() {
        _isLoading = false;
      });
    }
  }

  String _formatHourDisplay(int hour) {
    final hour12 = hour == 0 ? 12 : (hour > 12 ? hour - 12 : hour);
    final period = hour >= 12 ? 'PM' : 'AM';
    return '$hour12:00 $period';
  }

  Future<void> _updateEnabled(bool value) async {
    setState(() => _enabled = value);
    await setDailySummarySettings(enabled: value);
    MixpanelManager().dailySummaryToggled(enabled: value);
  }

  Future<void> _updateHour(int hour) async {
    setState(() => _selectedHour = hour);
    await setDailySummarySettings(hour: hour);
    MixpanelManager().dailySummaryTimeChanged(hour: hour);
  }

  Future<void> _showHourPicker() async {
    if (!_enabled) return;

    await showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        int tempHour = _selectedHour;
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Container(
              height: 350,
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: Text(
                          'Cancel',
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 16),
                        ),
                      ),
                      const Text(
                        'Select Time',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 17,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      TextButton(
                        onPressed: () {
                          _updateHour(tempHour);
                          Navigator.pop(context);
                        },
                        child: const Text(
                          'Done',
                          style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Expanded(
                    child: CupertinoTheme(
                      data: const CupertinoThemeData(
                        brightness: Brightness.dark,
                      ),
                      child: CupertinoPicker(
                        scrollController: FixedExtentScrollController(initialItem: tempHour),
                        itemExtent: 44,
                        onSelectedItemChanged: (index) {
                          setModalState(() => tempHour = index);
                        },
                        children: List.generate(24, (index) {
                          final hour12 = index == 0 ? 12 : (index > 12 ? index - 12 : index);
                          final period = index >= 12 ? 'PM' : 'AM';
                          return Center(
                            child: Text(
                              '$hour12:00 $period',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 20,
                              ),
                            ),
                          );
                        }),
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _showGenerateSummaryPicker() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: now.subtract(const Duration(days: 365)),
      lastDate: now,
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.dark(
              primary: Color(0xFF6366F1),
              onPrimary: Colors.white,
              surface: Color(0xFF1C1C1E),
              onSurface: Colors.white,
            ),
            dialogBackgroundColor: const Color(0xFF1C1C1E),
          ),
          child: child!,
        );
      },
    );

    if (picked != null && mounted) {
      final dateStr =
          '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';

      // Show loading
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => const Center(
          child: CircularProgressIndicator(color: Colors.white),
        ),
      );

      final summaryId = await generateDailySummary(date: dateStr);

      if (!mounted) return;
      Navigator.pop(context); // Dismiss loading

      if (summaryId != null) {
        MixpanelManager().dailySummaryTestGenerated(date: dateStr);

        // Refresh the hasDailySummaries flag so the Recap tab shows
        Provider.of<ConversationProvider>(context, listen: false).checkHasDailySummaries();

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Summary generated for ${picked.month}/${picked.day}/${picked.year}'),
            backgroundColor: Colors.green.shade700,
          ),
        );
      } else {
        MixpanelManager().dailySummaryTestGenerationFailed(date: dateStr);

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Failed to generate summary. Make sure you have conversations for that day.'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Daily Summary'),
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        actions: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert, color: Colors.white),
            color: const Color(0xFF1C1C1E),
            onSelected: (value) {
              if (value == 'generate') {
                _showGenerateSummaryPicker();
              }
            },
            itemBuilder: (context) => [
              const PopupMenuItem(
                value: 'generate',
                child: Row(
                  children: [
                    Icon(Icons.auto_awesome, color: Colors.white, size: 20),
                    SizedBox(width: 12),
                    Text('Generate Summary', style: TextStyle(color: Colors.white)),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: Colors.white))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Description
                  Padding(
                    padding: const EdgeInsets.only(bottom: 20),
                    child: Text(
                      'Get a personalized summary of your day\'s conversations delivered as a notification.',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 14,
                        height: 1.5,
                      ),
                    ),
                  ),
                  // Combined settings card
                  _buildSettingsCard(),
                ],
              ),
            ),
    );
  }

  Widget _buildSettingsCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          // Enable toggle row
          _buildSettingRow(
            icon: FontAwesomeIcons.bell,
            title: 'Daily Summary',
            trailing: Switch(
              value: _enabled,
              onChanged: _updateEnabled,
              activeColor: const Color(0xFF6366F1),
            ),
          ),

          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Divider(color: Colors.grey.shade800, height: 1),
          ),

          // Time selector row
          AnimatedOpacity(
            opacity: _enabled ? 1.0 : 0.4,
            duration: const Duration(milliseconds: 200),
            child: GestureDetector(
              onTap: _showHourPicker,
              behavior: HitTestBehavior.opaque,
              child: _buildSettingRow(
                icon: FontAwesomeIcons.clock,
                title: 'Delivery Time',
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      _formatHourDisplay(_selectedHour),
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Icon(
                      Icons.chevron_right,
                      color: Colors.grey.shade600,
                      size: 20,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSettingRow({
    required IconData icon,
    required String title,
    required Widget trailing,
  }) {
    return Row(
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: const Color(0xFF2A2A2E),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Center(child: FaIcon(icon, color: Colors.grey.shade400, size: 16)),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        trailing,
      ],
    );
  }
}
