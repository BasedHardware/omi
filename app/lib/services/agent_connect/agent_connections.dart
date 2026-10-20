import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/mcp_api.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/agent_connect/agent_prompts.dart';
import 'package:omi/services/agent_connect/zkr_share.dart';
import 'package:omi/utils/logger.dart';

/// Product name; never translated.
const chatGptBrandName = 'ChatGPT';

/// The approved ChatGPT directory listing: the one-tap ChatGPT path (same link as the macOS app's
/// `MemoryExportDestination.chatGPTDirectoryInstallURL`).
final chatGptDirectoryUrl =
    Uri.parse('https://chatgpt.com/plugins/plugin_asdk_app_6a1490df4c588191b9339ae21978c873?q=omi');

/// Opens ChatGPT with [prompt] typed in the composer.
Uri chatGptPromptUrl(String prompt) => Uri.https('chatgpt.com', '/', {'q': prompt});

/// OAuth client ids that mean "ChatGPT holds a grant". The directory listing always grants under
/// the prod id, even on a dev backend; mirrors backend `PUBLIC_CHATGPT_CLIENT_IDS`.
const chatGptClientIds = {'omi-chatgpt-prod', 'omi-chatgpt-dev'};

/// What the ChatGPT screens ask ChatGPT to read (backend `config/mcp_scopes.py`). The backend
/// enforces each scope separately, so a grant missing one gets refused for that kind of question.
const chatGptRequiredScopes = {'memories.read', 'conversations.read', 'action_items.read', 'goals.read'};

/// Agents that run on their own computer. They cannot approve Omi in the phone's browser, so each
/// gets its own MCP key, handed over through a one-time zkr link inside a copy-paste prompt.
enum ComputerAgent {
  grokBot('Grok Bot'),
  muse('Muse'),
  instinct('Instinct'),
  other(null);

  const ComputerAgent(this.brandName);

  /// Product name; never translated. Null for the catch-all row.
  final String? brandName;

  /// The MCP key's name, which is also how the row finds its active key again. The suffix keeps a
  /// key someone named "Muse" or "Agent" on the web from being mistaken for one this screen made.
  String get keyName => '${brandName ?? 'Agent'} (Omi app)';
}

/// Mirrors the backend token check (`database/mcp_oauth.py`): only an `active`, unrevoked grant
/// whose optional expiry is still ahead lets ChatGPT call Omi.
bool isLiveGrant(Map<String, dynamic> grant, {DateTime? now}) {
  if (grant['status'] != 'active' || grant['revoked_at'] != null) return false;
  final expiresAt = grant['expires_at'];
  if (expiresAt == null) return true;
  final expiry = expiresAt is String ? DateTime.tryParse(expiresAt) : null;
  return expiry != null && expiry.isAfter(now ?? DateTime.now());
}

/// What is connected right now: live ChatGPT grants and the MCP key each computer agent holds.
@immutable
class AgentConnections {
  const AgentConnections({
    required this.chatGptGrantIds,
    required this.agentKeys,
    this.chatGptMissingScopes = const {},
  });

  final List<String> chatGptGrantIds;
  final Map<ComputerAgent, McpApiKey> agentKeys;

  /// Required scopes no live ChatGPT grant carries. Empty when the grants do not list scopes, so
  /// an older grant record is never mistaken for a partial one.
  final Set<String> chatGptMissingScopes;

  bool get chatGptConnected => chatGptGrantIds.isNotEmpty;

  /// ChatGPT is connected but was approved without access the screens rely on; connecting again
  /// asks for it.
  bool get chatGptNeedsReconnect => chatGptConnected && chatGptMissingScopes.isNotEmpty;

  /// ChatGPT can look up a conversation for "Ask About This Conversation".
  bool get chatGptCanReadConversations => chatGptConnected && !chatGptMissingScopes.contains('conversations.read');

  AgentConnections withoutChatGpt() => AgentConnections(chatGptGrantIds: const [], agentKeys: agentKeys);

  AgentConnections withoutAgentKey(ComputerAgent agent) => AgentConnections(
        chatGptGrantIds: chatGptGrantIds,
        agentKeys: {...agentKeys}..remove(agent),
        chatGptMissingScopes: chatGptMissingScopes,
      );

  static AgentConnections from({required List<Map<String, dynamic>> grants, required List<McpApiKey> keys}) {
    final live = [
      for (final grant in grants)
        if (chatGptClientIds.contains(grant['client_id']) && isLiveGrant(grant) && grant['id'] is String) grant,
    ];
    final chatGpt = [for (final grant in live) grant['id'] as String];
    final scopes = <String>{
      for (final grant in live)
        if (grant['scopes'] is List) ...(grant['scopes'] as List).whereType<String>(),
    };
    final agentKeys = <ComputerAgent, McpApiKey>{};
    for (final agent in ComputerAgent.values) {
      final matches = keys.where((key) => key.name == agent.keyName).toList();
      if (matches.isNotEmpty) agentKeys[agent] = matches.first;
    }
    return AgentConnections(
      chatGptGrantIds: chatGpt,
      agentKeys: agentKeys,
      chatGptMissingScopes: scopes.isEmpty ? const {} : chatGptRequiredScopes.difference(scopes),
    );
  }
}

/// The calls the Connect an Agent screens make. Fields are seams for tests.
class AgentConnectService {
  AgentConnectService({
    Future<List<Map<String, dynamic>>> Function()? loadGrants,
    Future<void> Function(String grantId)? revokeGrant,
    Future<List<McpApiKey>> Function()? loadKeys,
    Future<McpApiKeyCreated> Function(String name)? createKey,
    Future<void> Function(String keyId)? deleteKey,
    Future<ZkrShare> Function(String secret)? share,
    String? apiBase,
  })  : _loadGrants = loadGrants ?? McpApi.getOauthGrants,
        _revokeGrant = revokeGrant ?? McpApi.revokeOauthGrant,
        _loadKeys = loadKeys ?? McpApi.getMcpApiKeys,
        _createKey = createKey ?? McpApi.createMcpApiKey,
        _deleteKey = deleteKey ?? McpApi.deleteMcpApiKey,
        _share = share ?? ((secret) => createZkrShare(secret, name: 'omi-mcp-key.txt')),
        _apiBase = apiBase;

  final Future<List<Map<String, dynamic>>> Function() _loadGrants;
  final Future<void> Function(String grantId) _revokeGrant;
  final Future<List<McpApiKey>> Function() _loadKeys;
  final Future<McpApiKeyCreated> Function(String name) _createKey;
  final Future<void> Function(String keyId) _deleteKey;
  final Future<ZkrShare> Function(String secret) _share;
  final String? _apiBase;

  Future<AgentConnections> load() async {
    final results = await Future.wait([_loadGrants(), _loadKeys()]);
    return AgentConnections.from(
      grants: results[0] as List<Map<String, dynamic>>,
      keys: results[1] as List<McpApiKey>,
    );
  }

  /// Whether ChatGPT can look up a conversation; grants only, for surfaces that do not show keys.
  Future<bool> chatGptCanReadConversations() async =>
      AgentConnections.from(grants: await _loadGrants(), keys: const []).chatGptCanReadConversations;

  Future<void> disconnectChatGpt(AgentConnections connections) =>
      Future.wait(connections.chatGptGrantIds.map(_revokeGrant));

  /// The prompt [agent] receives, with a placeholder where the one-time link goes. Shown before
  /// any key exists, so opening the sheet never creates one.
  String previewPrompt() => buildMcpKeyPrompt(_base, '<one-time secure link — made when you copy>');

  /// Creates a key named for [agent], seals it in a one-time link, and returns the prompt that
  /// carries the link. If the link cannot be made, the new key is deleted again. Older keys are left
  /// alone here; [retireOlderKeys] replaces them once the new prompt has been handed over.
  Future<PreparedAgentPrompt> preparePrompt(ComputerAgent agent) async {
    final created = await _createKey(agent.keyName);
    try {
      final share = await _share(created.key);
      return PreparedAgentPrompt(prompt: buildMcpKeyPrompt(_base, share.agentLink), keyId: created.id);
    } catch (_) {
      await _deleteKey(created.id).catchError((_) {});
      rethrow;
    }
  }

  /// One live key per agent: revokes every key with [agent]'s name except [keepKeyId]. Called only
  /// after the new prompt was copied, so an abandoned or failed attempt never cuts off a working
  /// agent, and a list that missed a key (a failed reload) cannot leave a forgotten one behind.
  /// Best effort: the next link for this agent retries.
  Future<void> retireOlderKeys(ComputerAgent agent, String keepKeyId) async {
    try {
      final older = (await _loadKeys()).where((key) => key.name == agent.keyName && key.id != keepKeyId);
      await Future.wait(older.map((key) => _deleteKey(key.id)));
    } catch (e) {
      // Still best effort, but no longer silent: revokeAgent sweeps any key left behind.
      Logger.debug('retireOlderKeys failed for ${agent.keyName}: $e');
    }
  }

  String get _base => _apiBase ?? Env.apiBaseUrl ?? 'https://api.omi.me/';

  Future<void> revokeKey(String keyId) => _deleteKey(keyId);

  /// Revokes every key [agent] holds, not only the one on screen: a failed [retireOlderKeys] can
  /// leave an older key alive under the same name. Reloads the list first, so a stale screen cannot
  /// miss one, and throws if any delete fails so the agent is never shown gone while a key works.
  ///
  /// If the list itself cannot load, the shown key is still revoked and the call throws, so the
  /// sheet says it failed and a retry (with a working list) sweeps the rest. A key the list no
  /// longer has is already gone and is not deleted twice.
  Future<void> revokeAgent(ComputerAgent agent, {required String shownKeyId}) async {
    final List<McpApiKey> listed;
    try {
      listed = await _loadKeys();
    } catch (_) {
      await _deleteKey(shownKeyId);
      rethrow;
    }
    final ids = [
      for (final key in listed)
        if (key.name == agent.keyName) key.id
    ];
    await Future.wait(ids.map(_deleteKey));
  }
}

@immutable
class PreparedAgentPrompt {
  const PreparedAgentPrompt({required this.prompt, required this.keyId});

  /// The copy-paste prompt, carrying the one-time link.
  final String prompt;

  /// The key the link holds, so a fresh link can replace it.
  final String keyId;
}
