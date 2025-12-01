import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:provider/provider.dart';

class TranscriptionSettingsPage extends StatefulWidget {
  const TranscriptionSettingsPage({super.key});

  @override
  State<TranscriptionSettingsPage> createState() => _TranscriptionSettingsPageState();
}

class _TranscriptionSettingsPageState extends State<TranscriptionSettingsPage> {
  bool _useCustomStt = false;
  SttProvider _selectedProvider = SttProvider.openai;
  bool _showAdvanced = false;
  bool _isSaving = false;
  String? _validationError;

  // Store API keys per provider
  final Map<SttProvider, String> _apiKeysPerProvider = {};

  final TextEditingController _apiKeyController = TextEditingController();
  final TextEditingController _hostController = TextEditingController(text: '127.0.0.1');
  final TextEditingController _portController = TextEditingController(text: '8080');

  // Store JSON configs per provider
  final Map<SttProvider, String> _requestJsonPerProvider = {};
  final Map<SttProvider, String> _schemaJsonPerProvider = {};

  bool _showApiKey = false;

  SttProviderConfig get _currentConfig => SttProviderConfig.get(_selectedProvider);

  @override
  void initState() {
    super.initState();
    _loadConfig();
  }

  void _loadConfig() {
    final config = SharedPreferencesUtil().customSttConfig;
    setState(() {
      _useCustomStt = config.isEnabled;
      _selectedProvider = config.provider == SttProvider.omi ? SttProvider.openai : config.provider;

      // Load stored API keys per provider from preferences
      _loadStoredApiKeys();

      // Set current provider's API key
      _apiKeyController.text = _apiKeysPerProvider[_selectedProvider] ?? '';
      _hostController.text = config.host ?? '127.0.0.1';
      _portController.text = (config.port ?? 8080).toString();

      // Initialize JSON configs for all providers with templates
      _initializeJsonConfigs();
    });
  }

  void _loadStoredApiKeys() {
    for (final provider in SttProvider.values) {
      if (provider != SttProvider.omi && provider != SttProvider.localWhisper && provider != SttProvider.custom) {
        final storedKey = SharedPreferencesUtil().getString('stt_api_key_${provider.name}');
        if (storedKey.isNotEmpty) {
          _apiKeysPerProvider[provider] = storedKey;
        }
      }
    }
  }

  void _initializeJsonConfigs() {
    for (final config in SttProviderConfig.allProviders) {
      final template = CustomSttConfig.getFullTemplateJson(config.provider);
      _requestJsonPerProvider[config.provider] = const JsonEncoder.withIndent('  ').convert(template['request']);
      _schemaJsonPerProvider[config.provider] = const JsonEncoder.withIndent('  ').convert(template['response_schema']);
    }
  }

  void _loadTemplateForProvider(SttProvider provider) {
    final template = CustomSttConfig.getFullTemplateJson(provider);
    _requestJsonPerProvider[provider] = const JsonEncoder.withIndent('  ').convert(template['request']);
    _schemaJsonPerProvider[provider] = const JsonEncoder.withIndent('  ').convert(template['response_schema']);
  }

  String get _currentRequestJson => _requestJsonPerProvider[_selectedProvider] ?? '{}';
  String get _currentSchemaJson => _schemaJsonPerProvider[_selectedProvider] ?? '{}';

  void _saveApiKeyForCurrentProvider() {
    if (_apiKeyController.text.isNotEmpty) {
      _apiKeysPerProvider[_selectedProvider] = _apiKeyController.text;
      SharedPreferencesUtil().saveString('stt_api_key_${_selectedProvider.name}', _apiKeyController.text);
    }
  }

  void _validateAndSetError() {
    setState(() {
      if (!_useCustomStt) {
        _validationError = null;
        return;
      }

      if (_selectedProvider == SttProvider.localWhisper) {
        if (_hostController.text.isEmpty) {
          _validationError = 'Host is required';
          return;
        }
        if (_portController.text.isEmpty || int.tryParse(_portController.text) == null) {
          _validationError = 'Valid port is required';
          return;
        }
      } else if (_selectedProvider != SttProvider.custom) {
        if (_apiKeyController.text.isEmpty) {
          _validationError = 'API key is required';
          return;
        }
      }

      if (_showAdvanced) {
        try {
          if (_currentRequestJson.isNotEmpty) {
            jsonDecode(_currentRequestJson);
          }
          if (_currentSchemaJson.isNotEmpty) {
            jsonDecode(_currentSchemaJson);
          }
        } catch (e) {
          _validationError = 'Invalid JSON configuration';
          return;
        }
      }

      _validationError = null;
    });
  }

  Future<void> _saveConfig() async {
    _validateAndSetError();
    if (_validationError != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_validationError!), backgroundColor: Colors.red.shade700),
      );
      return;
    }

    setState(() => _isSaving = true);

    try {
      // Save current API key for this provider
      _saveApiKeyForCurrentProvider();

      Map<String, dynamic> requestJson = {};
      Map<String, dynamic> schemaJson = {};

      if (_showAdvanced && _currentRequestJson.isNotEmpty) {
        requestJson = jsonDecode(_currentRequestJson);
      }
      if (_showAdvanced && _currentSchemaJson.isNotEmpty) {
        schemaJson = jsonDecode(_currentSchemaJson);
      }

      if (!_showAdvanced && _apiKeyController.text.isNotEmpty && _currentConfig.requiresApiKey) {
        requestJson = _currentConfig.getRequestConfigWithApiKey(_apiKeyController.text);
      }

      if (_selectedProvider == SttProvider.localWhisper) {
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
      final configChanged = previousConfig.sttConfigId != config.sttConfigId;

      SharedPreferencesUtil().customSttConfig = config;

      if (configChanged && mounted) {
        await Provider.of<CaptureProvider>(context, listen: false).onTranscriptionSettingsChanged();
      }

      if (mounted) {
        Navigator.of(context).pop();
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error saving: $e'), backgroundColor: Colors.red.shade700),
      );
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        title: const Text('Transcription', style: TextStyle(fontWeight: FontWeight.w600)),
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, size: 20),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildSourceSelector(),
                  const SizedBox(height: 24),
                  if (_useCustomStt) ...[
                    _buildProviderSection(),
                    const SizedBox(height: 20),
                    _buildConfigSection(),
                    const SizedBox(height: 20),
                    _buildAdvancedSection(),
                  ] else ...[
                    _buildOmiFeatures(),
                  ],
                  const SizedBox(height: 100),
                ],
              ),
            ),
          ),
          _buildBottomBar(),
        ],
      ),
    );
  }

  Widget _buildSourceSelector() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Source',
          style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(child: _buildSourceOption(false, 'Omi')),
            const SizedBox(width: 10),
            Expanded(child: _buildSourceOption(true, 'Custom')),
          ],
        ),
      ],
    );
  }

  Widget _buildSourceOption(bool isCustom, String title) {
    final isSelected = _useCustomStt == isCustom;
    return GestureDetector(
      onTap: () => setState(() => _useCustomStt = isCustom),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white : const Color(0xFF1A1A1A),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.grey.shade800,
            width: 1,
          ),
        ),
        child: Center(
          child: Text(
            title,
            style: TextStyle(
              color: isSelected ? Colors.black : Colors.grey.shade400,
              fontSize: 15,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildProviderSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Provider',
          style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: const Color(0xFF1A1A1A),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.grey.shade800),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<SttProvider>(
              value: _selectedProvider,
              isExpanded: true,
              dropdownColor: const Color(0xFF1A1A1A),
              style: const TextStyle(color: Colors.white, fontSize: 15),
              icon: Icon(Icons.keyboard_arrow_down, color: Colors.grey.shade500),
              items: SttProviderConfig.allProviders.map((config) {
                return DropdownMenuItem<SttProvider>(
                  value: config.provider,
                  child: Text(config.displayName),
                );
              }).toList(),
              onChanged: (provider) {
                if (provider != null) {
                  // Save current API key before switching
                  _saveApiKeyForCurrentProvider();

                  setState(() {
                    _selectedProvider = provider;
                    // Load API key for new provider
                    _apiKeyController.text = _apiKeysPerProvider[provider] ?? '';
                    if (provider == SttProvider.custom) {
                      _showAdvanced = true;
                    }
                  });
                  _validateAndSetError();
                }
              },
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _currentConfig.description,
          style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
        ),
      ],
    );
  }

  Widget _buildConfigSection() {
    if (_selectedProvider == SttProvider.localWhisper) {
      return _buildLocalWhisperConfig();
    } else if (_selectedProvider == SttProvider.custom) {
      return const SizedBox.shrink();
    }
    return _buildApiKeyInput();
  }

  Widget _buildApiKeyInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'API Key',
          style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _apiKeyController,
          obscureText: !_showApiKey,
          style: const TextStyle(color: Colors.white, fontSize: 15),
          onChanged: (_) => _validateAndSetError(),
          decoration: InputDecoration(
            hintText: 'Enter your API key',
            hintStyle: TextStyle(color: Colors.grey.shade700),
            filled: true,
            fillColor: const Color(0xFF1A1A1A),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: BorderSide.none,
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: BorderSide(color: Colors.grey.shade800),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: const BorderSide(color: Colors.white),
            ),
            suffixIcon: IconButton(
              icon: Icon(
                _showApiKey ? Icons.visibility_off : Icons.visibility,
                color: Colors.grey.shade600,
                size: 20,
              ),
              onPressed: () => setState(() => _showApiKey = !_showApiKey),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Stored locally, never shared',
          style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
        ),
      ],
    );
  }

  Widget _buildLocalWhisperConfig() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              flex: 3,
              child: _buildTextField(
                controller: _hostController,
                label: 'Host',
                hint: '127.0.0.1',
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              flex: 2,
              child: _buildTextField(
                controller: _portController,
                label: 'Port',
                hint: '8080',
                keyboardType: TextInputType.number,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          'http://${_hostController.text}:${_portController.text}/inference',
          style: TextStyle(color: Colors.grey.shade600, fontSize: 12, fontFamily: 'monospace'),
        ),
      ],
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    required String hint,
    TextInputType? keyboardType,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(color: Colors.grey.shade500, fontSize: 13)),
        const SizedBox(height: 10),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          style: const TextStyle(color: Colors.white, fontSize: 15),
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: TextStyle(color: Colors.grey.shade700),
            filled: true,
            fillColor: const Color(0xFF1A1A1A),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: BorderSide.none,
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: BorderSide(color: Colors.grey.shade800),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: const BorderSide(color: Colors.white),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildAdvancedSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
          onTap: () => setState(() => _showAdvanced = !_showAdvanced),
          child: Row(
            children: [
              Text(
                'Advanced',
                style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
              ),
              const SizedBox(width: 8),
              Icon(
                _showAdvanced ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                color: Colors.grey.shade500,
                size: 18,
              ),
            ],
          ),
        ),
        if (_showAdvanced) ...[
          const SizedBox(height: 16),
          _buildJsonEditors(),
        ],
      ],
    );
  }

  Widget _buildJsonEditors() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildJsonEditorButton(
          title: 'Request Configuration',
          jsonContent: _currentRequestJson,
          onTap: () => _openJsonEditor(
            title: 'Request Configuration',
            jsonContent: _currentRequestJson,
            isRequest: true,
          ),
        ),
        const SizedBox(height: 12),
        _buildJsonEditorButton(
          title: 'Response Schema',
          jsonContent: _currentSchemaJson,
          onTap: () => _openJsonEditor(
            title: 'Response Schema',
            jsonContent: _currentSchemaJson,
            isRequest: false,
          ),
        ),
      ],
    );
  }

  Widget _buildJsonEditorButton({
    required String title,
    required String jsonContent,
    required VoidCallback onTap,
  }) {
    String preview = '';
    try {
      final parsed = jsonDecode(jsonContent);
      if (parsed is Map) {
        preview = parsed.keys.take(3).join(', ');
        if (parsed.keys.length > 3) preview += '...';
      }
    } catch (_) {
      preview = 'Invalid JSON';
    }

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF1A1A1A),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: Colors.grey.shade800),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    preview,
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 12, fontFamily: 'monospace'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right, color: Colors.grey.shade600),
          ],
        ),
      ),
    );
  }

  Future<void> _openJsonEditor({
    required String title,
    required String jsonContent,
    required bool isRequest,
  }) async {
    final result = await Navigator.of(context).push<String>(
      MaterialPageRoute(
        builder: (context) => _JsonEditorPage(
          title: title,
          initialJson: jsonContent,
          isRequest: isRequest,
          provider: _selectedProvider,
          onReset: () => CustomSttConfig.getFullTemplateJson(_selectedProvider)[isRequest ? 'request' : 'response_schema'],
        ),
      ),
    );

    if (result != null) {
      setState(() {
        if (isRequest) {
          _requestJsonPerProvider[_selectedProvider] = result;
        } else {
          _schemaJsonPerProvider[_selectedProvider] = result;
        }
      });
      _validateAndSetError();
    }
  }

  Widget _buildOmiFeatures() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Using Omi\'s built-in transcription optimized for conversations with automatic speaker detection.',
          style: TextStyle(color: Colors.grey.shade500, fontSize: 14, height: 1.5),
        ),
      ],
    );
  }

  Widget _buildBottomBar() {
    return Container(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 16,
        bottom: MediaQuery.of(context).padding.bottom + 16,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFF0D0D0D),
        border: Border(top: BorderSide(color: Colors.grey.shade900)),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          width: double.infinity,
          height: 50,
          child: ElevatedButton(
            onPressed: _isSaving ? null : _saveConfig,
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              disabledBackgroundColor: Colors.grey.shade800,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              elevation: 0,
            ),
            child: _isSaving
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black),
                  )
                : const Text(
                    'Save',
                    style: TextStyle(color: Colors.black, fontSize: 16, fontWeight: FontWeight.w600),
                  ),
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _apiKeyController.dispose();
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }
}

class _JsonEditorPage extends StatefulWidget {
  final String title;
  final String initialJson;
  final bool isRequest;
  final SttProvider provider;
  final Map<String, dynamic> Function() onReset;

  const _JsonEditorPage({
    required this.title,
    required this.initialJson,
    required this.isRequest,
    required this.provider,
    required this.onReset,
  });

  @override
  State<_JsonEditorPage> createState() => _JsonEditorPageState();
}

class _JsonEditorPageState extends State<_JsonEditorPage> with SingleTickerProviderStateMixin {
  late TextEditingController _controller;
  late TabController _tabController;
  String? _parseError;
  Map<String, dynamic>? _parsedJson;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialJson);
    _tabController = TabController(length: 2, vsync: this);
    _parseJson();
  }

  void _parseJson() {
    try {
      _parsedJson = jsonDecode(_controller.text);
      _parseError = null;
    } catch (e) {
      _parseError = e.toString();
      _parsedJson = null;
    }
    setState(() {});
  }

  void _resetToTemplate() {
    final template = widget.onReset();
    _controller.text = const JsonEncoder.withIndent('  ').convert(template);
    _parseJson();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        title: Text(widget.title, style: const TextStyle(fontWeight: FontWeight.w600)),
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, size: 20),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          TextButton(
            onPressed: _resetToTemplate,
            child: Text('Reset', style: TextStyle(color: Colors.grey.shade400)),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: Colors.white,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.grey.shade600,
          tabs: const [
            Tab(text: 'Edit'),
            Tab(text: 'Preview'),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: [
                _buildEditorTab(),
                _buildPreviewTab(),
              ],
            ),
          ),
          _buildBottomBar(),
        ],
      ),
    );
  }

  Widget _buildEditorTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_parseError != null)
            Container(
              margin: const EdgeInsets.only(bottom: 12),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.red.shade900.withOpacity(0.3),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.red.shade700),
              ),
              child: Row(
                children: [
                  Icon(Icons.error_outline, color: Colors.red.shade400, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Invalid JSON',
                      style: TextStyle(color: Colors.red.shade400, fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1A),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.grey.shade800),
              ),
              child: TextField(
                controller: _controller,
                maxLines: null,
                expands: true,
                style: const TextStyle(color: Colors.white, fontFamily: 'monospace', fontSize: 13),
                onChanged: (_) => _parseJson(),
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.all(16),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPreviewTab() {
    if (_parsedJson == null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, color: Colors.red.shade400, size: 48),
            const SizedBox(height: 16),
            Text(
              'Cannot preview invalid JSON',
              style: TextStyle(color: Colors.grey.shade500, fontSize: 15),
            ),
          ],
        ),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (widget.isRequest) ...[
            _buildPreviewSection('Request Structure', _buildRequestPreview()),
          ] else ...[
            _buildPreviewSection('Response Schema', _buildSchemaPreview()),
          ],
        ],
      ),
    );
  }

  Widget _buildPreviewSection(String title, Widget content) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(color: Colors.grey.shade500, fontSize: 13, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 12),
        content,
      ],
    );
  }

  Widget _buildRequestPreview() {
    final json = _parsedJson!;
    final method = (json['request_type'] ?? 'POST').toString().toUpperCase();
    final url = json['api_url']?.toString() ?? 'https://api.example.com/transcribe';
    final headers = json['headers'] as Map<String, dynamic>? ?? {};
    final fields = json['fields'] as Map<String, dynamic>? ?? {};
    final audioFieldName = json['audio_field_name']?.toString() ?? 'file';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade800),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Request line
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xFF0D0D0D),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade800,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    method,
                    style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold, fontFamily: 'monospace'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    url,
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 13, fontFamily: 'monospace'),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Headers section
          if (headers.isNotEmpty) ...[
            Text('Headers', style: TextStyle(color: Colors.grey.shade500, fontSize: 12, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF0D0D0D),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: headers.entries.map((e) {
                  final value = e.value.toString().contains('API_KEY') 
                      ? 'Bearer ••••••••••••••••' 
                      : e.value.toString();
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      '${e.key}: $value',
                      style: TextStyle(fontFamily: 'monospace', fontSize: 12, color: Colors.grey.shade400),
                    ),
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 16),
          ],

          // Body section
          Text('Body (multipart/form-data)', style: TextStyle(color: Colors.grey.shade500, fontSize: 12, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFF0D0D0D),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Audio file field
                Text(
                  '$audioFieldName: <audio.wav>',
                  style: TextStyle(fontFamily: 'monospace', fontSize: 12, color: Colors.grey.shade400),
                ),
                // Other form fields
                ...fields.entries.map((e) => Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    '${e.key}: ${e.value}',
                    style: TextStyle(fontFamily: 'monospace', fontSize: 12, color: Colors.grey.shade400),
                  ),
                )),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSchemaPreview() {
    final json = _parsedJson!;
    
    // Build example JSON response based on schema
    final exampleResponse = _buildExampleResponseJson(json);
    final prettyJson = const JsonEncoder.withIndent('  ').convert(exampleResponse);
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Schema mapping info
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFF1A1A1A),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.grey.shade800),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Path Mappings', style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w600)),
              const SizedBox(height: 12),
              if (json['segments_path'] != null) 
                _buildSchemaRow('Segments', json['segments_path'].toString()),
              if (json['text_field'] != null) 
                _buildSchemaRow('Text Field', json['text_field'].toString()),
              if (json['start_field'] != null) 
                _buildSchemaRow('Start Time', json['start_field'].toString()),
              if (json['end_field'] != null) 
                _buildSchemaRow('End Time', json['end_field'].toString()),
              if (json['speaker_field'] != null) 
                _buildSchemaRow('Speaker', json['speaker_field'].toString()),
              if (json['raw_text_path'] != null) 
                _buildSchemaRow('Raw Text', json['raw_text_path'].toString()),
              if (json['language_path'] != null) 
                _buildSchemaRow('Language', json['language_path'].toString()),
              if (json['duration_path'] != null) 
                _buildSchemaRow('Duration', json['duration_path'].toString()),
            ],
          ),
        ),
        const SizedBox(height: 16),
        
        // Example JSON response
        Text('Example Response', style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFF1A1A1A),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.grey.shade800),
          ),
          child: _buildSyntaxHighlightedJson(prettyJson),
        ),
      ],
    );
  }

  Widget _buildSchemaRow(String label, String path) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 80,
            child: Text(
              label,
              style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              path,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 12, fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }

  Map<String, dynamic> _buildExampleResponseJson(Map<String, dynamic> schema) {
    final result = <String, dynamic>{};
    
    // Build segments structure based on segments_path
    final segmentsPath = schema['segments_path'] as String?;
    final textField = schema['text_field'] as String? ?? 'text';
    final startField = schema['start_field'] as String?;
    final endField = schema['end_field'] as String?;
    final speakerField = schema['speaker_field'] as String?;
    final confidenceField = schema['confidence_field'] as String?;
    
    // Build example segment
    final exampleSegment = <String, dynamic>{};
    exampleSegment[textField] = 'Hello, this is a sample transcription.';
    if (startField != null) exampleSegment[startField] = 0.0;
    if (endField != null) exampleSegment[endField] = 2.5;
    if (speakerField != null) exampleSegment[speakerField] = 'SPEAKER_00';
    if (confidenceField != null) exampleSegment[confidenceField] = 0.95;

    // Build nested structure based on path
    if (segmentsPath != null && segmentsPath.isNotEmpty) {
      _setNestedValue(result, segmentsPath, [exampleSegment]);
    }

    // Add raw text path
    final rawTextPath = schema['raw_text_path'] as String?;
    if (rawTextPath != null) {
      _setNestedValue(result, rawTextPath, 'Hello, this is a sample transcription.');
    }

    // Add language path
    final languagePath = schema['language_path'] as String?;
    if (languagePath != null) {
      _setNestedValue(result, languagePath, 'en');
    }

    // Add duration path
    final durationPath = schema['duration_path'] as String?;
    if (durationPath != null) {
      _setNestedValue(result, durationPath, 2.5);
    }

    return result;
  }

  void _setNestedValue(Map<String, dynamic> obj, String path, dynamic value) {
    // Parse path like "results.channels[0].alternatives[0].words"
    final parts = <String>[];
    final regex = RegExp(r'([^\.\[\]]+)|\[(\d+)\]');
    
    for (final match in regex.allMatches(path)) {
      if (match.group(1) != null) {
        parts.add(match.group(1)!);
      } else if (match.group(2) != null) {
        parts.add('[${match.group(2)}]');
      }
    }

    dynamic current = obj;
    for (int i = 0; i < parts.length - 1; i++) {
      final part = parts[i];
      final nextPart = parts[i + 1];
      
      if (part.startsWith('[')) {
        // Array index - skip for now in simple preview
        continue;
      }
      
      if (current is Map<String, dynamic>) {
        if (!current.containsKey(part)) {
          if (nextPart.startsWith('[')) {
            current[part] = <dynamic>[];
          } else {
            current[part] = <String, dynamic>{};
          }
        }
        
        if (nextPart.startsWith('[') && current[part] is List) {
          if ((current[part] as List).isEmpty) {
            current[part].add(<String, dynamic>{});
          }
          current = current[part][0];
        } else {
          current = current[part];
        }
      }
    }

    final lastPart = parts.last;
    if (!lastPart.startsWith('[') && current is Map<String, dynamic>) {
      current[lastPart] = value;
    }
  }

  Widget _buildSyntaxHighlightedJson(String json) {
    return Text(
      json,
      style: TextStyle(fontFamily: 'monospace', fontSize: 12, height: 1.4, color: Colors.grey.shade400),
    );
  }

  Widget _buildPreviewRow(String label, String value, {bool indent = false}) {
    return Padding(
      padding: EdgeInsets.only(left: indent ? 12 : 0, bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: indent ? 100 : 120,
            child: Text(
              label,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(color: Colors.white, fontSize: 13, fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomBar() {
    return Container(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 16,
        bottom: MediaQuery.of(context).padding.bottom + 16,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFF0D0D0D),
        border: Border(top: BorderSide(color: Colors.grey.shade900)),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          width: double.infinity,
          height: 50,
          child: ElevatedButton(
            onPressed: _parseError != null ? null : () => Navigator.of(context).pop(_controller.text),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              disabledBackgroundColor: Colors.grey.shade800,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              elevation: 0,
            ),
            child: const Text(
              'Save',
              style: TextStyle(color: Colors.black, fontSize: 16, fontWeight: FontWeight.w600),
            ),
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    _tabController.dispose();
    super.dispose();
  }
}
