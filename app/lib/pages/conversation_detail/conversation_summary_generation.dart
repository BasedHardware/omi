import 'package:flutter/foundation.dart';

import 'package:collection/collection.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/logger.dart';

/// Installed summary templates; throws when the list could not be read (never an empty list).
typedef EnabledSummaryAppsFetch = Future<List<App>> Function();

/// Templates suggested for one conversation; throws when the list could not be read.
typedef SuggestedSummaryAppsFetch = Future<List<App>> Function(String conversationId);

/// Saves [appId] as the server preferred template, or clears it (null: Omi's own summary).
/// Resolves false when the server did not store it.
typedef PreferredSummaryAppWrite = Future<bool> Function(String? appId);

/// Where a template list fetch stands. [failed] is distinct from an empty [loaded] list.
enum SummaryTemplatesLoad { idle, loading, loaded, failed }

/// Why the last summary request on a conversation produced no summary.
enum SummaryFailureKind {
  /// The chosen template ran but returned nothing (or the server would not run it).
  template,

  /// Another writer was already processing the conversation (HTTP 409).
  busy,

  /// The hourly regenerate limit (HTTP 429).
  rateLimited,

  /// Anything else.
  generic,
}

/// The last failed summary request, scoped to the conversation it was for.
@immutable
class SummaryFailure {
  const SummaryFailure({required this.conversationId, required this.kind, this.appId});

  final String conversationId;
  final SummaryFailureKind kind;

  /// The template that was asked for; null for Omi's own summary.
  final String? appId;
}

/// Whether [conversation] carries the summary a reprocess asked for: the template's non-empty
/// result when [appId] is set, otherwise a non-empty Omi summary — the compatibility overview or
/// the rendered sections, which is exactly what [ConversationSummarySelection.firstParty] accepts.
/// A template result never stands in for Omi's own: a stale stored one would read as success.
bool conversationHasRequestedSummary(ServerConversation conversation, String? appId) {
  if (appId != null) {
    return conversation.appResults.any((result) => result.appId == appId && result.content.trim().isNotEmpty);
  }
  return ConversationSummarySelection.firstParty(conversation).kind != ConversationSummaryKind.empty;
}

/// The production [PreferredSummaryAppWrite]: `PUT` for a template, `DELETE` for Omi.
Future<bool> writeServerPreferredSummaryApp(String? appId) =>
    appId == null ? clearPreferredSummarizationAppServer() : setPreferredSummarizationAppServer(appId);

/// Installed summary templates that work on conversations; throws when the list cannot be read.
Future<List<App>> fetchInstalledSummaryApps() async {
  final result = await retrieveInstalledChatApps(limit: 100);
  return switch (result) {
    ApiSuccess(:final data) => (data.data ?? const [])
        .map(App.fromGeneratedCatalogItem)
        .where((app) => !app.deleted && app.worksWithMemories() && app.enabled)
        .toList(),
    ApiFailure(:final problem) => throw StateError('installed apps unavailable: ${problem.kind.name}'),
  };
}

/// Templates the server suggests for one conversation; throws when the list cannot be read.
Future<List<App>> fetchConversationSuggestedSummaryApps(String conversationId) async {
  final apps = await getConversationSuggestedApps(conversationId);
  if (apps == null) throw StateError('suggested apps unavailable');
  return apps;
}

/// Summary-generation state of the conversation detail page: the template lists (with load
/// states and stale-response guards), the last failed summary request, the saved default template
/// and which summary source the Summary tab shows. ConversationDetailProvider mixes it in.
mixin ConversationSummaryGeneration on ChangeNotifier {
  ServerConversation? get conversationOrNull;
  ServerConversation get conversation;
  AppProvider? get appProvider;
  EnabledSummaryAppsFetch get enabledSummaryAppsFetch;
  SuggestedSummaryAppsFetch get suggestedSummaryAppsFetch;
  PreferredSummaryAppWrite get preferredSummaryAppWrite;

  /// Whether the provider is disposed; late responses must not notify.
  bool get summaryGenerationDisposed;

  SummaryFailure? _summaryFailure;

  /// Why the open conversation's last summary request produced nothing, until the next request
  /// starts or the reader dismisses it. Null for any other conversation.
  SummaryFailure? get summaryFailure {
    final failure = _summaryFailure;
    if (failure == null || failure.conversationId != conversationOrNull?.id) return null;
    return failure;
  }

  /// Hides the failure card (the reader acknowledged it).
  void dismissSummaryFailure() {
    if (_summaryFailure == null) return;
    _summaryFailure = null;
    notifyListeners();
  }

  /// Sets (or clears) the failure without notifying; the reprocess flow notifies once.
  @protected
  void recordSummaryFailure(SummaryFailure? failure) => _summaryFailure = failure;

  // Installed summary templates are the user's, so they survive opening another conversation.
  // Suggestions belong to one conversation and are dropped when the page shows a different one.
  final List<App> _cachedEnabledConversationApps = [];
  final List<App> _cachedSuggestedApps = [];
  String? _cachedSuggestedAppsConversationId;
  int _suggestedAppsGeneration = 0;
  int _enabledAppsGeneration = 0;
  SummaryTemplatesLoad enabledTemplatesLoad = SummaryTemplatesLoad.idle;
  SummaryTemplatesLoad suggestedTemplatesLoad = SummaryTemplatesLoad.idle;
  // Track locally added apps (e.g., from quick template creator) to preserve during refetch
  final Set<String> _locallyAddedAppIds = {};

  /// Returns cached enabled conversation apps
  List<App> get cachedEnabledConversationApps => _cachedEnabledConversationApps;

  /// Returns cached suggested apps for the open conversation (empty for any other).
  List<App> get cachedSuggestedApps =>
      _cachedSuggestedAppsConversationId != null && _cachedSuggestedAppsConversationId == conversationOrNull?.id
          ? _cachedSuggestedApps
          : const [];

  /// Forgets the open conversation's suggestions (another conversation is now open).
  @protected
  void resetSuggestedSummaryApps() {
    _cachedSuggestedApps.clear();
    _cachedSuggestedAppsConversationId = null;
    _suggestedAppsGeneration++;
    suggestedTemplatesLoad = SummaryTemplatesLoad.idle;
  }

  /// The summary source the Summary tab shows for the open conversation, as `sourceKey`; null
  /// follows [ConversationSummarySelection.select].
  String? _summaryViewKey;
  String? _summaryViewConversationId;

  /// The summary the Summary tab shows: the source the reader picked (a chip, or the one a
  /// reprocess just wrote) while the conversation still has it, else [ConversationSummarySelection.select].
  ConversationSummarySelection getDisplayedSummarySelection() {
    final target = conversation;
    final key = _summaryViewConversationId == target.id ? _summaryViewKey : null;
    if (key != null) {
      final picked =
          ConversationSummarySelection.available(target).firstWhereOrNull((selection) => selection.sourceKey == key);
      if (picked != null) return picked;
    }
    return ConversationSummarySelection.select(target);
  }

  /// Shows [selection]'s source on the Summary tab.
  void showSummarySource(ConversationSummarySelection selection) {
    final target = conversationOrNull;
    if (target == null) return;
    _summaryViewConversationId = target.id;
    _summaryViewKey = selection.sourceKey;
    notifyListeners();
  }

  /// After a reprocess lands, show the source it was asked for (Omi when [appId] is null).
  @protected
  void showRequestedSummarySource(String conversationId, String? appId) {
    _summaryViewConversationId = conversationId;
    _summaryViewKey = appId == null ? 'omi' : 'app:$appId';
  }

  /// Fetches and caches enabled conversation apps, keeping [enabledTemplatesLoad] current. A failed
  /// read keeps whatever was cached and reports [SummaryTemplatesLoad.failed]; it is never an empty
  /// list. Preserves locally added apps that may not yet be returned by the API.
  Future<void> fetchAndCacheEnabledConversationApps() async {
    // Only the newest read may publish: an older one finishing late must not overwrite it.
    final generation = ++_enabledAppsGeneration;
    // Not notified: callers start fetches from initState, and the sheet reads idle and loading alike.
    enabledTemplatesLoad = SummaryTemplatesLoad.loading;
    List<App> apps;
    try {
      apps = await enabledSummaryAppsFetch();
    } catch (e) {
      Logger.debug('Error fetching enabled conversation apps: ${e.runtimeType}');
      if (summaryGenerationDisposed || generation != _enabledAppsGeneration) return;
      enabledTemplatesLoad = SummaryTemplatesLoad.failed;
      notifyListeners();
      return;
    }
    if (summaryGenerationDisposed || generation != _enabledAppsGeneration) return;

    // Preserve locally added apps that aren't in the API response yet
    final locallyAddedApps =
        _cachedEnabledConversationApps.where((app) => _locallyAddedAppIds.contains(app.id)).toList();

    _cachedEnabledConversationApps.clear();
    _cachedEnabledConversationApps.addAll(apps);

    // Add back locally added apps if they weren't returned by the API
    for (final localApp in locallyAddedApps) {
      if (!apps.any((app) => app.id == localApp.id)) {
        _cachedEnabledConversationApps.add(localApp);
      } else {
        // If API returned the app, remove from locally tracked set
        _locallyAddedAppIds.remove(localApp.id);
      }
    }
    enabledTemplatesLoad = SummaryTemplatesLoad.loaded;
    notifyListeners();
  }

  /// Fetches and caches the open conversation's suggested apps, keeping [suggestedTemplatesLoad]
  /// current. A response for a conversation the page no longer shows is dropped.
  Future<void> fetchAndCacheSuggestedApps() async {
    final conversationId = conversationOrNull?.id;
    if (conversationId == null) return;
    final generation = ++_suggestedAppsGeneration;
    suggestedTemplatesLoad = SummaryTemplatesLoad.loading;
    List<App>? apps;
    try {
      apps = await suggestedSummaryAppsFetch(conversationId);
    } catch (e) {
      Logger.debug('Error fetching suggested apps: ${e.runtimeType}');
    }
    final stale = generation != _suggestedAppsGeneration || conversationOrNull?.id != conversationId;
    if (summaryGenerationDisposed || stale) return;
    _cachedSuggestedApps.clear();
    if (apps != null) _cachedSuggestedApps.addAll(apps);
    _cachedSuggestedAppsConversationId = conversationId;
    suggestedTemplatesLoad = apps == null ? SummaryTemplatesLoad.failed : SummaryTemplatesLoad.loaded;
    notifyListeners();
  }

  /// Finds an app by ID from cached apps
  App? findAppById(String? appId) {
    if (appId == null) return null;

    final enabledApp = _cachedEnabledConversationApps.firstWhereOrNull((app) => app.id == appId);
    if (enabledApp != null) return enabledApp;

    final suggestedApp = _cachedSuggestedApps.firstWhereOrNull((app) => app.id == appId);
    if (suggestedApp != null) return suggestedApp;

    // The two caches above only fill after the summary sheet fetches. The durable
    // app catalog (appProvider.apps) is loaded at startup, so a real app_id must
    // resolve here instead of rendering "Unknown App" until the sheet is opened
    // (SCA-359).
    final providerApp = appProvider?.apps.firstWhereOrNull((app) => app.id == appId);
    return providerApp;
  }

  /// Enables an app and updates the cached enabled apps list
  /// Returns true if successful, false otherwise
  Future<bool> enableApp(App app) async {
    try {
      // Make the server call to enable the app
      final (success, _) = await enableAppServer(app.id);
      if (summaryGenerationDisposed) return false;

      if (success) {
        // Update SharedPreferences
        SharedPreferencesUtil().enableApp(app.id);

        // Update the app's enabled state
        app.enabled = true;

        // Add to cached enabled apps if not already there
        final existingIndex = _cachedEnabledConversationApps.indexWhere((a) => a.id == app.id);
        if (existingIndex == -1) {
          _cachedEnabledConversationApps.add(app);
        } else {
          _cachedEnabledConversationApps[existingIndex] = app;
        }

        notifyListeners();
      }

      return success;
    } catch (e) {
      Logger.debug('Error enabling app ${app.id}: $e');
      return false;
    }
  }

  /// Adds an app to the cached enabled conversation apps list
  /// Used when a new app is created and installed from the quick template creator
  void addToEnabledConversationApps(App app) {
    final existingIndex = _cachedEnabledConversationApps.indexWhere((a) => a.id == app.id);
    if (existingIndex == -1) {
      _cachedEnabledConversationApps.add(app);
    } else {
      _cachedEnabledConversationApps[existingIndex] = app;
    }
    // Track this as a locally added app so it's preserved during refetch
    _locallyAddedAppIds.add(app.id);
    notifyListeners();
  }

  /// Checks if a suggested app is available/enabled for the user
  bool isSuggestedAppAvailable(String appId) {
    if (appProvider == null) return false;
    return appProvider!.apps.any((app) => app.id == appId && app.worksWithMemories() && app.enabled);
  }

  /// The template saved with "Make this my default"; null means Omi's own summary.
  /// Stored per signed-in user on this device, so another account never inherits it.
  static String _defaultTemplateKey() => 'defaultSummaryTemplateAppId:${SharedPreferencesUtil().uid}';

  String? get defaultSummaryTemplateAppId {
    final id = SharedPreferencesUtil().getString(_defaultTemplateKey());
    return id.isEmpty ? null : id;
  }

  /// Saves the default locally (the sheet's initial choice on this device) and on the server, which
  /// owns what automatic processing runs: a template is set as the preferred app, Omi clears it.
  /// Resolves whether the server stored it; the local choice is kept either way.
  Future<bool> setDefaultSummaryTemplateAppId(String? appId) async {
    SharedPreferencesUtil().saveString(_defaultTemplateKey(), appId ?? '');
    notifyListeners();
    try {
      final stored = await preferredSummaryAppWrite(appId);
      if (!stored) Logger.debug('preferred summary app was not stored on the server');
      return stored;
    } catch (e) {
      Logger.debug('preferred summary app write failed: ${e.runtimeType}');
      return false;
    }
  }
}
