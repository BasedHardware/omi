import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/notifications/daily_reflection_notification.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

class NotificationsSettingsPage extends StatefulWidget {
  const NotificationsSettingsPage({super.key});

  @override
  State<NotificationsSettingsPage> createState() => _NotificationsSettingsPageState();
}

class _NotificationsSettingsPageState extends State<NotificationsSettingsPage> {
  bool _isLoading = true;
  
  // Notification frequency (0-5)
  int _notificationFrequency = 3;
  
  // Daily Summary settings
  bool _dailySummaryEnabled = true;
  int _dailySummaryHour = 22; // Default to 10 PM
  
  // Daily Reflection settings
  bool _dailyReflectionEnabled = true;

  @override
  void initState() {
    super.initState();
    _loadSettings();
    MixpanelManager().dailySummarySettingsOpened();
  }

  Future<void> _loadSettings() async {
    // Load Daily Summary settings from API
    final settings = await getDailySummarySettings();
    
    // Load settings from local prefs
    final reflectionEnabled = SharedPreferencesUtil().dailyReflectionEnabled;
    final frequency = SharedPreferencesUtil().notificationFrequency;
    
    if (mounted) {
      setState(() {
        if (settings != null) {
          _dailySummaryEnabled = settings.enabled;
          _dailySummaryHour = settings.hour;
        }
        _dailyReflectionEnabled = reflectionEnabled;
        _notificationFrequency = frequency;
        _isLoading = false;
      });
    }
  }

  void _updateNotificationFrequency(int value) {
    setState(() => _notificationFrequency = value);
    SharedPreferencesUtil().notificationFrequency = value;
  }

  String _getFrequencyLabel(int value) {
    switch (value) {
      case 0:
        return 'Off';
      case 1:
        return 'Minimal';
      case 2:
        return 'Low';
      case 3:
        return 'Balanced';
      case 4:
        return 'High';
      case 5:
        return 'Maximum';
      default:
        return 'Balanced';
    }
  }

  String _getFrequencyDescription(int value) {
    switch (value) {
      case 0:
        return 'No proactive notifications';
      case 1:
        return 'Only critical reminders';
      case 2:
        return 'Important updates only';
      case 3:
        return 'Regular helpful nudges';
      case 4:
        return 'Frequent check-ins';
      case 5:
        return 'Stay constantly engaged';
      default:
        return 'Regular helpful nudges';
    }
  }

  String _formatHourDisplay(int hour) {
    final hour12 = hour == 0 ? 12 : (hour > 12 ? hour - 12 : hour);
    final period = hour >= 12 ? 'PM' : 'AM';
    return '$hour12:00 $period';
  }

  Future<void> _updateDailySummaryEnabled(bool value) async {
    setState(() => _dailySummaryEnabled = value);
    await setDailySummarySettings(enabled: value);
    MixpanelManager().dailySummaryToggled(enabled: value);
  }

  Future<void> _updateDailySummaryHour(int hour) async {
    setState(() => _dailySummaryHour = hour);
    await setDailySummarySettings(hour: hour);
    MixpanelManager().dailySummaryTimeChanged(hour: hour);
  }

  void _updateDailyReflectionEnabled(bool value) {
    setState(() => _dailyReflectionEnabled = value);
    SharedPreferencesUtil().dailyReflectionEnabled = value;
    
    // Schedule or cancel the notification based on the setting
    if (value) {
      DailyReflectionNotification.scheduleDailyNotification(channelKey: 'channel');
    } else {
      DailyReflectionNotification.cancelNotification();
    }
  }

  Future<void> _showHourPicker() async {
    if (!_dailySummaryEnabled) return;

    await showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1C1C1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        int tempHour = _dailySummaryHour;
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
                          _updateDailySummaryHour(tempHour);
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
        title: const Text('Notifications'),
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
                  // Notification Frequency Section
                  _buildSectionHeader('Notification Frequency'),
                  const SizedBox(height: 8),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Text(
                      'Control how often Omi sends you proactive notifications and reminders.',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 14,
                        height: 1.5,
                      ),
                    ),
                  ),
                  _buildFrequencyCard(),
                  
                  const SizedBox(height: 32),
                  
                  // Daily Summary Section
                  _buildSectionHeader('Daily Summary'),
                  const SizedBox(height: 8),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Text(
                      'Get a personalized summary of your day\'s conversations delivered as a notification.',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 14,
                        height: 1.5,
                      ),
                    ),
                  ),
                  _buildDailySummaryCard(),
                  
                  const SizedBox(height: 32),
                  
                  // Daily Reflection Section
                  _buildSectionHeader('Daily Reflection'),
                  const SizedBox(height: 8),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Text(
                      'Get a reminder at 9 PM to reflect on your day and capture your thoughts.',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 14,
                        height: 1.5,
                      ),
                    ),
                  ),
                  _buildDailyReflectionCard(),
                ],
              ),
            ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Text(
      title,
      style: const TextStyle(
        color: Colors.white,
        fontSize: 20,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  Widget _buildFrequencyCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          // Current value display
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _getFrequencyLabel(_notificationFrequency),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _getFrequencyDescription(_notificationFrequency),
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: _notificationFrequency == 0 
                      ? Colors.grey.shade800 
                      : const Color(0xFF6366F1).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Center(
                  child: Text(
                    '$_notificationFrequency',
                    style: TextStyle(
                      color: _notificationFrequency == 0 
                          ? Colors.grey.shade500 
                          : const Color(0xFF6366F1),
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ],
          ),
          
          const SizedBox(height: 20),
          
          // Slider
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: const Color(0xFF6366F1),
              inactiveTrackColor: Colors.grey.shade800,
              thumbColor: Colors.white,
              overlayColor: const Color(0xFF6366F1).withOpacity(0.2),
              trackHeight: 6,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 10),
            ),
            child: Slider(
              value: _notificationFrequency.toDouble(),
              min: 0,
              max: 5,
              divisions: 5,
              onChanged: (value) => _updateNotificationFrequency(value.round()),
            ),
          ),
          
          // Labels
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Off',
                  style: TextStyle(
                    color: Colors.grey.shade500,
                    fontSize: 12,
                  ),
                ),
                Text(
                  'Max',
                  style: TextStyle(
                    color: Colors.grey.shade500,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDailySummaryCard() {
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
            title: 'Enable',
            trailing: Switch(
              value: _dailySummaryEnabled,
              onChanged: _updateDailySummaryEnabled,
              activeColor: const Color(0xFF6366F1),
            ),
          ),

          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Divider(color: Colors.grey.shade800, height: 1),
          ),

          // Time selector row
          AnimatedOpacity(
            opacity: _dailySummaryEnabled ? 1.0 : 0.4,
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
                      _formatHourDisplay(_dailySummaryHour),
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

  Widget _buildDailyReflectionCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: _buildSettingRow(
        icon: FontAwesomeIcons.moon,
        title: 'Enable',
        trailing: Switch(
          value: _dailyReflectionEnabled,
          onChanged: _updateDailyReflectionEnabled,
          activeColor: const Color(0xFF6366F1),
        ),
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
