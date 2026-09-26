import 'dart:async';

import 'package:flutter/material.dart';

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
  const TaskIntegrationsPage({super.key});

  @override
  State<TaskIntegrationsPage> createState() => _TaskIntegrationsPageState();
}

class _TaskIntegrationsPageState extends State<TaskIntegrationsPage> with WidgetsBindingObserver {
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
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Refresh when app comes back from background (e.g., after OAuth)
      _loadFromBackend();
    }
  }

  Future<void> _loadFromBackend() async {
    await context.read<TaskIntegrationProvider>().loadFromBackend();
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
    if (!app.isAvailable) {
      _showComingSoonDialog(app);
      return;
    }

    // Check if Apple Reminders requires permission
    if (app == TaskIntegrationApp.appleReminders) {
      final provider = context.read<TaskIntegrationProvider>();
      final remindersService = AppleRemindersService();
      final hasPermission = await remindersService.hasPermission();
      if (!hasPermission) {
        final granted = await remindersService.requestPermission();
        if (granted) {
          // Update the provider's cached permission status with the granted result
          await provider.updateAppleRemindersPermission(granted: true);
          // Save connected status to backend so auto-sync works
          await provider.saveConnectionDetails(app.key, {'connected': true});
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
      await provider.setSelectedApp(app);
      return;
    }

    // Check if Todoist requires authentication
    if (app == TaskIntegrationApp.todoist) {
      final todoistService = TodoistService();
      if (!todoistService.isAuthenticated) {
        final provider = context.read<TaskIntegrationProvider>();
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth) {
          final success = await todoistService.authenticate();
          if (success) {
            if (mounted) {
              OmiFeedback.info(context, context.l10n.completeAuthBrowser);
            }
            await provider.setSelectedApp(app);
            // Note: OAuth callback will save connection to Firebase
            // Provider will refresh when user returns to this page
            Logger.debug('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
            // Track authentication failure
            PlatformManager.instance.analytics.taskIntegrationAuthFailed(appName: 'todoist');

            if (mounted) {
              OmiFeedback.error(context, context.l10n.failedToStartAppAuth('Todoist'));
            }
          }
        }
        return;
      }
    }

    // Check if Asana requires authentication
    if (app == TaskIntegrationApp.asana) {
      final asanaService = AsanaService();
      if (!asanaService.isAuthenticated) {
        final provider = context.read<TaskIntegrationProvider>();
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth) {
          final success = await asanaService.authenticate();
          if (success) {
            if (mounted) {
              OmiFeedback.info(context, context.l10n.completeAuthBrowser);
            }
            await provider.setSelectedApp(app);
            Logger.debug('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
            // Track authentication failure
            PlatformManager.instance.analytics.taskIntegrationAuthFailed(appName: 'asana');

            if (mounted) {
              OmiFeedback.error(context, context.l10n.failedToStartAppAuth('Asana'));
            }
          }
        }
        return;
      }
    }

    // Check if Google Tasks requires authentication
    if (app == TaskIntegrationApp.googleTasks) {
      final googleTasksService = GoogleTasksService();
      if (!googleTasksService.isAuthenticated) {
        final provider = context.read<TaskIntegrationProvider>();
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth) {
          final success = await googleTasksService.authenticate();
          if (success) {
            if (mounted) {
              OmiFeedback.info(context, context.l10n.completeAuthBrowser);
            }
            await provider.setSelectedApp(app);
            Logger.debug('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
            // Track authentication failure
            PlatformManager.instance.analytics.taskIntegrationAuthFailed(appName: 'google_tasks');

            if (mounted) {
              OmiFeedback.error(context, context.l10n.failedToStartAppAuth('Google Tasks'));
            }
          }
        }
        return;
      }
    }

    // Check if ClickUp requires authentication
    if (app == TaskIntegrationApp.clickup) {
      final clickupService = ClickUpService();
      if (!clickupService.isAuthenticated) {
        final provider = context.read<TaskIntegrationProvider>();
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth) {
          final success = await clickupService.authenticate();
          if (success) {
            if (mounted) {
              OmiFeedback.info(context, context.l10n.completeAuthBrowser);
            }
            await provider.setSelectedApp(app);
            Logger.debug('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
            // Track authentication failure
            PlatformManager.instance.analytics.taskIntegrationAuthFailed(appName: 'clickup');

            if (mounted) {
              OmiFeedback.error(context, context.l10n.failedToStartAppAuth('ClickUp'));
            }
          }
        }
        return;
      }
    }

    // Save to backend via provider
    await context.read<TaskIntegrationProvider>().setSelectedApp(app);

    // Log app selection
    Logger.debug('✓ Task integration selected: ${app.displayName} (${app.key})');
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
        decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
      ),
    );
  }

  Widget _buildAppTile(TaskIntegrationApp app, bool isLoading) {
    final isSelected = context.read<TaskIntegrationProvider>().selectedApp == app;
    final isAvailable = app.isAvailable;
    final isConnected = _isAppConnected(app);

    final VoidCallback? onTap = isAvailable && !isLoading
        ? () {
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
    if (isLoading && app != TaskIntegrationApp.appleReminders) {
      // Shimmer while loading (except for Apple Reminders, which is always connected)
      trailing = _buildShimmerButton();
    } else if (!isAvailable) {
      trailing = IntegrationStatusChip(context.l10n.comingSoon, tone: IntegrationChipTone.muted);
    } else if (!isConnected) {
      trailing = IntegrationStatusChip(context.l10n.connect);
    } else if (isSelected) {
      // Radio mark for connected services
      trailing = const FaIcon(FontAwesomeIcons.solidCircleCheck, color: OmiColors.success, size: 24);
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
    final isLoading = provider.isLoading || !provider.hasLoaded;

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
                decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
                child: Row(
                  children: [
                    const FaIcon(FontAwesomeIcons.solidLightbulb, color: OmiColors.textTertiary, size: 20),
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
