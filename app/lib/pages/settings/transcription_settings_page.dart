import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/sockets/stt_response_schema.dart';
import 'package:provider/provider.dart';

enum SttProvider {
  omi,
  openai,
  deepgram,
  falai,
  gemini,
  whisperCpp,
  custom,
}

extension SttProviderExtension on SttProvider {
  String get displayName {
    final config = providerConfig;
    if (config != null) return config.displayName;
    return this == SttProvider.omi ? 'Omi' : name;
  }

  String get description {
    final config = providerConfig;
    if (config != null) return config.description;
    return this == SttProvider.omi ? 'Omi\'s optimized transcription service' : '';
  }

  IconData get icon {
    switch (this) {
      case SttProvider.omi:
        return FontAwesomeIcons.robot;
      case SttProvider.openai:
        return FontAwesomeIcons.brain;
      case SttProvider.deepgram:
        return FontAwesomeIcons.waveSquare;
      case SttProvider.falai:
        return FontAwesomeIcons.bolt;
      case SttProvider.gemini:
        return FontAwesomeIcons.google;
      case SttProvider.whisperCpp:
        return FontAwesomeIcons.server;
      case SttProvider.custom:
        return FontAwesomeIcons.code;
    }
  }

  bool get requiresApiKey {
    switch (this) {
      case SttProvider.omi:
      case SttProvider.whisperCpp:
      case SttProvider.custom:
        return false;
      default:
        return true;
    }
  }

  SttResponseSchema get schema {
    final config = providerConfig;
    return config?.responseSchema ?? const SttResponseSchema();
  }

  /// Get the centralized provider config
  SttProviderConfig? get providerConfig {
    switch (this) {
      case SttProvider.openai:
        return SttProviderConfig.openAI;
      case SttProvider.deepgram:
        return SttProviderConfig.deepgram;
      case SttProvider.falai:
        return SttProviderConfig.falAI;
      case SttProvider.gemini:
        return SttProviderConfig.gemini;
      case SttProvider.whisperCpp:
        return SttProviderConfig.whisperCpp;
      case SttProvider.custom:
        return SttProviderConfig.custom;
      default:
        return null;
    }
  }
}

class CustomSttConfig {
  final SttProvider provider;
  final String? apiKey;
  final String? apiUrl;
  final String? host;
  final int? port;
  final Map<String, String>? headers;
  final Map<String, String>? fields;
  final String? audioFieldName;
  final String? requestType;
  final Map<String, dynamic>? schemaJson;
  final Map<String, dynamic>? fileUploadConfig;

  const CustomSttConfig({
    required this.provider,
    this.apiKey,
    this.apiUrl,
    this.host,
    this.port,
    this.headers,
    this.fields,
    this.audioFieldName,
    this.requestType,
    this.schemaJson,
    this.fileUploadConfig,
  });

  bool get isEnabled => provider != SttProvider.omi;

  SttResponseSchema get schema {
    if (schemaJson != null) {
      return SttResponseSchema.fromJson(schemaJson!);
    }
    return provider.schema;
  }

  Map<String, dynamic> toJson() => {
        'provider': provider.name,
        'api_key': apiKey,
        'api_url': apiUrl,
        'host': host,
        'port': port,
        'headers': headers,
        'fields': fields,
        'audio_field_name': audioFieldName,
        'request_type': requestType,
        'schema': schemaJson,
        'file_upload_config': fileUploadConfig,
      };

  factory CustomSttConfig.fromJson(Map<String, dynamic> json) {
    return CustomSttConfig(
      provider: SttProvider.values.firstWhere(
        (e) => e.name == json['provider'],
        orElse: () => SttProvider.omi,
      ),
      apiKey: json['api_key'],
      apiUrl: json['api_url'],
      host: json['host'],
      port: json['port'],
      headers: json['headers'] != null ? Map<String, String>.from(json['headers']) : null,
      fields: json['fields'] != null ? Map<String, String>.from(json['fields']) : null,
      audioFieldName: json['audio_field_name'],
      requestType: json['request_type'],
      schemaJson: json['schema'] != null ? Map<String, dynamic>.from(json['schema']) : null,
      fileUploadConfig:
          json['file_upload_config'] != null ? Map<String, dynamic>.from(json['file_upload_config']) : null,
    );
  }

  static const CustomSttConfig defaultConfig = CustomSttConfig(provider: SttProvider.omi);

  /// Generate a unique key for this config to detect changes
  String get configKey {
    if (!isEnabled) return 'omi:default';
    return '${provider.name}:${apiKey ?? ""}:${apiUrl ?? ""}:${host ?? ""}:${port ?? 0}';
  }

  /// Get full template JSON using centralized SttProviderConfig
  static Map<String, dynamic> getFullTemplateJson(SttProvider provider) {
    final config = provider.providerConfig;
    if (config != null) {
      return config.getFullTemplateJson();
    }
    return {
      'request': SttProviderConfig.custom.requestConfig,
      'response_schema': const SttResponseSchema().toJson(),
    };
  }
}

class TranscriptionSettingsPage extends StatefulWidget {
  const TranscriptionSettingsPage({super.key});

  @override
  State<TranscriptionSettingsPage> createState() => _TranscriptionSettingsPageState();
}

class _TranscriptionSettingsPageState extends State<TranscriptionSettingsPage> with SingleTickerProviderStateMixin {
  bool _useCustomStt = false;
  SttProvider _selectedProvider = SttProvider.openai;
  late TabController _tabController;

  final TextEditingController _apiKeyController = TextEditingController();
  final TextEditingController _hostController = TextEditingController(text: '127.0.0.1');
  final TextEditingController _portController = TextEditingController(text: '8080');
  final TextEditingController _requestJsonController = TextEditingController();
  final TextEditingController _schemaJsonController = TextEditingController();

  bool _showApiKey = false;
  bool _isAdvancedMode = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _loadConfig();
  }

  void _loadConfig() {
    final config = SharedPreferencesUtil().customSttConfig;
    setState(() {
      _useCustomStt = config.isEnabled;
      _selectedProvider = config.provider == SttProvider.omi ? SttProvider.openai : config.provider;
      _apiKeyController.text = config.apiKey ?? '';
      _hostController.text = config.host ?? '127.0.0.1';
      _portController.text = (config.port ?? 8080).toString();
      _loadTemplateForProvider(_selectedProvider);
    });
  }

  void _loadTemplateForProvider(SttProvider provider) {
    final template = CustomSttConfig.getFullTemplateJson(provider);
    _requestJsonController.text = const JsonEncoder.withIndent('  ').convert(template['request']);
    _schemaJsonController.text = const JsonEncoder.withIndent('  ').convert(template['response_schema']);
  }

  Future _saveConfig() async{
    try {
      Map<String, dynamic> requestJson = {};
      Map<String, dynamic> schemaJson = {};

      if (_requestJsonController.text.isNotEmpty) {
        requestJson = jsonDecode(_requestJsonController.text);
      }
      if (_schemaJsonController.text.isNotEmpty) {
        schemaJson = jsonDecode(_schemaJsonController.text);
      }

      if (!_isAdvancedMode && _apiKeyController.text.isNotEmpty && _selectedProvider.requiresApiKey) {
        final headers = Map<String, String>.from(requestJson['headers'] ?? {});
        switch (_selectedProvider) {
          case SttProvider.openai:
            headers['Authorization'] = 'Bearer ${_apiKeyController.text}';
            break;
          case SttProvider.deepgram:
            headers['Authorization'] = 'Token ${_apiKeyController.text}';
            break;
          case SttProvider.falai:
            headers['Authorization'] = 'Key ${_apiKeyController.text}';
            if (requestJson['file_upload'] != null) {
              final fileUpload = Map<String, dynamic>.from(requestJson['file_upload']);
              final fileUploadHeaders = Map<String, String>.from(fileUpload['file_upload_headers'] ?? {});
              fileUploadHeaders['Authorization'] = 'Key ${_apiKeyController.text}';
              fileUpload['file_upload_headers'] = fileUploadHeaders;
              requestJson['file_upload'] = fileUpload;
            }
            break;
          case SttProvider.gemini:
            final url = requestJson['api_url'] as String? ?? '';
            requestJson['api_url'] = url.replaceAll('YOUR_API_KEY', _apiKeyController.text);
            break;
          default:
            break;
        }
        requestJson['headers'] = headers;
      }

      if (_selectedProvider == SttProvider.whisperCpp) {
        requestJson['api_url'] = 'http://${_hostController.text}:${_portController.text}/inference';
      }

      final config = CustomSttConfig(
        provider: _useCustomStt ? _selectedProvider : SttProvider.omi,
        apiKey: _apiKeyController.text.isNotEmpty ? _apiKeyController.text : null,
        apiUrl: requestJson['api_url'],
        host: _hostController.text.isNotEmpty ? _hostController.text : null,
        port: int.tryParse(_portController.text),
        headers: requestJson['headers'] != null ? Map<String, String>.from(requestJson['headers']) : null,
        fields: requestJson['fields'] != null ? Map<String, String>.from(requestJson['fields']) : null,
        audioFieldName: requestJson['audio_field_name'],
        requestType: requestJson['request_type'],
        schemaJson: schemaJson.isNotEmpty ? schemaJson : null,
        fileUploadConfig:
            requestJson['file_upload'] != null ? Map<String, dynamic>.from(requestJson['file_upload']) : null,
      );

      final previousConfig = SharedPreferencesUtil().customSttConfig;
      final configChanged = previousConfig.provider != config.provider ||
          previousConfig.apiKey != config.apiKey ||
          previousConfig.apiUrl != config.apiUrl ||
          previousConfig.host != config.host ||
          previousConfig.port != config.port;

      SharedPreferencesUtil().customSttConfig = config;

      // Refresh the transcription service if config changed
      if (configChanged && mounted) {
        final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
        await captureProvider.onTranscriptionSettingsChanged();
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Transcription settings saved')),
        );
        Navigator.of(context).pop();
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Invalid JSON: $e'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Transcription'),
        backgroundColor: Colors.black,
        actions: [
          TextButton(
            onPressed: _saveConfig,
            child: const Text('Save', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildMainToggle(),
            const SizedBox(height: 24),
            if (_useCustomStt) ...[
              _buildProviderSelector(),
              const SizedBox(height: 24),
              _buildModeToggle(),
              const SizedBox(height: 16),
              if (_isAdvancedMode) _buildAdvancedConfig() else _buildSimpleConfig(),
            ] else ...[
              _buildOmiInfoCard(),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildMainToggle() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Use Custom STT',
                style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
              ),
              Switch(
                value: _useCustomStt,
                activeColor: Colors.white,
                activeTrackColor: const Color(0xFF7C3AED),
                onChanged: (value) => setState(() => _useCustomStt = value),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            _useCustomStt
                ? 'Your STT transcribes audio → Omi processes conversations (no credits)'
                : 'Using Omi\'s optimized transcription',
            style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
          ),
        ],
      ),
    );
  }

  Widget _buildProviderSelector() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'STT Provider',
            style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: SttProvider.values
                .where((p) => p != SttProvider.omi)
                .map((provider) => _buildProviderChip(provider))
                .toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildProviderChip(SttProvider provider) {
    final isSelected = _selectedProvider == provider;
    return GestureDetector(
      onTap: () {
        setState(() => _selectedProvider = provider);
        _loadTemplateForProvider(provider);
        if (provider == SttProvider.custom) {
          setState(() => _isAdvancedMode = true);
        }
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF7C3AED) : Colors.grey.shade800,
          borderRadius: BorderRadius.circular(20),
          border: isSelected ? null : Border.all(color: Colors.grey.shade700),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(provider.icon, size: 14, color: Colors.white),
            const SizedBox(width: 6),
            Text(provider.displayName, style: const TextStyle(color: Colors.white, fontSize: 13)),
          ],
        ),
      ),
    );
  }

  Widget _buildModeToggle() {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Expanded(child: _buildModeButton('Simple', !_isAdvancedMode, () => setState(() => _isAdvancedMode = false))),
          Expanded(child: _buildModeButton('Advanced', _isAdvancedMode, () => setState(() => _isAdvancedMode = true))),
        ],
      ),
    );
  }

  Widget _buildModeButton(String label, bool isSelected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF1C1C1E) : Colors.transparent,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(
          label,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.grey,
            fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
      ),
    );
  }

  Widget _buildSimpleConfig() {
    if (_selectedProvider == SttProvider.whisperCpp) {
      return _buildWhisperCppConfig();
    } else if (_selectedProvider == SttProvider.custom) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !_isAdvancedMode) {
          setState(() => _isAdvancedMode = true);
        }
      });
      return const SizedBox.shrink();
    }
    return _buildApiKeyConfig();
  }

  Widget _buildApiKeyConfig() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _selectedProvider.displayName,
            style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(_selectedProvider.description, style: TextStyle(color: Colors.grey.shade400, fontSize: 13)),
          const SizedBox(height: 16),
          const Text('API Key', style: TextStyle(color: Colors.white70, fontSize: 13)),
          const SizedBox(height: 8),
          TextField(
            controller: _apiKeyController,
            obscureText: !_showApiKey,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              hintText: 'Enter your API key',
              hintStyle: TextStyle(color: Colors.grey.shade600),
              filled: true,
              fillColor: Colors.grey.shade900,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
              suffixIcon: IconButton(
                icon: Icon(_showApiKey ? Icons.visibility_off : Icons.visibility, color: Colors.grey),
                onPressed: () => setState(() => _showApiKey = !_showApiKey),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWhisperCppConfig() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Whisper.cpp Server',
              style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text('Connect to your local server', style: TextStyle(color: Colors.grey.shade400, fontSize: 13)),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                flex: 2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Host', style: TextStyle(color: Colors.white70, fontSize: 13)),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _hostController,
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        hintText: '127.0.0.1',
                        hintStyle: TextStyle(color: Colors.grey.shade600),
                        filled: true,
                        fillColor: Colors.grey.shade900,
                        border:
                            OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Port', style: TextStyle(color: Colors.white70, fontSize: 13)),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _portController,
                      keyboardType: TextInputType.number,
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        hintText: '8080',
                        hintStyle: TextStyle(color: Colors.grey.shade600),
                        filled: true,
                        fillColor: Colors.grey.shade900,
                        border:
                            OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAdvancedConfig() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Configuration',
                  style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600)),
              PopupMenuButton<SttProvider>(
                icon: const Icon(Icons.content_copy, color: Colors.grey, size: 20),
                tooltip: 'Load template',
                color: Colors.grey.shade900,
                onSelected: (provider) {
                  setState(() => _selectedProvider = provider);
                  _loadTemplateForProvider(provider);
                },
                itemBuilder: (context) => SttProvider.values
                    .where((p) => p != SttProvider.omi && p != SttProvider.custom)
                    .map((p) => PopupMenuItem(
                        value: p, child: Text(p.displayName, style: const TextStyle(color: Colors.white))))
                    .toList(),
              ),
            ],
          ),
          const SizedBox(height: 16),
          TabBar(
            controller: _tabController,
            indicatorColor: const Color(0xFF7C3AED),
            labelColor: Colors.white,
            unselectedLabelColor: Colors.grey,
            tabs: const [Tab(text: 'Request'), Tab(text: 'Response Schema')],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 320,
            child: TabBarView(
              controller: _tabController,
              children: [_buildRequestEditor(), _buildSchemaEditor()],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRequestEditor() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('API endpoint, headers, request format', style: TextStyle(color: Colors.grey.shade400, fontSize: 12)),
        const SizedBox(height: 8),
        Expanded(
          child: Container(
            decoration: BoxDecoration(color: Colors.grey.shade900, borderRadius: BorderRadius.circular(8)),
            child: TextField(
              controller: _requestJsonController,
              maxLines: null,
              expands: true,
              style: const TextStyle(color: Colors.white, fontFamily: 'monospace', fontSize: 12),
              decoration: InputDecoration(
                hintText: '{\n  "api_url": "...",\n  ...\n}',
                hintStyle: TextStyle(color: Colors.grey.shade700),
                border: InputBorder.none,
                contentPadding: const EdgeInsets.all(12),
              ),
            ),
          ),
        ),
        const SizedBox(height: 8),
        _buildRequestHelp(),
      ],
    );
  }

  Widget _buildSchemaEditor() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Define how to parse STT response', style: TextStyle(color: Colors.grey.shade400, fontSize: 12)),
        const SizedBox(height: 8),
        Expanded(
          child: Container(
            decoration: BoxDecoration(color: Colors.grey.shade900, borderRadius: BorderRadius.circular(8)),
            child: TextField(
              controller: _schemaJsonController,
              maxLines: null,
              expands: true,
              style: const TextStyle(color: Colors.white, fontFamily: 'monospace', fontSize: 12),
              decoration: InputDecoration(
                hintText: '{\n  "segments_path": "...",\n  ...\n}',
                hintStyle: TextStyle(color: Colors.grey.shade700),
                border: InputBorder.none,
                contentPadding: const EdgeInsets.all(12),
              ),
            ),
          ),
        ),
        const SizedBox(height: 8),
        _buildSchemaHelp(),
      ],
    );
  }

  Widget _buildRequestHelp() {
    return ExpansionTile(
      title: const Text('Field Reference', style: TextStyle(color: Colors.grey, fontSize: 12)),
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      iconColor: Colors.grey,
      collapsedIconColor: Colors.grey,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: Colors.grey.shade900, borderRadius: BorderRadius.circular(8)),
          child: Text(
            '• api_url: API endpoint\n'
            '• request_type: multipart_form | raw_binary | json_base64\n'
            '• headers: HTTP headers\n'
            '• fields: Form fields (multipart)\n'
            '• audio_field_name: Audio file field name\n'
            '• file_upload: Pre-upload config (Fal.AI)',
            style: TextStyle(color: Colors.grey.shade400, fontSize: 11, fontFamily: 'monospace'),
          ),
        ),
      ],
    );
  }

  Widget _buildSchemaHelp() {
    return ExpansionTile(
      title: const Text('Field Reference', style: TextStyle(color: Colors.grey, fontSize: 12)),
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      iconColor: Colors.grey,
      collapsedIconColor: Colors.grey,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: Colors.grey.shade900, borderRadius: BorderRadius.circular(8)),
          child: Text(
            '• segments_path: Path to segments array\n'
            '  e.g., "segments" or "results.channels[0].alternatives[0].words"\n'
            '• text_field: Transcript text field\n'
            '• start_field: Segment start time\n'
            '• end_field: Segment end time\n'
            '• speaker_field: Speaker ID (optional)\n'
            '• confidence_field: Confidence score (optional)\n'
            '• raw_text_path: Full transcript path\n'
            '• duration_path: Audio duration path\n'
            '• language_path: Detected language path',
            style: TextStyle(color: Colors.grey.shade400, fontSize: 11, fontFamily: 'monospace'),
          ),
        ),
      ],
    );
  }

  Widget _buildOmiInfoCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFF7C3AED).withOpacity(0.2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(FontAwesomeIcons.robot, color: Color(0xFF7C3AED), size: 24),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Omi Transcription',
                    style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(
                  'Optimized for conversations with speaker diarization',
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _tabController.dispose();
    _apiKeyController.dispose();
    _hostController.dispose();
    _portController.dispose();
    _requestJsonController.dispose();
    _schemaJsonController.dispose();
    super.dispose();
  }
}
