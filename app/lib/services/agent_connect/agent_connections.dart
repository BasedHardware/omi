import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/mcp_api.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/agent_connect/agent_prompts.dart';
import 'package:omi/services/agent_connect/zkr_share.dart';

/// The approved ChatGPT directory listing: the one-tap ChatGPT path (same link as the macOS app's
/// `MemoryExportDestination.chatGPTDirectoryInstallURL`).
final chatGptDirectoryUrl =
    Uri.parse('https://chatgpt.com/plugins/plugin_asdk_app_6a1490df4c588191b9339ae21978c873?q=omi');

/// Opens ChatGPT with [prompt] typed in the composer.
Uri chatGptPromptUrl(String prompt) => Uri.https('chatgpt.com', '/', {'q': prompt});

/// OAuth client ids that mean "ChatGPT holds a grant". The directory listing always grants under
/// the prod id, even on a dev backend; mirrors backend `PUBLIC_CHATGPT_CLIENT_IDS`.
const chatGptClientIds = {'omi-chatgpt-prod', 'omi-chatgpt-dev'};

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

  /// The MCP key's name, which is also how the row finds its active key again.
  String get keyName => brandName ?? 'Agent';
}

bool isLiveGrant(Map<String, dynamic> grant) => grant['revoked_at'] == null && grant['status'] != 'revoked';

/// What is connected right now: live ChatGPT grants and the MCP key each computer agent holds.
@immutable
class AgentConnections {
  const AgentConnections({required this.chatGptGrantIds, required this.agentKeys});

  final List<String> chatGptGrantIds;
  final Map<ComputerAgent, McpApiKey> agentKeys;

  bool get chatGptConnected => chatGptGrantIds.isNotEmpty;

  static AgentConnections from({required List<Map<String, dynamic>> grants, required List<McpApiKey> keys}) {
    final chatGpt = [
      for (final grant in grants)
        if (chatGptClientIds.contains(grant['client_id']) && isLiveGrant(grant) && grant['id'] is String)
          grant['id'] as String,
    ];
    final agentKeys = <ComputerAgent, McpApiKey>{};
    for (final agent in ComputerAgent.values) {
      final matches = keys.where((key) => key.name == agent.keyName).toList();
      if (matches.isNotEmpty) agentKeys[agent] = matches.first;
    }
    return AgentConnections(chatGptGrantIds: chatGpt, agentKeys: agentKeys);
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

  /// Whether ChatGPT holds a live grant; grants only, for surfaces that do not show keys.
  Future<bool> chatGptConnected() async =>
      AgentConnections.from(grants: await _loadGrants(), keys: const []).chatGptConnected;

  Future<void> disconnectChatGpt(AgentConnections connections) =>
      Future.wait(connections.chatGptGrantIds.map(_revokeGrant));

  /// The prompt [agent] receives, with a placeholder where the one-time link goes. Shown before
  /// any key exists, so opening the sheet never creates one.
  String previewPrompt() => buildMcpKeyPrompt(_base, '<one-time secure link — made when you copy>');

  /// Creates a key named for [agent], seals it in a one-time link, and returns the prompt that
  /// carries the link. If the link cannot be made, the new key is deleted again.
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

  String get _base => _apiBase ?? Env.apiBaseUrl ?? 'https://api.omi.me/';

  Future<void> revokeKey(String keyId) => _deleteKey(keyId);
}

@immutable
class PreparedAgentPrompt {
  const PreparedAgentPrompt({required this.prompt, required this.keyId});

  /// The copy-paste prompt, carrying the one-time link.
  final String prompt;

  /// The key the link holds, so a fresh link can replace it.
  final String keyId;
}
