import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/integrations/connection_wait.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/settings/asana_settings_page.dart';
import 'package:omi/pages/settings/clickup_settings_page.dart';
import 'package:omi/pages/settings/google_tasks_settings_page.dart';
import 'package:omi/pages/settings/integration_selection_card.dart';
import 'package:omi/pages/settings/todoist_settings_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/integrations/apple_reminders_service.dart';
import 'package:omi/services/integrations/asana_service.dart';
import 'package:omi/services/integrations/clickup_service.dart';
import 'package:omi/services/integrations/google_tasks_service.dart';
import 'package:omi/services/integrations/todoist_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

enum TaskIntegrationApp { appleReminders, todoist, clickup, asana, googleTasks, trello, monday }

extension TaskIntegrationAppExtension on TaskIntegrationApp {
  String get displayName {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return 'Apple Reminders';
      case TaskIntegrationApp.googleTasks:
        return 'Google Tasks';
      case TaskIntegrationApp.clickup:
        return 'ClickUp';
      case TaskIntegrationApp.asana:
        return 'Asana';
      case TaskIntegrationApp.trello:
        return 'Trello';
      case TaskIntegrationApp.todoist:
        return 'Todoist';
      case TaskIntegrationApp.monday:
        return 'Monday';
    }
  }

  String get key {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return 'apple_reminders';
      case TaskIntegrationApp.googleTasks:
        return 'google_tasks';
      case TaskIntegrationApp.clickup:
        return 'clickup';
      case TaskIntegrationApp.asana:
        return 'asana';
      case TaskIntegrationApp.trello:
        return 'trello';
      case TaskIntegrationApp.todoist:
        return 'todoist';
      case TaskIntegrationApp.monday:
        return 'monday';
    }
  }

  String? get logoPath {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return Assets.images.appleRemindersLogo.path;
      case TaskIntegrationApp.googleTasks:
        return Assets.integrationAppLogos.googleTasksLogo.path;
      case TaskIntegrationApp.clickup:
        return Assets.integrationAppLogos.clickupLogo.path;
      case TaskIntegrationApp.asana:
        return Assets.integrationAppLogos.asanaLogo.path;
      case TaskIntegrationApp.trello:
        return Assets.integrationAppLogos.trelloLogo.path;
      case TaskIntegrationApp.todoist:
        return Assets.integrationAppLogos.todoistLogo.path;
      case TaskIntegrationApp.monday:
        return Assets.integrationAppLogos.mondayLogo.path;
    }
  }

  FaIconData get icon {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return FontAwesomeIcons.listCheck;
      case TaskIntegrationApp.googleTasks:
        return FontAwesomeIcons.circleCheck;
      case TaskIntegrationApp.clickup:
        return FontAwesomeIcons.rocket;
      case TaskIntegrationApp.asana:
        return FontAwesomeIcons.chartLine;
      case TaskIntegrationApp.trello:
        return FontAwesomeIcons.tableColumns;
      case TaskIntegrationApp.todoist:
        return FontAwesomeIcons.circleCheck;
      case TaskIntegrationApp.monday:
        return FontAwesomeIcons.calendarDay;
    }
  }

  Color get iconColor {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return const Color(0xFF007AFF); // omi-ux-allow: color-literal -- third-party brand colour
      case TaskIntegrationApp.googleTasks:
        return const Color(0xFF4285F4); // omi-ux-allow: color-literal -- third-party brand colour
      case TaskIntegrationApp.clickup:
        return const Color(0xFF7B68EE); // omi-ux-allow: color-literal -- third-party brand colour
      case TaskIntegrationApp.asana:
        return const Color(0xFFF06A6A); // omi-ux-allow: color-literal -- third-party brand colour
      case TaskIntegrationApp.trello:
        return const Color(0xFF0079BF); // omi-ux-allow: color-literal -- third-party brand colour
      case TaskIntegrationApp.todoist:
        return const Color(0xFFE44332); // omi-ux-allow: color-literal -- third-party brand colour
      case TaskIntegrationApp.monday:
        return const Color(0xFFFF3D57); // omi-ux-allow: color-literal -- third-party brand colour
    }
  }

  bool get isAvailable {
    // Apple Reminders, Todoist, Asana, and ClickUp are available
    return this == TaskIntegrationApp.appleReminders ||
        this == TaskIntegrationApp.todoist ||
        this == TaskIntegrationApp.asana ||
        this == TaskIntegrationApp.googleTasks ||
        this == TaskIntegrationApp.clickup;
  }
}

class TaskIntegrationsPage extends StatefulWidget {
  const TaskIntegrationsPage({super.key, this.authenticate});

  final Future<bool> Function(TaskIntegrationApp app)? authenticate;

  @override
  State<TaskIntegrationsPage> createState() => _TaskIntegrationsPageState();
}

class _TaskIntegrationsPageState extends State<TaskIntegrationsPage> with WidgetsBindingObserver {
  TaskIntegrationApp? _pendingAuthApp;
  bool _selectingPending = false;
  ConnectionWait? _connectionWait;

  /// Each selection owns everything it starts: the confirmation dialog, the
  /// browser launch, polling and the default save. A newer selection, a
  /// departed page or an account change retires it, so a late result from an
  /// older attempt can never select an app the user has moved on from.
  int _selectionAttempt = 0;

  bool Function() _ownSelection({bool claim = false}) {
    final attempt = claim ? ++_selectionAttempt : _selectionAttempt;
    final uid = SharedPreferencesUtil().uid;
    return () => mounted && _selectionAttempt == attempt && SharedPreferencesUtil().uid == uid;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Schedule loading for after the first frame to avoid setState during build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadFromBackend();
    });
  }

  @override
  void dispose() {
    _connectionWait?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Refresh when app comes back from background (e.g., after OAuth)
      if (_connectionWait?.isActive == true) {
        _connectionWait!.refresh();
      } else {
        _loadFromBackend(forceRefresh: true);
      }
    }
  }

  Future<void> _loadFromBackend({bool forceRefresh = false}) async {
    if (!mounted) return;
    final provider = context.read<TaskIntegrationProvider>();
    await provider.loadFromBackend(forceRefresh: forceRefresh);
  }

  void _waitForTaskConnection(TaskIntegrationApp pending, bool Function() isCurrent) {
    if (_selectingPending) return;
    _connectionWait?.cancel();
    final provider = context.read<TaskIntegrationProvider>();
    late final ConnectionWait wait;
    wait = ConnectionWait(
      isCurrent: () => isCurrent() && _pendingAuthApp == pending,
      // A probe is one provider status read; it must outlive that read's own budget.
      probeTimeout: provider.statusTimeout + const Duration(seconds: 5),
      probe: () async {
        await provider.loadFromBackend(forceRefresh: true, silent: true);
        if (provider.hasLoadError) return ConnectionProbe.failed;
        if (provider.isLoading) return ConnectionProbe.pending;
        return provider.isAppConnected(pending) ? ConnectionProbe.connected : ConnectionProbe.pending;
      },
    );
    _connectionWait = wait;
    unawaited(wait.start().then((outcome) async {
      if (!mounted || !isCurrent() || !identical(_connectionWait, wait)) return;
      if (outcome == ConnectionWaitOutcome.connected) {
        setState(() => _selectingPending = true);
        final bool selected;
        try {
          selected = await provider.setSelectedApp(pending);
        } finally {
          if (mounted) setState(() => _selectingPending = false);
        }
        if (!mounted || !isCurrent() || !identical(_connectionWait, wait)) return;
        if (selected) {
          setState(() => _pendingAuthApp = null);
          OmiFeedback.confirm(context, context.l10n.connectedToApp(pending.displayName));
        } else {
          OmiFeedback.error(context, context.l10n.connectionErrorDesc);
        }
      } else if (outcome != ConnectionWaitOutcome.cancelled) {
        OmiFeedback.error(context, context.l10n.connectionErrorDesc);
      }
    }));
  }

  bool _shouldShowSettingsIcon() {
    final selected = context.read<TaskIntegrationProvider>().selectedApp;
    final hasSettings = (selected == TaskIntegrationApp.asana && AsanaService().isAuthenticated) ||
        (selected == TaskIntegrationApp.clickup && ClickUpService().isAuthenticated) ||
        (selected == TaskIntegrationApp.todoist && TodoistService().isAuthenticated) ||
        (selected == TaskIntegrationApp.googleTasks && GoogleTasksService().isAuthenticated);
    return hasSettings;
  }

  void _openSelectedAppSettings() {
    final selected = context.read<TaskIntegrationProvider>().selectedApp;
    if (selected == TaskIntegrationApp.asana && AsanaService().isAuthenticated) {
      PlatformManager.instance.analytics.taskIntegrationSettingsOpened(appName: 'asana');
      routeToPage(context, const AsanaSettingsPage());
    } else if (selected == TaskIntegrationApp.clickup && ClickUpService().isAuthenticated) {
      PlatformManager.instance.analytics.taskIntegrationSettingsOpened(appName: 'clickup');
      routeToPage(context, const ClickUpSettingsPage());
    } else if (selected == TaskIntegrationApp.todoist && TodoistService().isAuthenticated) {
      PlatformManager.instance.analytics.taskIntegrationSettingsOpened(appName: 'todoist');
      routeToPage(context, const TodoistSettingsPage());
    } else if (selected == TaskIntegrationApp.googleTasks && GoogleTasksService().isAuthenticated) {
      PlatformManager.instance.analytics.taskIntegrationSettingsOpened(appName: 'google_tasks');
      routeToPage(context, const GoogleTasksSettingsPage());
    }
  }

  Future<void> _selectApp(TaskIntegrationApp app) async {
    if (_selectingPending) return;
    if (!app.isAvailable) {
      _showComingSoonDialog(app);
      return;
    }
    final isCurrent = _ownSelection(claim: true);
    if (_pendingAuthApp != null && _pendingAuthApp != app) {
      _connectionWait?.cancel();
      _connectionWait = null;
      setState(() => _pendingAuthApp = null);
    }

    // Check if Apple Reminders requires permission
    if (app == TaskIntegrationApp.appleReminders) {
      final provider = context.read<TaskIntegrationProvider>();
      final remindersService = AppleRemindersService();
      final hasPermission = await remindersService.hasPermission();
      if (!mounted || !isCurrent()) return;
      if (!hasPermission) {
        final granted = await remindersService.requestPermission();
        if (!mounted || !isCurrent()) return;
        if (granted) {
          // Update the provider's cached permission status with the granted result
          await provider.updateAppleRemindersPermission(granted: true);
          // Save connected status to backend so auto-sync works
          await provider.saveConnectionDetails(app.key, {'connected': true});
          if (!mounted || !isCurrent()) return;
          await provider.setSelectedApp(app);
          PlatformManager.instance.analytics.taskIntegrationEnabled(appName: app.key, success: true);
          Logger.debug('✓ Task integration enabled: ${app.displayName} (${app.key})');
        } else {
          if (mounted) {
            OmiFeedback.error(
              context,
              context.l10n.enableRemindersAccess,
              actionLabel: context.l10n.openSettings,
              onAction: () => unawaited(openAppSettings()),
            );
          }
        }
        return;
      }
      // Permission already granted - ensure backend knows it's connected
      await provider.saveConnectionDetails(app.key, {'connected': true});
      if (!mounted || !isCurrent()) return;
      await provider.setSelectedApp(app);
      return;
    }

    final (authenticated, authenticate) = switch (app) {
      TaskIntegrationApp.todoist => (TodoistService().isAuthenticated, TodoistService().authenticate),
      TaskIntegrationApp.asana => (AsanaService().isAuthenticated, AsanaService().authenticate),
      TaskIntegrationApp.googleTasks => (GoogleTasksService().isAuthenticated, GoogleTasksService().authenticate),
      TaskIntegrationApp.clickup => (ClickUpService().isAuthenticated, ClickUpService().authenticate),
      _ => (false, ({bool Function()? isCurrent}) async => false),
    };
    if (!authenticated) {
      if (!await _showAuthDialog(app) || !mounted || !isCurrent()) return;
      bool started;
      try {
        started = await (widget.authenticate?.call(app) ?? authenticate(isCurrent: isCurrent));
      } catch (e) {
        Logger.debug('Task integration authorization failed to start: $e');
        started = false;
      }
      if (!mounted || !isCurrent()) return;
      if (started) {
        setState(() => _pendingAuthApp = app);
        OmiFeedback.info(context, context.l10n.completeAuthBrowser);
        _waitForTaskConnection(app, isCurrent);
      } else {
        PlatformManager.instance.analytics.taskIntegrationAuthFailed(appName: app.key);
        OmiFeedback.error(context, context.l10n.failedToStartAppAuth(app.displayName));
      }
      return;
    }

    // Save to backend via provider
    final saved = await context.read<TaskIntegrationProvider>().setSelectedApp(app);
    if (!mounted || !isCurrent()) return;
    if (!saved) OmiFeedback.error(context, context.l10n.connectionErrorDesc);

    // Log app selection
    if (saved) Logger.debug('✓ Task integration selected: ${app.displayName} (${app.key})');
  }

  Future<bool> _showAuthDialog(TaskIntegrationApp app) {
    return showOmiConfirm(
      context,
      title: context.l10n.connectToAppTitle(app.displayName),
      message: context.l10n.authorizeOmiForTasks(app.displayName),
      confirmLabel: context.l10n.continueButton,
    );
  }

  void _showComingSoonDialog(TaskIntegrationApp app) {
    showOmiAlert(
      context,
      title: context.l10n.appIntegration(app.displayName),
      message: context.l10n.integrationComingSoon(app.displayName),
      okLabel: context.l10n.gotIt,
    );
  }

  bool _isAppConnected(TaskIntegrationApp app) {
    // Use provider to get connection status so it updates reactively
    return context.read<TaskIntegrationProvider>().isAppConnected(app);
  }

  String _getHeroTag(TaskIntegrationApp app) {
    // Return Hero tag for apps shown in the banner
    switch (app) {
      case TaskIntegrationApp.todoist:
        return 'task_integration_todoist_icon';
      case TaskIntegrationApp.clickup:
        return 'task_integration_clickup_icon';
      case TaskIntegrationApp.asana:
        return 'task_integration_asana_icon';
      default:
        // Unique tag for apps not in banner
        return 'task_integration_${app.key}_icon';
    }
  }

  Widget _buildShimmerButton() {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface2,
      highlightColor: OmiColors.surface3,
      child: Container(
        width: 70,
        height: 28,
        decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
      ),
    );
  }

  Widget _buildAppTile(TaskIntegrationApp app, bool isLoading) {
    final isSelected = context.read<TaskIntegrationProvider>().selectedApp == app;
    final isAvailable = app.isAvailable;
    final isConnected = _isAppConnected(app);
    final statusError =
        app != TaskIntegrationApp.appleReminders && context.read<TaskIntegrationProvider>().hasLoadError;

    final VoidCallback? onTap = isAvailable && !isLoading
        ? () {
            if (statusError) {
              _loadFromBackend(forceRefresh: true);
              return;
            }
            // If already connected and selected, open settings
            if (isConnected && isSelected) {
              if (app == TaskIntegrationApp.asana) {
                routeToPage(context, const AsanaSettingsPage());
              } else if (app == TaskIntegrationApp.clickup) {
                routeToPage(context, const ClickUpSettingsPage());
              } else if (app == TaskIntegrationApp.todoist) {
                routeToPage(context, const TodoistSettingsPage());
              } else if (app == TaskIntegrationApp.googleTasks) {
                routeToPage(context, const GoogleTasksSettingsPage());
              }
            } else {
              _selectApp(app);
            }
          }
        : null;

    final Widget trailing;
    if (!isAvailable) {
      trailing = IntegrationStatusChip(context.l10n.comingSoon, tone: IntegrationChipTone.muted);
    } else if (isLoading && app != TaskIntegrationApp.appleReminders) {
      trailing = _buildShimmerButton();
    } else if (statusError) {
      trailing = IntegrationStatusChip(context.l10n.tryAgain, tone: IntegrationChipTone.muted);
    } else if (!isConnected) {
      trailing = IntegrationStatusChip(context.l10n.connect);
    } else if (isSelected) {
      // Radio mark for connected services
      trailing = FaIcon(FontAwesomeIcons.solidCircleCheck, color: OmiColors.success, size: 24);
    } else {
      trailing = Container(
        width: 24,
        height: 24,
        decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: OmiColors.border, width: 2)),
      );
    }

    return MergeSemantics(
      child: Semantics(
        button: true,
        selected: isConnected ? isSelected : null,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
            child: Row(
              children: [
                // App Icon (with Hero animation for banner icons)
                ExcludeSemantics(
                  child: Hero(
                    tag: _getHeroTag(app),
                    child: SizedBox(
                      width: 40,
                      height: 40,
                      child: app.logoPath != null
                          ? ClipRRect(
                              borderRadius: OmiRadius.smAll,
                              child: Image.asset(app.logoPath!, width: 40, height: 40, fit: BoxFit.contain),
                            )
                          : Container(
                              decoration: BoxDecoration(
                                color: isAvailable ? app.iconColor.withValues(alpha: 0.2) : OmiColors.surface2,
                                borderRadius: OmiRadius.smAll,
                              ),
                              child: FaIcon(
                                app.icon,
                                color: isAvailable ? app.iconColor : OmiColors.textTertiary,
                                size: 24,
                              ),
                            ),
                    ),
                  ),
                ),
                const SizedBox(width: OmiSpacing.md),
                Expanded(
                  child: Text(
                    app.displayName,
                    style: OmiType.body.copyWith(color: isAvailable ? OmiColors.textPrimary : OmiColors.textTertiary),
                  ),
                ),
                trailing,
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Watch provider to rebuild when it changes
    final provider = context.watch<TaskIntegrationProvider>();
    final isLoading = provider.isLoading || !provider.hasLoaded || _selectingPending;

    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.taskIntegrations),
        actions: [
          // Settings icon for apps that have configuration options
          if (_shouldShowSettingsIcon())
            OmiIconButton(
              icon: const Icon(Icons.settings),
              label: context.l10n.configureSettings,
              onPressed: _openSelectedAppSettings,
            ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (provider.hasLoadError)
                Semantics(liveRegion: true, child: Text(context.l10n.connectionErrorDesc, style: OmiType.subhead)),
              if (_pendingAuthApp != null) ...[
                Text(
                    _selectingPending
                        ? context.l10n.saving
                        : !provider.hasLoadError && provider.isAppConnected(_pendingAuthApp!)
                            ? context.l10n.connectedToApp(_pendingAuthApp!.displayName)
                            : context.l10n.completeAuthBrowser,
                    style: OmiType.subhead),
                TextButton(
                    onPressed: isLoading ? null : () => _waitForTaskConnection(_pendingAuthApp!, _ownSelection()),
                    child: Text(context.l10n.tryAgain)),
              ],
              // App List
              Expanded(
                child: ListView(
                  children: TaskIntegrationApp.values
                      .where((app) {
                        // Hide Apple Reminders on Android
                        if (app == TaskIntegrationApp.appleReminders && !PlatformService.isApple) {
                          return false;
                        }
                        return true;
                      })
                      .map((app) => _buildAppTile(app, isLoading))
                      .toList(),
                ),
              ),
              const SizedBox(height: OmiSpacing.md),

              // Footer Note
              Container(
                padding: const EdgeInsets.all(OmiSpacing.md),
                decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
                child: Row(
                  children: [
                    FaIcon(FontAwesomeIcons.solidLightbulb, color: OmiColors.textTertiary, size: 20),
                    const SizedBox(width: OmiSpacing.sm),
                    Expanded(
                      child: Text(
                        context.l10n.tasksExportedOneApp,
                        style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
