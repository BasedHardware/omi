import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/desktop/pages/onboarding/desktop_onboarding_wrapper.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/providers/developer_mode_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/persona/persona_profile.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/conversation_display_settings.dart';
import 'package:omi/pages/settings/conversation_timeout_dialog.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/delete_account.dart';
import 'package:omi/pages/settings/import_history_page.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/calendar_provider.dart';
import 'package:omi/services/calendar_service.dart';
import 'package:intl/intl.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/pages/settings/widgets/developer_api_keys_section.dart';
import 'package:omi/pages/speech_profile/page.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/shortcut_service.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

enum SettingsSection {
  account,
  plansAndBilling,
  calendarIntegration,
  customVocabulary,
  dailySummary,
  shortcuts,
  developer,
  about,
}

class DesktopSettingsModal extends StatefulWidget {
  final SettingsSection initialSection;

  const DesktopSettingsModal({
    super.key,
    this.initialSection = SettingsSection.account,
  });

  static Future<void> show(BuildContext context, {SettingsSection initialSection = SettingsSection.account}) {
    return showGeneralDialog(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'Settings',
      barrierColor: Colors.black.withValues(alpha: 0.5),
      transitionDuration: const Duration(milliseconds: 200),
      pageBuilder: (context, animation, secondaryAnimation) {
        return DesktopSettingsModal(initialSection: initialSection);
      },
      transitionBuilder: (context, animation, secondaryAnimation, child) {
        return FadeTransition(
          opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
          child: ScaleTransition(
            scale: Tween<double>(begin: 0.95, end: 1.0).animate(
              CurvedAnimation(parent: animation, curve: Curves.easeOut),
            ),
            child: child,
          ),
        );
      },
    );
  }

  @override
  State<DesktopSettingsModal> createState() => _DesktopSettingsModalState();
}

class _DesktopSettingsModalState extends State<DesktopSettingsModal> {
  late SettingsSection _selectedSection;
  
  // Shortcuts state
  ShortcutInfo? _askAIShortcut;
  ShortcutInfo? _toggleControlBarShortcut;
  bool _shortcutsLoading = true;
  String? _recordingFor;

  // Calendar state
  bool _showMenuBarMeetings = true;
  bool _showEventsWithNoParticipants = false;

  // Custom vocabulary state
  final TextEditingController _vocabularyController = TextEditingController();
  final Set<String> _pendingDeletions = {};
  Timer? _deletionDebounceTimer;
  bool _isDeletingBatch = false;

  // Daily summary state
  bool _dailySummaryLoading = true;
  bool _dailySummaryEnabled = true;
  int _dailySummaryHour = 22;

  @override
  void initState() {
    super.initState();
    _selectedSection = widget.initialSection;
    _loadShortcuts();
    _loadCalendarSettings();
    _loadDailySummarySettings();
    
    // Initialize developer mode provider
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        context.read<DeveloperModeProvider>().initialize();
        context.read<McpProvider>().fetchKeys();
        _initCalendarProvider();
      }
    });
  }

  @override
  void dispose() {
    _vocabularyController.dispose();
    _deletionDebounceTimer?.cancel();
    super.dispose();
  }

  void _loadCalendarSettings() {
    _showMenuBarMeetings = SharedPreferencesUtil().showMeetingsInMenuBar;
    _showEventsWithNoParticipants = SharedPreferencesUtil().showEventsWithNoParticipants;
  }

  void _initCalendarProvider() {
    final provider = context.read<CalendarProvider>();
    if (provider.isAuthorized) {
      provider.fetchSystemCalendars();
    }
  }

  Future<void> _loadDailySummarySettings() async {
    final settings = await getDailySummarySettings();
    if (settings != null && mounted) {
      setState(() {
        _dailySummaryEnabled = settings.enabled;
        _dailySummaryHour = settings.hour;
        _dailySummaryLoading = false;
      });
    } else if (mounted) {
      setState(() => _dailySummaryLoading = false);
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

  Future<void> _showHourPicker() async {
    if (!_dailySummaryEnabled) return;

    int tempHour = _dailySummaryHour;
    await showDialog(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return AlertDialog(
              backgroundColor: ResponsiveHelper.backgroundSecondary,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
                side: BorderSide(color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5)),
              ),
              title: const Text(
                'Select Time',
                style: TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              content: SizedBox(
                width: 300,
                height: 250,
                child: ListView.builder(
                  itemCount: 24,
                  itemBuilder: (context, index) {
                    final hour12 = index == 0 ? 12 : (index > 12 ? index - 12 : index);
                    final period = index >= 12 ? 'PM' : 'AM';
                    final isSelected = tempHour == index;
                    return ListTile(
                      title: Text(
                        '$hour12:00 $period',
                        style: TextStyle(
                          color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textPrimary,
                          fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                        ),
                      ),
                      trailing: isSelected ? const Icon(Icons.check, color: ResponsiveHelper.purplePrimary) : null,
                      onTap: () {
                        setDialogState(() => tempHour = index);
                      },
                    );
                  },
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Cancel', style: TextStyle(color: ResponsiveHelper.textSecondary)),
                ),
                TextButton(
                  onPressed: () {
                    _updateDailySummaryHour(tempHour);
                    Navigator.pop(context);
                  },
                  child: const Text('Done', style: TextStyle(color: ResponsiveHelper.purplePrimary, fontWeight: FontWeight.w600)),
                ),
              ],
            );
          },
        );
      },
    );
  }

  // Vocabulary methods
  Future<void> _addVocabularyWord(UserProvider userProvider) async {
    final input = _vocabularyController.text;
    if (input.trim().isEmpty) return;

    final words = input.split(',').map((w) => w.trim()).where((w) => w.isNotEmpty).toList();
    if (words.isEmpty) return;

    _vocabularyController.clear();
    final success = await userProvider.addVocabularyWords(words);
    if (success && mounted) {
      context.read<CaptureProvider>().onTranscriptionSettingsChanged();
    }
  }

  void _queueWordDeletion(UserProvider userProvider, String word) {
    setState(() => _pendingDeletions.add(word));
    _deletionDebounceTimer?.cancel();
    _deletionDebounceTimer = Timer(const Duration(seconds: 1), () {
      _executeBatchDeletion(userProvider);
    });
  }

  Future<void> _executeBatchDeletion(UserProvider userProvider) async {
    if (_pendingDeletions.isEmpty) return;
    setState(() => _isDeletingBatch = true);

    final wordsToDelete = List<String>.from(_pendingDeletions);
    bool anySuccess = false;

    for (final word in wordsToDelete) {
      final success = await userProvider.removeVocabularyWord(word);
      if (success) anySuccess = true;
    }

    if (mounted) {
      setState(() {
        _pendingDeletions.clear();
        _isDeletingBatch = false;
      });
      if (anySuccess) {
        context.read<CaptureProvider>().onTranscriptionSettingsChanged();
      }
    }
  }
  
  Future<void> _loadShortcuts() async {
    if (!ShortcutService.isSupported) return;
    setState(() => _shortcutsLoading = true);
    try {
      final askAI = await ShortcutService.getAskAIShortcut();
      final toggleControlBar = await ShortcutService.getToggleControlBarShortcut();
      if (mounted) {
        setState(() {
          _askAIShortcut = askAI;
          _toggleControlBarShortcut = toggleControlBar;
          _shortcutsLoading = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _shortcutsLoading = false);
    }
  }
  
  void _startRecording(String id) {
    setState(() => _recordingFor = id);
  }

  Future<void> _saveShortcut(String shortcutId, int keyCode, int modifiers) async {
    bool success = false;
    if (shortcutId == 'askAI') {
      success = await ShortcutService.setAskAIShortcut(keyCode, modifiers);
    } else if (shortcutId == 'toggleControlBar') {
      success = await ShortcutService.setToggleControlBarShortcut(keyCode, modifiers);
    }
    setState(() => _recordingFor = null);
    if (success) {
      _loadShortcuts();
    }
  }

  Future<void> _resetShortcut(String shortcutId) async {
    bool success = false;
    if (shortcutId == 'askAI') {
      success = await ShortcutService.resetAskAIShortcut();
    } else if (shortcutId == 'toggleControlBar') {
      success = await ShortcutService.resetToggleControlBarShortcut();
    }
    if (success) {
      _loadShortcuts();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Material(
        color: Colors.transparent,
        child: Container(
          width: 900,
          height: 650,
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.4),
                blurRadius: 40,
                offset: const Offset(0, 15),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Row(
              children: [
                // Left navigation rail
                _buildNavigationRail(),

                // Right content area
                Expanded(
                  child: _buildContent(),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildNavigationRail() {
    return Container(
      width: 220,
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
        border: Border(
          right: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
            width: 1,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
            child: Text(
              'SETTINGS',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: ResponsiveHelper.textTertiary,
                letterSpacing: 0.5,
              ),
            ),
          ),

          // Navigation items
          _buildNavItem(
            icon: FontAwesomeIcons.user,
            label: 'Account',
            section: SettingsSection.account,
          ),
          _buildNavItem(
            icon: FontAwesomeIcons.creditCard,
            label: 'Plans & Billing',
            section: SettingsSection.plansAndBilling,
          ),
          _buildNavItem(
            icon: FontAwesomeIcons.calendar,
            label: 'Calendar Integration',
            section: SettingsSection.calendarIntegration,
          ),
          _buildNavItem(
            icon: FontAwesomeIcons.book,
            label: 'Custom Vocabulary',
            section: SettingsSection.customVocabulary,
          ),
          _buildNavItem(
            icon: FontAwesomeIcons.bell,
            label: 'Daily Summary',
            section: SettingsSection.dailySummary,
          ),
          if (ShortcutService.isSupported)
            _buildNavItem(
              icon: FontAwesomeIcons.keyboard,
              label: 'Keyboard Shortcuts',
              section: SettingsSection.shortcuts,
            ),
          _buildNavItem(
            icon: FontAwesomeIcons.code,
            label: 'Developer',
            section: SettingsSection.developer,
          ),
          _buildNavItem(
            icon: FontAwesomeIcons.circleInfo,
            label: 'About',
            section: SettingsSection.about,
          ),

          const Spacer(),
        ],
      ),
    );
  }

  Widget _buildNavItem({
    required IconData icon,
    required String label,
    required SettingsSection section,
  }) {
    final isSelected = _selectedSection == section;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => setState(() => _selectedSection = section),
          borderRadius: BorderRadius.circular(8),
          hoverColor: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: isSelected ? ResponsiveHelper.backgroundTertiary : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                Icon(
                  icon,
                  size: 14,
                  color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                ),
                const SizedBox(width: 10),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
                    color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildContent() {
    return Container(
      color: ResponsiveHelper.backgroundSecondary,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 24),

          // Content area
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
              child: _buildSectionContent(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionContent() {
    switch (_selectedSection) {
      case SettingsSection.account:
        return _buildAccountContent();
      case SettingsSection.plansAndBilling:
        return _buildPlansContent();
      case SettingsSection.calendarIntegration:
        return _buildCalendarIntegrationContent();
      case SettingsSection.customVocabulary:
        return _buildCustomVocabularyContent();
      case SettingsSection.dailySummary:
        return _buildDailySummaryContent();
      case SettingsSection.shortcuts:
        return _buildShortcutsContent();
      case SettingsSection.developer:
        return _buildDeveloperContent();
      case SettingsSection.about:
        return _buildAboutContent();
    }
  }

  Widget _buildAccountContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Your Information section
        _buildSettingsGroup(
          title: 'Your Information',
          children: [
            _buildSettingsRow(
              title: 'Name',
              subtitle: SharedPreferencesUtil().givenName.isEmpty ? 'Not set' : SharedPreferencesUtil().givenName,
              onTap: () async {
                MixpanelManager().pageOpened('Profile Change Name');
                await showDialog(
                  context: context,
                  builder: (BuildContext context) => const ChangeNameWidget(),
                ).whenComplete(() => setState(() {}));
              },
            ),
            _buildSettingsRow(
              title: 'Email',
              subtitle: SharedPreferencesUtil().email.isEmpty ? 'Not set' : SharedPreferencesUtil().email,
              onTap: () {},
              showChevron: false,
            ),
            Consumer<HomeProvider>(
              builder: (context, homeProvider, _) {
                final languageName = homeProvider.userPrimaryLanguage.isNotEmpty
                    ? homeProvider.availableLanguages.entries
                        .firstWhere(
                          (element) => element.value == homeProvider.userPrimaryLanguage,
                        )
                        .key
                    : 'Not set';

                return _buildSettingsRow(
                  title: 'Language',
                  subtitle: languageName,
                  onTap: () async {
                    MixpanelManager().pageOpened('Profile Change Language');
                    await LanguageSelectionDialog.show(context, isRequired: false, forceShow: true);
                    await homeProvider.setupUserPrimaryLanguage();
                    setState(() {});
                  },
                );
              },
            ),
          ],
        ),

        const SizedBox(height: 24),

        // Voice & People section
        _buildSettingsGroup(
          title: 'Voice & People',
          children: [
            _buildSettingsRow(
              title: 'Speech Profile',
              onTap: () {
                Navigator.of(context).pop();
                routeToPage(context, const SpeechProfilePage());
                MixpanelManager().pageOpened('Profile Speech Profile');
              },
            ),
            _buildSettingsRow(
              title: 'Identifying Others',
              onTap: () {
                Navigator.of(context).pop();
                routeToPage(context, const UserPeoplePage());
              },
            ),
          ],
        ),

        const SizedBox(height: 24),

        // Payment & Display & Privacy section
        _buildSettingsGroup(
          title: 'Preferences',
          children: [
            _buildSettingsRow(
              title: 'Payment Methods',
              onTap: () {
                Navigator.of(context).pop();
                routeToPage(context, const PaymentsPage());
              },
            ),
            _buildSettingsRow(
              title: 'Conversation Display',
              onTap: () {
                Navigator.of(context).pop();
                routeToPage(context, const ConversationDisplaySettings());
              },
            ),
            _buildSettingsRow(
              title: 'Data Privacy',
              onTap: () {
                Navigator.of(context).pop();
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (context) => const DataPrivacyPage()),
                );
              },
            ),
          ],
        ),

        const SizedBox(height: 24),

        // Account section
        _buildSettingsGroup(
          title: 'Account',
          children: [
            Builder(
              builder: (context) {
                final uid = SharedPreferencesUtil().uid;
                final truncatedUid = uid.length > 6 ? '${uid.substring(0, 3)}•••••${uid.substring(uid.length - 3)}' : uid;
                return _buildSettingsRow(
                  title: 'User ID',
                  subtitle: truncatedUid,
                  onTap: () {
                    Clipboard.setData(ClipboardData(text: uid));
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: const Text('User ID copied to clipboard'),
                        backgroundColor: Colors.grey.shade800,
                        behavior: SnackBarBehavior.floating,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        duration: const Duration(seconds: 2),
                      ),
                    );
                  },
                );
              },
            ),
            _buildSettingsRow(
              title: 'Sign Out',
              onTap: _showSignOutDialog,
            ),
            _buildSettingsRow(
              title: 'Delete Account',
              isDestructive: true,
              onTap: () {
                Navigator.of(context).pop();
                MixpanelManager().pageOpened('Profile Delete Account Dialog');
                Navigator.push(context, MaterialPageRoute(builder: (context) => const DeleteAccount()));
              },
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildCustomVocabularyContent() {
    return Consumer<UserProvider>(
      builder: (context, userProvider, _) {
        final isDisabled = _isDeletingBatch || userProvider.isUpdatingVocabulary;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text(
                  'CUSTOM VOCABULARY',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: ResponsiveHelper.textTertiary,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '${userProvider.transcriptionVocabulary.length}',
                    style: const TextStyle(
                      color: ResponsiveHelper.textTertiary,
                      fontSize: 11,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                  width: 1,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Add words that Omi should recognize during transcription.',
                    style: TextStyle(
                      fontSize: 13,
                      color: ResponsiveHelper.textTertiary,
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Input field
                  Row(
                    children: [
                      Expanded(
                        child: Container(
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundSecondary,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: TextField(
                            controller: _vocabularyController,
                            enabled: !(userProvider.isUpdatingVocabulary && !_isDeletingBatch),
                            style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14),
                            decoration: InputDecoration(
                              hintText: 'Enter words (comma separated)',
                              hintStyle: TextStyle(color: ResponsiveHelper.textTertiary.withValues(alpha: 0.6), fontSize: 14),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                              border: InputBorder.none,
                            ),
                            onSubmitted: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                                ? null
                                : (_) => _addVocabularyWord(userProvider),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: userProvider.isUpdatingVocabulary ? null : () => _addVocabularyWord(userProvider),
                          borderRadius: BorderRadius.circular(10),
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                                  ? ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3)
                                  : ResponsiveHelper.purplePrimary,
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: userProvider.isUpdatingVocabulary && !_isDeletingBatch
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: ResponsiveHelper.textTertiary),
                                  )
                                : const Icon(FontAwesomeIcons.plus, color: Colors.white, size: 14),
                          ),
                        ),
                      ),
                    ],
                  ),

                  // Word chips
                  if (userProvider.transcriptionVocabulary.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    Container(
                      height: 1,
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                    ),
                    const SizedBox(height: 16),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: userProvider.transcriptionVocabulary.map((word) {
                        final isPendingDelete = _pendingDeletions.contains(word);
                        return Container(
                          padding: const EdgeInsets.only(left: 12, right: 6, top: 6, bottom: 6),
                          decoration: BoxDecoration(
                            color: isPendingDelete
                                ? ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.2)
                                : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                            borderRadius: BorderRadius.circular(100),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                word,
                                style: TextStyle(
                                  color: isPendingDelete ? ResponsiveHelper.textTertiary : ResponsiveHelper.textPrimary,
                                  fontSize: 13,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                              const SizedBox(width: 6),
                              if (isPendingDelete)
                                const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: ResponsiveHelper.textTertiary),
                                )
                              else
                                GestureDetector(
                                  onTap: isDisabled ? null : () => _queueWordDeletion(userProvider, word),
                                  child: Container(
                                    padding: const EdgeInsets.all(4),
                                    decoration: BoxDecoration(
                                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                                      shape: BoxShape.circle,
                                    ),
                                    child: Icon(
                                      Icons.close,
                                      color: isDisabled ? ResponsiveHelper.textTertiary : ResponsiveHelper.textSecondary,
                                      size: 10,
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        );
                      }).toList(),
                    ),
                  ],
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildDailySummaryContent() {
    if (_dailySummaryLoading) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'DAILY SUMMARY',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: ResponsiveHelper.textTertiary,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Center(
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2, color: ResponsiveHelper.purplePrimary),
              ),
            ),
          ),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'DAILY SUMMARY',
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w600,
            color: ResponsiveHelper.textTertiary,
            letterSpacing: 0.5,
          ),
        ),
        const SizedBox(height: 8),
        Container(
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
              width: 1,
            ),
          ),
          child: Column(
            children: [
              // Enable toggle
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Daily Summary',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w500,
                              color: ResponsiveHelper.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Get a personalized summary of your conversations',
                            style: TextStyle(
                              fontSize: 12,
                              color: ResponsiveHelper.textTertiary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    OmiCheckbox(
                      value: _dailySummaryEnabled,
                      onChanged: _updateDailySummaryEnabled,
                      size: 18,
                    ),
                  ],
                ),
              ),

              Container(
                height: 1,
                margin: const EdgeInsets.symmetric(horizontal: 16),
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
              ),

              // Time selector
              Opacity(
                opacity: _dailySummaryEnabled ? 1.0 : 0.4,
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: _showHourPicker,
                    borderRadius: BorderRadius.circular(10),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'Delivery Time',
                                  style: TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w500,
                                    color: ResponsiveHelper.textPrimary,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'When to receive your daily summary',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: ResponsiveHelper.textTertiary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Text(
                            _formatHourDisplay(_dailySummaryHour),
                            style: const TextStyle(
                              fontSize: 14,
                              color: ResponsiveHelper.textSecondary,
                            ),
                          ),
                          const SizedBox(width: 8),
                          const Icon(
                            FontAwesomeIcons.chevronRight,
                            size: 12,
                            color: ResponsiveHelper.textTertiary,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildPlansContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSettingsGroup(
          title: 'Subscription',
          children: [
            _buildSettingsRow(
              title: 'View Plans & Usage',
              subtitle: 'Manage your subscription and see usage stats',
              onTap: () {
                Navigator.of(context).pop();
                MixpanelManager().pageOpened('Plan & Usage');
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (context) => const UsagePage()),
                );
              },
            ),
            _buildSettingsRow(
              title: 'Payment Methods',
              subtitle: 'Add or change your payment method',
              onTap: () {
                Navigator.of(context).pop();
                routeToPage(context, const PaymentsPage());
              },
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildCalendarIntegrationContent() {
    return Consumer<CalendarProvider>(
      builder: (context, provider, _) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Calendar Providers Section
            _buildSettingsGroup(
              title: 'Calendar Providers',
              children: [
                _buildCalendarProviderRow(
                  icon: FontAwesomeIcons.calendar,
                  iconColor: const Color(0xFF5AC8FA),
                  title: 'macOS Calendar',
                  subtitle: 'Connect your macOS Calendar',
                  isEnabled: provider.isAuthorized && provider.isMonitoring,
                  onToggle: (value) async {
                    if (value) {
                      if (provider.isAuthorized) {
                        SharedPreferencesUtil().calendarIntegrationEnabled = true;
                        await provider.startMonitoring();
                      } else {
                        await provider.requestPermission();
                      }
                    } else {
                      await provider.stopMonitoring();
                    }
                  },
                ),
                _buildCalendarProviderRow(
                  icon: FontAwesomeIcons.google,
                  iconColor: const Color(0xFF4285F4),
                  title: 'Google Calendar',
                  subtitle: 'Sync your Google account',
                  isEnabled: false,
                  onToggle: (value) {
                    AppSnackbar.showSnackbar('Google Calendar integration coming soon!');
                  },
                ),
              ],
            ),

            const SizedBox(height: 24),

            // Settings Section
            _buildSettingsGroup(
              title: 'Display Options',
              children: [
                _buildCalendarToggleRow(
                  title: 'Show Meetings in Menu Bar',
                  subtitle: 'Display upcoming meetings in the menu bar',
                  value: _showMenuBarMeetings,
                  onChanged: (value) {
                    setState(() => _showMenuBarMeetings = value);
                    provider.updateShowMeetingsInMenuBar(value);
                  },
                ),
                _buildCalendarToggleRow(
                  title: 'Show Events Without Participants',
                  subtitle: 'Include personal events with no attendees',
                  value: _showEventsWithNoParticipants,
                  onChanged: (value) {
                    setState(() => _showEventsWithNoParticipants = value);
                    provider.updateShowEventsWithNoParticipants(value);
                  },
                ),
              ],
            ),

            // Upcoming Meetings Section
            if (provider.isAuthorized) ...[
              const SizedBox(height: 24),
              _buildUpcomingMeetingsSection(provider),
            ],
          ],
        );
      },
    );
  }

  Widget _buildCalendarProviderRow({
    required IconData icon,
    required Color iconColor,
    required String title,
    required String subtitle,
    required bool isEnabled,
    required ValueChanged<bool> onToggle,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: iconColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: iconColor, size: 16),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: ResponsiveHelper.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontSize: 12,
                    color: ResponsiveHelper.textTertiary,
                  ),
                ),
              ],
            ),
          ),
          OmiCheckbox(
            value: isEnabled,
            onChanged: onToggle,
            size: 18,
          ),
        ],
      ),
    );
  }

  Widget _buildCalendarToggleRow({
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: ResponsiveHelper.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontSize: 12,
                    color: ResponsiveHelper.textTertiary,
                  ),
                ),
              ],
            ),
          ),
          OmiCheckbox(
            value: value,
            onChanged: onChanged,
            size: 18,
          ),
        ],
      ),
    );
  }

  Widget _buildUpcomingMeetingsSection(CalendarProvider provider) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text(
              'UPCOMING MEETINGS',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: ResponsiveHelper.textTertiary,
                letterSpacing: 0.5,
              ),
            ),
            const Spacer(),
            if (provider.upcomingMeetings.isNotEmpty)
              TextButton(
                onPressed: () => provider.refreshMeetings(),
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: const Text(
                  'Refresh',
                  style: TextStyle(
                    color: ResponsiveHelper.purplePrimary,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 8),
        if (provider.upcomingMeetings.isEmpty)
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                width: 1,
              ),
            ),
            child: const Column(
              children: [
                Icon(
                  Icons.event_busy,
                  color: ResponsiveHelper.textTertiary,
                  size: 32,
                ),
                SizedBox(height: 12),
                Text(
                  'No upcoming meetings',
                  style: TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  'Checking the next 7 days',
                  style: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          )
        else
          _buildMeetingsList(provider),
      ],
    );
  }

  Widget _buildMeetingsList(CalendarProvider provider) {
    final sortedMeetings = List<CalendarMeeting>.from(provider.upcomingMeetings)
      ..sort((a, b) => a.startTime.compareTo(b.startTime));

    final groupedMeetings = <DateTime, List<CalendarMeeting>>{};
    for (final meeting in sortedMeetings) {
      final dateKey = DateTime(meeting.startTime.year, meeting.startTime.month, meeting.startTime.day);
      groupedMeetings.putIfAbsent(dateKey, () => []).add(meeting);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: groupedMeetings.entries.map((entry) {
        final date = entry.key;
        final meetings = entry.value;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 8, top: 8),
              child: Text(
                _formatMeetingDateHeader(date),
                style: const TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            Container(
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                  width: 1,
                ),
              ),
              child: Column(
                children: [
                  for (int i = 0; i < meetings.length; i++) ...[
                    _buildMeetingCard(meetings[i]),
                    if (i < meetings.length - 1)
                      Container(
                        height: 1,
                        margin: const EdgeInsets.symmetric(horizontal: 16),
                        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                      ),
                  ],
                ],
              ),
            ),
          ],
        );
      }).toList(),
    );
  }

  String _formatMeetingDateHeader(DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final tomorrow = today.add(const Duration(days: 1));

    if (date == today) {
      return 'Today';
    } else if (date == tomorrow) {
      return 'Tomorrow';
    } else {
      return DateFormat('EEEE, MMMM d').format(date);
    }
  }

  Widget _buildMeetingCard(CalendarMeeting meeting) {
    final dateFormat = DateFormat('h:mm a');
    final duration = meeting.endTime.difference(meeting.startTime);
    final durationString = '${duration.inMinutes} min';
    final platformColor = _getMeetingPlatformColor(meeting.platform);

    return Padding(
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 36,
            decoration: BoxDecoration(
              color: platformColor,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  meeting.title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Text(
                      '${dateFormat.format(meeting.startTime)} • $durationString',
                      style: const TextStyle(
                        color: ResponsiveHelper.textTertiary,
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: platformColor.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        meeting.platform,
                        style: TextStyle(
                          color: platformColor,
                          fontSize: 10,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Color _getMeetingPlatformColor(String platform) {
    switch (platform.toLowerCase()) {
      case 'zoom':
        return const Color(0xFF2D8CFF);
      case 'google meet':
        return const Color(0xFF00AC47);
      case 'teams':
        return const Color(0xFF6264A7);
      case 'slack':
        return const Color(0xFF4A154B);
      default:
        return ResponsiveHelper.purplePrimary;
    }
  }

  Widget _buildShortcutsContent() {
    if (_shortcutsLoading) {
      return const Center(
        child: CircularProgressIndicator(color: ResponsiveHelper.purplePrimary),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSettingsGroup(
          title: 'Shortcuts',
          children: [
            _buildShortcutRow(
              id: 'toggleControlBar',
              title: 'Toggle Control Bar',
              shortcut: _toggleControlBarShortcut?.displayString ?? '⌘\\',
              isRecording: _recordingFor == 'toggleControlBar',
              onTap: () => _startRecording('toggleControlBar'),
              onReset: () => _resetShortcut('toggleControlBar'),
            ),
            _buildShortcutRow(
              id: 'askAI',
              title: 'Ask Omi',
              shortcut: _askAIShortcut?.displayString ?? '⌘↩︎',
              isRecording: _recordingFor == 'askAI',
              onTap: () => _startRecording('askAI'),
              onReset: () => _resetShortcut('askAI'),
            ),
          ],
        ),
        
        const SizedBox(height: 16),
        
        const Text(
          'Click on a shortcut to change it. Press Escape to cancel.',
          style: TextStyle(
            fontSize: 12,
            color: ResponsiveHelper.textTertiary,
          ),
        ),
      ],
    );
  }

  Widget _buildShortcutRow({
    required String id,
    required String title,
    required String shortcut,
    bool isRecording = false,
    VoidCallback? onTap,
    VoidCallback? onReset,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          if (!isRecording)
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_horiz, color: ResponsiveHelper.textTertiary, size: 20),
              color: ResponsiveHelper.backgroundSecondary,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: BorderSide(color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5)),
              ),
              onSelected: (value) {
                if (value == 'reset') onReset?.call();
              },
              itemBuilder: (context) => [
                const PopupMenuItem(
                  value: 'reset',
                  child: Text('Reset to default', style: TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 13)),
                ),
              ],
            ),
          const SizedBox(width: 4),
          isRecording
              ? _ShortcutRecorderBadge(
                  onRecorded: (keyCode, modifiers) => _saveShortcut(id, keyCode, modifiers),
                  onCancel: () => setState(() => _recordingFor = null),
                )
              : GestureDetector(
                  onTap: onTap,
                  child: MouseRegion(
                    cursor: SystemMouseCursors.click,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.backgroundTertiary,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        shortcut,
                        style: const TextStyle(
                          color: ResponsiveHelper.textPrimary,
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          fontFamily: 'SF Mono',
                          letterSpacing: 0.5,
                        ),
                      ),
                    ),
                  ),
                ),
        ],
      ),
    );
  }

  Widget _buildDeveloperContent() {
    return Consumer2<DeveloperModeProvider, McpProvider>(
      builder: (context, devProvider, mcpProvider, _) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Configuration Section
            _buildSettingsGroup(
              title: 'Configuration',
              children: [
                _buildSettingsRow(
                  title: 'Persona',
                  subtitle: 'Configure your AI persona',
                  onTap: () {
                    Navigator.of(context).pop();
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (context) => const PersonaProfilePage(),
                        settings: const RouteSettings(arguments: 'from_settings'),
                      ),
                    );
                    MixpanelManager().pageOpened('Developer Persona Settings');
                  },
                ),
                _buildSettingsRow(
                  title: 'Transcription',
                  subtitle: 'Configure STT provider',
                  onTap: () {
                    Navigator.of(context).pop();
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (context) => const TranscriptionSettingsPage()),
                    );
                  },
                ),
                _buildSettingsRow(
                  title: 'Conversation Timeout',
                  subtitle: 'Set when conversations auto-end',
                  onTap: () {
                    ConversationTimeoutDialog.show(context);
                  },
                ),
                _buildSettingsRow(
                  title: 'Import Data',
                  subtitle: 'Import data from other sources',
                  onTap: () {
                    Navigator.of(context).pop();
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (context) => const ImportHistoryPage()),
                    );
                  },
                ),
              ],
            ),

            const SizedBox(height: 24),

            // Debug & Diagnostics Section
            _buildSettingsGroup(
              title: 'Debug & Diagnostics',
              children: [
                _buildToggleRow(
                  title: 'Debug Logs',
                  subtitle: SharedPreferencesUtil().devLogsToFileEnabled
                      ? 'Auto-deletes after 3 days'
                      : 'Helps diagnose issues',
                  value: SharedPreferencesUtil().devLogsToFileEnabled,
                  onChanged: (v) async {
                    await DebugLogManager.setEnabled(v);
                    setState(() {});
                  },
                ),
                if (SharedPreferencesUtil().devLogsToFileEnabled)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    child: Row(
                      children: [
                        Expanded(
                          child: ElevatedButton.icon(
                            onPressed: () async {
                              final files = await DebugLogManager.listLogFiles();
                              if (files.isEmpty) {
                                AppSnackbar.showSnackbarError('No log files found.');
                                return;
                              }
                              if (files.length == 1) {
                                await Share.shareXFiles([XFile(files.first.path)], text: 'Omi debug log');
                                return;
                              }
                              // Multiple files - share the first one for simplicity
                              await Share.shareXFiles([XFile(files.first.path)], text: 'Omi debug log');
                            },
                            icon: const Icon(Icons.upload_file, size: 16),
                            label: const Text('Share Logs'),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: ResponsiveHelper.backgroundTertiary,
                              foregroundColor: ResponsiveHelper.textPrimary,
                              padding: const EdgeInsets.symmetric(vertical: 10),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        ElevatedButton(
                          onPressed: () async {
                            await DebugLogManager.clear();
                            AppSnackbar.showSnackbar('Debug logs cleared');
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.red.withValues(alpha: 0.15),
                            foregroundColor: Colors.red.shade400,
                            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 16),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                          ),
                          child: const Text('Clear'),
                        ),
                      ],
                    ),
                  ),
                _buildSettingsRow(
                  title: 'Export All Data',
                  subtitle: 'Export conversations to JSON',
                  trailing: devProvider.loadingExportMemories
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2, color: ResponsiveHelper.purplePrimary),
                        )
                      : null,
                  onTap: devProvider.loadingExportMemories
                      ? null
                      : () async {
                          devProvider.loadingExportMemories = true;
                          setState(() {});

                          AppSnackbar.showSnackbar('Exporting conversations...');
                          List<ServerConversation> memories = await getConversations(limit: 10000, offset: 0);
                          String json = const JsonEncoder.withIndent("     ").convert(memories);
                          final directory = await getApplicationDocumentsDirectory();
                          final file = File('${directory.path}/conversations.json');
                          await file.writeAsString(json);

                          await Share.shareXFiles([XFile(file.path)], text: 'Exported Conversations from Omi');
                          MixpanelManager().exportMemories();
                          devProvider.loadingExportMemories = false;
                          setState(() {});
                        },
                ),
                _buildSettingsRow(
                  title: 'Delete Knowledge Graph',
                  subtitle: 'Clear all nodes and connections',
                  isDestructive: true,
                  onTap: () {
                    showDialog(
                      context: context,
                      builder: (ctx) => AlertDialog(
                        backgroundColor: ResponsiveHelper.backgroundSecondary,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: BorderSide(color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5)),
                        ),
                        title: const Text('Delete Knowledge Graph?', style: TextStyle(color: ResponsiveHelper.textPrimary)),
                        content: const Text(
                          'This will delete all derived knowledge graph data. Your original memories remain safe.',
                          style: TextStyle(color: ResponsiveHelper.textSecondary),
                        ),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.of(ctx).pop(),
                            child: const Text('Cancel', style: TextStyle(color: ResponsiveHelper.textTertiary)),
                          ),
                          TextButton(
                            onPressed: () async {
                              Navigator.of(ctx).pop();
                              try {
                                await KnowledgeGraphApi.deleteKnowledgeGraph();
                                AppSnackbar.showSnackbar('Knowledge Graph deleted');
                              } catch (e) {
                                AppSnackbar.showSnackbarError('Failed to delete: $e');
                              }
                            },
                            child: Text('Delete', style: TextStyle(color: Colors.red.shade400)),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ],
            ),

            const SizedBox(height: 24),

            // Developer API Keys Section
            _buildSettingsGroup(
              title: 'Developer API Keys',
              children: [
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: DeveloperApiKeysSection(),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // MCP Section
            _buildSettingsGroup(
              title: 'MCP',
              children: [
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Expanded(
                            child: Text(
                              'Connect Omi with AI assistants',
                              style: TextStyle(fontSize: 13, color: ResponsiveHelper.textSecondary),
                            ),
                          ),
                          TextButton(
                            onPressed: () => launchUrl(Uri.parse('https://docs.omi.me/doc/developer/MCP')),
                            child: const Text('Docs'),
                            style: TextButton.styleFrom(foregroundColor: ResponsiveHelper.purplePrimary),
                          ),
                          TextButton.icon(
                            onPressed: () => showDialog(
                              context: context,
                              builder: (context) => const CreateMcpApiKeyDialog(),
                            ),
                            icon: const Icon(Icons.add, size: 16),
                            label: const Text('Create Key'),
                            style: TextButton.styleFrom(
                              foregroundColor: ResponsiveHelper.purplePrimary,
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      // Server URL
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: ResponsiveHelper.backgroundPrimary,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5)),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                '${Env.apiBaseUrl}v1/mcp/sse',
                                style: const TextStyle(
                                  fontSize: 12,
                                  fontFamily: 'monospace',
                                  color: ResponsiveHelper.textSecondary,
                                ),
                              ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.copy, size: 16, color: ResponsiveHelper.textTertiary),
                              onPressed: () {
                                Clipboard.setData(ClipboardData(text: '${Env.apiBaseUrl}v1/mcp/sse'));
                                AppSnackbar.showSnackbar('URL copied');
                              },
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                      if (mcpProvider.isLoading && mcpProvider.keys.isEmpty)
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.all(16),
                            child: CircularProgressIndicator(strokeWidth: 2, color: ResponsiveHelper.purplePrimary),
                          ),
                        )
                      else if (mcpProvider.keys.isEmpty)
                        const Text(
                          'No API keys. Create one to get started.',
                          style: TextStyle(fontSize: 13, color: ResponsiveHelper.textTertiary),
                        )
                      else
                        ...mcpProvider.keys.map((key) => McpApiKeyListItem(apiKey: key)),
                    ],
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // Webhooks Section
            _buildSettingsGroup(
              title: 'Webhooks',
              children: [
                _buildToggleRow(
                  title: 'Conversation Events',
                  subtitle: 'New conversation created',
                  value: devProvider.conversationEventsToggled,
                  onChanged: devProvider.onConversationEventsToggled,
                ),
                if (devProvider.conversationEventsToggled)
                  _buildWebhookUrlField(devProvider.webhookOnConversationCreated),
                _buildToggleRow(
                  title: 'Real-time Transcript',
                  subtitle: 'Transcript received',
                  value: devProvider.transcriptsToggled,
                  onChanged: devProvider.onTranscriptsToggled,
                ),
                if (devProvider.transcriptsToggled)
                  _buildWebhookUrlField(devProvider.webhookOnTranscriptReceived),
                _buildToggleRow(
                  title: 'Audio Bytes',
                  subtitle: 'Audio data received',
                  value: devProvider.audioBytesToggled,
                  onChanged: devProvider.onAudioBytesToggled,
                ),
                if (devProvider.audioBytesToggled) ...[
                  _buildWebhookUrlField(devProvider.webhookAudioBytes),
                  _buildWebhookUrlField(devProvider.webhookAudioBytesDelay, label: 'Interval (seconds)'),
                ],
                _buildToggleRow(
                  title: 'Day Summary',
                  subtitle: 'Summary generated',
                  value: devProvider.daySummaryToggled,
                  onChanged: devProvider.onDaySummaryToggled,
                ),
                if (devProvider.daySummaryToggled)
                  _buildWebhookUrlField(devProvider.webhookDaySummary),
              ],
            ),

            const SizedBox(height: 24),

            // Experimental features
            _buildSettingsGroup(
              title: 'Experimental',
              children: [
                _buildToggleRow(
                  title: 'Transcription Diagnostics',
                  subtitle: 'Detailed diagnostic messages',
                  value: devProvider.transcriptionDiagnosticEnabled,
                  onChanged: (v) => devProvider.onTranscriptionDiagnosticChanged(v),
                ),
                _buildToggleRow(
                  title: 'Auto-create Speakers',
                  subtitle: 'Auto-create when name detected',
                  value: devProvider.autoCreateSpeakersEnabled,
                  onChanged: (v) => devProvider.onAutoCreateSpeakersChanged(v),
                ),
                _buildToggleRow(
                  title: 'Follow-up Questions',
                  subtitle: 'Suggest questions after conversations',
                  value: devProvider.followUpQuestionEnabled,
                  onChanged: (v) => devProvider.onFollowUpQuestionChanged(v),
                ),
                _buildToggleRow(
                  title: 'Goal Tracker',
                  subtitle: 'Track personal goals on homepage',
                  value: devProvider.showGoalTrackerEnabled,
                  onChanged: (v) => devProvider.onShowGoalTrackerChanged(v),
                ),
                _buildToggleRow(
                  title: 'Daily Reflection',
                  subtitle: '9 PM reminder to reflect on your day',
                  value: devProvider.dailyReflectionEnabled,
                  onChanged: (v) => devProvider.onDailyReflectionChanged(v),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // Save button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: devProvider.savingSettingsLoading ? null : devProvider.saveSettings,
                style: ElevatedButton.styleFrom(
                  backgroundColor: ResponsiveHelper.purplePrimary,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
                child: devProvider.savingSettingsLoading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Text('Save Settings', style: TextStyle(fontWeight: FontWeight.w600)),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildWebhookUrlField(TextEditingController controller, {String label = 'Endpoint URL'}) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Container(
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundPrimary,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5)),
        ),
        child: TextField(
          controller: controller,
          style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 13),
          decoration: InputDecoration(
            labelText: label,
            labelStyle: const TextStyle(color: ResponsiveHelper.textTertiary, fontSize: 12),
            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            border: InputBorder.none,
          ),
        ),
      ),
    );
  }

  Widget _buildAboutContent() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSettingsGroup(
          title: 'Links',
          children: [
            _buildSettingsRow(
              title: 'Privacy Policy',
              onTap: () {
                MixpanelManager().pageOpened('About Privacy Policy');
                launchUrl(Uri.parse('https://www.omi.me/pages/privacy'));
              },
            ),
            _buildSettingsRow(
              title: 'Visit Website',
              subtitle: 'https://omi.me',
              onTap: () {
                MixpanelManager().pageOpened('About Visit Website');
                launchUrl(Uri.parse('https://www.omi.me/'));
              },
            ),
            _buildSettingsRow(
              title: 'Help or Inquiries',
              subtitle: 'team@basedhardware.com',
              onTap: () async {
                final Uri emailUri = Uri(
                  scheme: 'mailto',
                  path: 'team@basedhardware.com',
                  query: 'subject=Omi Desktop App Inquiry',
                );
                if (await canLaunchUrl(emailUri)) {
                  await launchUrl(emailUri);
                }
              },
            ),
            _buildSettingsRow(
              title: 'Join the Community',
              subtitle: '8000+ members on Discord',
              onTap: () {
                MixpanelManager().pageOpened('About Join Discord');
                launchUrl(Uri.parse('http://discord.omi.me'));
              },
            ),
          ],
        ),

        const SizedBox(height: 24),

        // User ID section
        _buildSettingsGroup(
          title: 'User Information',
          children: [
            _buildSettingsRow(
              title: 'User ID',
              subtitle: SharedPreferencesUtil().uid,
              trailing: OmiIconButton(
                icon: FontAwesomeIcons.copy,
                style: OmiIconButtonStyle.neutral,
                size: 28,
                iconSize: 12,
                borderRadius: 6,
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: SharedPreferencesUtil().uid));
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: const Text('User ID copied to clipboard'),
                      backgroundColor: Colors.grey.shade800,
                      behavior: SnackBarBehavior.floating,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      duration: const Duration(seconds: 2),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildSettingsGroup({
    required String title,
    required List<Widget> children,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title.toUpperCase(),
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w600,
            color: ResponsiveHelper.textTertiary,
            letterSpacing: 0.5,
          ),
        ),
        const SizedBox(height: 8),
        Container(
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
              width: 1,
            ),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: Column(
              children: [
                for (int i = 0; i < children.length; i++) ...[
                  children[i],
                  if (i < children.length - 1)
                    Container(
                      height: 1,
                      margin: const EdgeInsets.symmetric(horizontal: 16),
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                    ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSettingsRow({
    required String title,
    String? subtitle,
    Widget? trailing,
    VoidCallback? onTap,
    bool isDestructive = false,
    bool showChevron = true,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        hoverColor: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: isDestructive ? Colors.red.shade400 : ResponsiveHelper.textPrimary,
                      ),
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: const TextStyle(
                          fontSize: 12,
                          color: ResponsiveHelper.textTertiary,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (trailing != null) trailing,
              if (onTap != null && trailing == null && showChevron)
                const Icon(
                  FontAwesomeIcons.chevronRight,
                  size: 12,
                  color: ResponsiveHelper.textTertiary,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildToggleRow({
    required String title,
    String? subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
    VoidCallback? onInfoTap,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              onTap: onInfoTap,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: ResponsiveHelper.textPrimary,
                      decoration: onInfoTap != null ? TextDecoration.underline : null,
                      decorationColor: ResponsiveHelper.textTertiary,
                    ),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: const TextStyle(
                        fontSize: 12,
                        color: ResponsiveHelper.textTertiary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          OmiCheckbox(
            value: value,
            onChanged: onChanged,
            size: 18,
          ),
        ],
      ),
    );
  }

  void _showSignOutDialog() {
    showDialog(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
            width: 1,
          ),
        ),
        title: const Text(
          'Sign Out?',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        content: const Text(
          'Are you sure you want to sign out?',
          style: TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 14,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text(
              'Cancel',
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
              ),
            ),
          ),
          TextButton(
            onPressed: () async {
              await SharedPreferencesUtil().clear();
              Navigator.of(dialogContext).pop();
              Navigator.of(context).pop(); // Close settings modal
              await AuthService.instance.signOut();
              if (mounted) {
                routeToPage(context, const DesktopOnboardingWrapper(), replace: true);
              }
            },
            child: Text(
              'Sign Out',
              style: TextStyle(
                color: Colors.red.shade400,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// Inline shortcut recorder badge
class _ShortcutRecorderBadge extends StatefulWidget {
  final void Function(int keyCode, int modifiers) onRecorded;
  final VoidCallback onCancel;

  const _ShortcutRecorderBadge({required this.onRecorded, required this.onCancel});

  @override
  State<_ShortcutRecorderBadge> createState() => _ShortcutRecorderBadgeState();
}

class _ShortcutRecorderBadgeState extends State<_ShortcutRecorderBadge> {
  final FocusNode _focusNode = FocusNode();
  String _displayText = 'Press keys...';
  int? _keyCode;
  int? _modifiers;
  bool _isValid = false;

  static const int cmdKey = 0x100;
  static const int shiftKey = 0x200;
  static const int optionKey = 0x800;
  static const int controlKey = 0x1000;

  static final Map<int, int> _physicalKeyToCarbonKeyCode = {
    0x04: 0, 0x05: 11, 0x06: 8, 0x07: 2, 0x08: 14, 0x09: 3, 0x0A: 5, 0x0B: 4,
    0x0C: 34, 0x0D: 38, 0x0E: 40, 0x0F: 37, 0x10: 46, 0x11: 45, 0x12: 31, 0x13: 35,
    0x14: 12, 0x15: 15, 0x16: 1, 0x17: 17, 0x18: 32, 0x19: 9, 0x1A: 13, 0x1B: 7,
    0x1C: 16, 0x1D: 6, 0x1E: 18, 0x1F: 19, 0x20: 20, 0x21: 21, 0x22: 23, 0x23: 22,
    0x24: 26, 0x25: 28, 0x26: 25, 0x27: 29, 0x28: 36, 0x2C: 49, 0x31: 42,
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _focusNode.requestFocus());
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  void _handleKeyEvent(KeyEvent event) {
    if (event is! KeyDownEvent) return;

    if (event.logicalKey == LogicalKeyboardKey.escape) {
      widget.onCancel();
      return;
    }

    if (_isModifierKey(event.logicalKey)) return;

    final isCommand = HardwareKeyboard.instance.isMetaPressed;
    if (!isCommand) {
      setState(() {
        _displayText = '⌘ required';
        _isValid = false;
      });
      return;
    }

    final isShift = HardwareKeyboard.instance.isShiftPressed;
    final isOption = HardwareKeyboard.instance.isAltPressed;
    final isControl = HardwareKeyboard.instance.isControlPressed;

    int modifiers = cmdKey;
    if (isShift) modifiers |= shiftKey;
    if (isOption) modifiers |= optionKey;
    if (isControl) modifiers |= controlKey;

    final usbHidUsage = event.physicalKey.usbHidUsage & 0xFF;
    final carbonKeyCode = _physicalKeyToCarbonKeyCode[usbHidUsage];

    if (carbonKeyCode == null) {
      setState(() {
        _displayText = 'Invalid key';
        _isValid = false;
      });
      return;
    }

    final parts = <String>[];
    if (isControl) parts.add('⌃');
    if (isOption) parts.add('⌥');
    if (isShift) parts.add('⇧');
    parts.add('⌘');
    parts.add(_getKeyName(event.logicalKey));

    setState(() {
      _keyCode = carbonKeyCode;
      _modifiers = modifiers;
      _displayText = parts.join();
      _isValid = true;
    });

    Future.delayed(const Duration(milliseconds: 300), () {
      if (_isValid && mounted) {
        widget.onRecorded(_keyCode!, _modifiers!);
      }
    });
  }

  bool _isModifierKey(LogicalKeyboardKey key) {
    return key == LogicalKeyboardKey.meta ||
        key == LogicalKeyboardKey.metaLeft ||
        key == LogicalKeyboardKey.metaRight ||
        key == LogicalKeyboardKey.shift ||
        key == LogicalKeyboardKey.shiftLeft ||
        key == LogicalKeyboardKey.shiftRight ||
        key == LogicalKeyboardKey.alt ||
        key == LogicalKeyboardKey.altLeft ||
        key == LogicalKeyboardKey.altRight ||
        key == LogicalKeyboardKey.control ||
        key == LogicalKeyboardKey.controlLeft ||
        key == LogicalKeyboardKey.controlRight;
  }

  String _getKeyName(LogicalKeyboardKey key) {
    if (key == LogicalKeyboardKey.enter || key == LogicalKeyboardKey.numpadEnter) return '↩︎';
    if (key == LogicalKeyboardKey.space) return 'Space';
    if (key == LogicalKeyboardKey.backslash) return '\\';
    final label = key.keyLabel;
    return label.length == 1 ? label.toUpperCase() : label;
  }

  @override
  Widget build(BuildContext context) {
    return KeyboardListener(
      focusNode: _focusNode,
      onKeyEvent: _handleKeyEvent,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: ResponsiveHelper.purplePrimary, width: 1.5),
        ),
        child: Text(
          _displayText,
          style: TextStyle(
            color: _isValid ? ResponsiveHelper.textPrimary : ResponsiveHelper.purplePrimary,
            fontSize: 13,
            fontWeight: FontWeight.w500,
            fontFamily: 'SF Mono',
            letterSpacing: 0.5,
          ),
        ),
      ),
    );
  }
}

