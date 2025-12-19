import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/custom_stt_log_service.dart';
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
  bool _showLogs = true;
  bool _isSaving = false;
  Timer? _logRefreshTimer;
  String? _validationError;

  // Device codec compatibility
  BleAudioCodec? _connectedDeviceCodec;
  String? _connectedDeviceName;

  // Store complete config per provider
  final Map<SttProvider, CustomSttConfig> _configsPerProvider = {};

  final TextEditingController _apiKeyController = TextEditingController();
  final TextEditingController _hostController = TextEditingController(text: '127.0.0.1');
  final TextEditingController _portController = TextEditingController(text: '8080');
  final TextEditingController _urlController = TextEditingController(text: '');

  // Store JSON configs per provider (for editing UI)
  final Map<SttProvider, String> _requestJsonPerProvider = {};
  final Map<SttProvider, String> _schemaJsonPerProvider = {};
  final Map<SttProvider, bool> _requestJsonCustomized = {};

  // Version counter to force autocomplete rebuild after JSON edits
  int _configSyncVersion = 0;

  bool _showApiKey = false;

  SttProviderConfig get _currentConfig => SttProviderConfig.get(_selectedProvider);
  CustomSttConfig? get _currentProviderConfig => _configsPerProvider[_selectedProvider];
  String get _currentLanguage => _currentProviderConfig?.language ?? _currentConfig.defaultLanguage;
  String get _currentModel => _currentProviderConfig?.model ?? _currentConfig.defaultModel;
  String get _currentRequestJson => _requestJsonPerProvider[_selectedProvider] ?? '{}';
  String get _currentSchemaJson => _schemaJsonPerProvider[_selectedProvider] ?? '{}';

  @override
  void initState() {
    super.initState();
    _loadConfig();
    _checkConnectedDevice();
    _startLogRefreshTimer();
  }

  void _startLogRefreshTimer() {
    _logRefreshTimer?.cancel();
    _logRefreshTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (_showLogs && mounted) {
        setState(() {});
      }
    });
  }

  Future<void> _checkConnectedDevice() async {
    final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
    if (captureProvider.havingRecordingDevice) {
      try {
        final device = captureProvider.recordingDevice;
        if (device != null) {
          final connection = await ServiceManager.instance().device.ensureConnection(device.id);
          if (connection != null && mounted) {
            final codec = await connection.getAudioCodec();
            setState(() {
              _connectedDeviceCodec = codec;
              _connectedDeviceName = device.name;
            });
          }
        }
      } catch (e) {
        debugPrint('Error checking device codec: $e');
      }
    }
  }

  bool get _isCodecCompatible {
    if (_connectedDeviceCodec == null) return true;
    return TranscriptSocketServiceFactory.isCodecSupportedForCustomStt(_connectedDeviceCodec!);
  }

  void _loadConfig() {
    final activeConfig = SharedPreferencesUtil().customSttConfig;
    setState(() {
      _useCustomStt = activeConfig.isEnabled;
      _selectedProvider = activeConfig.provider == SttProvider.omi ? SttProvider.openai : activeConfig.provider;

      // Load all provider configs from preferences
      _loadAllProviderConfigs();

      // If current provider has no saved config but active config matches, use it
      if (_configsPerProvider[_selectedProvider] == null && activeConfig.provider == _selectedProvider) {
        _configsPerProvider[_selectedProvider] = activeConfig;
      }

      // Populate UI from current provider's config
      _populateUIFromConfig(_configsPerProvider[_selectedProvider]);

      // Initialize JSON configs for all providers
      _initializeJsonConfigs();

      // Auto-expand advanced if current provider has modified configs
      if (_requestJsonCustomized[_selectedProvider] == true) {
        _showAdvanced = true;
      }
    });
  }

  void _loadAllProviderConfigs() {
    for (final provider in SttProvider.values) {
      if (provider != SttProvider.omi) {
        final savedConfig = SharedPreferencesUtil().getConfigForProvider(provider);
        if (savedConfig != null) {
          _configsPerProvider[provider] = savedConfig;
        }
      }
    }
  }

  void _populateUIFromConfig(CustomSttConfig? config) {
    final providerDefaults = SttProviderConfig.get(_selectedProvider);

    _apiKeyController.text = config?.apiKey ?? '';
    _hostController.text = config?.host ?? '127.0.0.1';
    _portController.text = (config?.port ?? 8080).toString();
    _urlController.text = config?.url ?? '';

    // Restore JSON configs if customized
    if (config != null) {
      final hasCustomRequest = config.requestType != null ||
          config.headers != null ||
          config.params != null ||
          config.audioFieldName != null;

      if (hasCustomRequest) {
        final defaults = providerDefaults.buildRequestConfig(
          apiKey: config.apiKey,
          language: config.language ?? providerDefaults.defaultLanguage,
          model: config.model ?? providerDefaults.defaultModel,
        );

        final requestConfig = <String, dynamic>{};
        requestConfig['url'] = config.url ?? defaults['url'];
        requestConfig['request_type'] = config.requestType ?? defaults['request_type'];
        requestConfig['headers'] = config.headers ?? defaults['headers'];
        requestConfig['params'] = config.params ?? defaults['params'];
        if (config.audioFieldName != null || defaults['audio_field_name'] != null) {
          requestConfig['audio_field_name'] = config.audioFieldName ?? defaults['audio_field_name'];
        }

        _requestJsonPerProvider[_selectedProvider] = const JsonEncoder.withIndent('  ').convert(requestConfig);
        _requestJsonCustomized[_selectedProvider] = true;
      }

      if (config.schemaJson != null) {
        _schemaJsonPerProvider[_selectedProvider] = const JsonEncoder.withIndent('  ').convert(config.schemaJson);
      }
    }
  }

  void _initializeJsonConfigs() {
    // Initialize JSON configs for all providers
    for (final config in SttProviderConfig.allProviders) {
      // Skip if already loaded as customized (from _populateUIFromConfig)
      if (_requestJsonCustomized[config.provider] != true) {
        _regenerateRequestJson(config.provider);
        _requestJsonCustomized[config.provider] = false;
      }
      // Only set schema if not already set
      if (_schemaJsonPerProvider[config.provider] == null) {
        final template = CustomSttConfig.getFullTemplateJson(config.provider);
        _schemaJsonPerProvider[config.provider] = const JsonEncoder.withIndent('  ').convert(template['response_schema']);
      }
    }
  }

  void _regenerateRequestJson(SttProvider provider) {
    final providerDefaults = SttProviderConfig.get(provider);
    final savedConfig = _configsPerProvider[provider];

    final apiKey = savedConfig?.apiKey ?? _apiKeyController.text;
    final language = savedConfig?.language ?? providerDefaults.defaultLanguage;
    final model = savedConfig?.model ?? providerDefaults.defaultModel;
    final host = savedConfig?.host ?? _hostController.text;
    final port = savedConfig?.port ?? int.tryParse(_portController.text);

    final requestConfig = providerDefaults.buildRequestConfig(
      apiKey: apiKey,
      language: language,
      model: model,
      host: host,
      port: port,
    );
    _requestJsonPerProvider[provider] = const JsonEncoder.withIndent('  ').convert(requestConfig);
  }

  void _onLanguageOrModelChanged(String? newLanguage, String? newModel) {
    // Update the stored config with new language/model
    _updateCurrentProviderConfig(language: newLanguage, model: newModel);

    // Only regenerate JSON if user hasn't customized it
    if (_requestJsonCustomized[_selectedProvider] != true) {
      _regenerateRequestJson(_selectedProvider);
    }
  }

  void _updateCurrentProviderConfig({
    String? apiKey,
    String? language,
    String? model,
    String? url,
    String? host,
    int? port,
  }) {
    final current = _configsPerProvider[_selectedProvider];
    final providerDefaults = SttProviderConfig.get(_selectedProvider);

    _configsPerProvider[_selectedProvider] = CustomSttConfig(
      provider: _selectedProvider,
      apiKey: apiKey ?? current?.apiKey ?? _apiKeyController.text,
      language: language ?? current?.language ?? providerDefaults.defaultLanguage,
      model: model ?? current?.model ?? providerDefaults.defaultModel,
      url: url ?? current?.url ?? _urlController.text,
      host: host ?? current?.host ?? _hostController.text,
      port: port ?? current?.port ?? int.tryParse(_portController.text),
      requestType: current?.requestType,
      headers: current?.headers,
      params: current?.params,
      audioFieldName: current?.audioFieldName,
      schemaJson: current?.schemaJson,
    );
  }

  Future<void> _saveCurrentProviderConfig() async {
    // Build complete config from current UI state
    final config = _buildCurrentConfig();
    _configsPerProvider[_selectedProvider] = config;
    await SharedPreferencesUtil().saveConfigForProvider(_selectedProvider, config);
  }

  CustomSttConfig _buildCurrentConfig() {
    Map<String, dynamic>? requestJson;
    Map<String, dynamic>? schemaJson;

    if (_showAdvanced && _currentRequestJson.isNotEmpty) {
      try {
        requestJson = jsonDecode(_currentRequestJson);
      } catch (_) {}
    }
    if (_showAdvanced && _currentSchemaJson.isNotEmpty) {
      try {
        schemaJson = jsonDecode(_currentSchemaJson);
      } catch (_) {}
    }

    // Extract values from request JSON if customized
    String? url;
    String? requestType;
    Map<String, String>? headers;
    Map<String, String>? params;
    String? audioFieldName;

    if (requestJson != null && _requestJsonCustomized[_selectedProvider] == true) {
      url = requestJson['url'];
      requestType = requestJson['request_type'];
      headers = requestJson['headers'] != null ? Map<String, String>.from(requestJson['headers']) : null;
      params = requestJson['params'] != null ? Map<String, String>.from(requestJson['params']) : null;
      audioFieldName = requestJson['audio_field_name'];
    }

    // Use URL from text field for custom providers
    if (_selectedProvider == SttProvider.custom || _selectedProvider == SttProvider.customLive) {
      url = _urlController.text.isNotEmpty ? _urlController.text : url;
    }

    final current = _configsPerProvider[_selectedProvider];
    final providerDefaults = SttProviderConfig.get(_selectedProvider);

    return CustomSttConfig(
      provider: _selectedProvider,
      apiKey: _apiKeyController.text.isNotEmpty ? _apiKeyController.text : null,
      language: current?.language ?? providerDefaults.defaultLanguage,
      model: current?.model ?? providerDefaults.defaultModel,
      url: url,
      host: _selectedProvider == SttProvider.localWhisper ? _hostController.text : null,
      port: _selectedProvider == SttProvider.localWhisper ? int.tryParse(_portController.text) : null,
      requestType: requestType,
      headers: headers,
      params: params,
      audioFieldName: audioFieldName,
      schemaJson: schemaJson,
    );
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
      } else if (_selectedProvider == SttProvider.customLive) {
        if (_urlController.text.isEmpty || !_urlController.text.startsWith('wss://')) {
          _validationError = 'Valid WebSocket URL is required (wss://)';
          return;
        }
      } else if (_selectedProvider == SttProvider.custom) {
        if (_urlController.text.isEmpty) {
          _validationError = 'API URL is required';
          return;
        }
      } else if (_selectedProvider != SttProvider.custom) {
        if (_currentConfig.requiresApiKey && _apiKeyController.text.isEmpty) {
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

  Future<void> _launchUrl(String url) async {
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
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
      // Save current provider's complete config
      await _saveCurrentProviderConfig();

      // Build the active config (with correct provider based on _useCustomStt)
      final currentConfig = _buildCurrentConfig();
      final activeConfig = _useCustomStt ? currentConfig : CustomSttConfig(provider: SttProvider.omi);

      final previousConfig = SharedPreferencesUtil().customSttConfig;
      final configChanged = previousConfig.sttConfigId != activeConfig.sttConfigId;

      await SharedPreferencesUtil().saveCustomSttConfig(activeConfig);
      debugPrint(SharedPreferencesUtil().customSttConfig.provider.toString());

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

  Future<void> _exportConfig() async {
    final config = _buildCurrentConfig();
    
    // Build exportable config (exclude sensitive API key)
    final exportableConfig = <String, dynamic>{
      'provider': config.provider.name,
      'language': config.language ?? _currentConfig.defaultLanguage,
      'model': config.model ?? _currentConfig.defaultModel,
      if (config.url != null) 'url': config.url,
      if (config.host != null) 'host': config.host,
      if (config.port != null) 'port': config.port,
      if (config.requestType != null) 'request_type': config.requestType,
      if (config.headers != null) 'headers': _sanitizeHeaders(config.headers!),
      if (config.params != null) 'params': config.params,
      if (config.audioFieldName != null) 'audio_field_name': config.audioFieldName,
      if (config.schemaJson != null) 'schema': config.schemaJson,
    };

    final jsonString = const JsonEncoder.withIndent('  ').convert(exportableConfig);
    
    await Clipboard.setData(ClipboardData(text: jsonString));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Configuration copied to clipboard'),
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  Map<String, String> _sanitizeHeaders(Map<String, String> headers) {
    // Remove or mask sensitive header values
    return headers.map((key, value) {
      final lowerKey = key.toLowerCase();
      if (lowerKey == 'authorization' || lowerKey.contains('api') || lowerKey.contains('key')) {
        return MapEntry(key, '<YOUR_API_KEY>');
      }
      return MapEntry(key, value);
    });
  }

  Future<void> _importConfig() async {
    final controller = TextEditingController();
    
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A1A),
        title: const Text(
          'Import Configuration',
          style: TextStyle(color: Colors.white, fontSize: 18),
        ),
        content: SizedBox(
          width: double.maxFinite,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Paste your JSON configuration below:',
                style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
              ),
              const SizedBox(height: 12),
              Container(
                height: 200,
                decoration: BoxDecoration(
                  color: const Color(0xFF0D0D0D),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.grey.shade800),
                ),
                child: TextField(
                  controller: controller,
                  maxLines: null,
                  expands: true,
                  style: const TextStyle(
                    color: Colors.white,
                    fontFamily: 'monospace',
                    fontSize: 12,
                  ),
                  decoration: InputDecoration(
                    hintText: '{\n  "provider": "deepgramLive",\n  ...\n}',
                    hintStyle: TextStyle(color: Colors.grey.shade700),
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.all(12),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.info_outline, size: 14, color: Colors.grey.shade600),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'You\'ll need to add your own API key after importing',
                      style: TextStyle(color: Colors.grey.shade600, fontSize: 11),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel', style: TextStyle(color: Colors.grey.shade400)),
          ),
          TextButton(
            onPressed: () async {
              final clipboardData = await Clipboard.getData(Clipboard.kTextPlain);
              if (clipboardData?.text != null) {
                controller.text = clipboardData!.text!;
              }
            },
            child: const Text('Paste', style: TextStyle(color: Colors.white)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('Import', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (result != null && result.isNotEmpty) {
      _parseAndApplyConfig(result);
    }
  }

  void _parseAndApplyConfig(String jsonString) {
    try {
      final json = jsonDecode(jsonString) as Map<String, dynamic>;
      final config = CustomSttConfig.fromJson(json);
      
      // Validate provider
      if (config.provider == SttProvider.omi) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Invalid provider in configuration'),
            backgroundColor: Colors.red.shade700,
          ),
        );
        return;
      }

      setState(() {
        _selectedProvider = config.provider;
        _configsPerProvider[_selectedProvider] = config;
        
        // Update UI fields
        _apiKeyController.text = config.apiKey ?? '';
        _urlController.text = config.url ?? '';
        _hostController.text = config.host ?? '127.0.0.1';
        _portController.text = (config.port ?? 8080).toString();
        
        // Update JSON configs
        if (config.requestType != null || config.headers != null || config.params != null) {
          final requestConfig = <String, dynamic>{};
          if (config.url != null) requestConfig['url'] = config.url;
          if (config.requestType != null) requestConfig['request_type'] = config.requestType;
          if (config.headers != null) requestConfig['headers'] = config.headers;
          if (config.params != null) requestConfig['params'] = config.params;
          if (config.audioFieldName != null) requestConfig['audio_field_name'] = config.audioFieldName;
          
          _requestJsonPerProvider[_selectedProvider] = const JsonEncoder.withIndent('  ').convert(requestConfig);
          _requestJsonCustomized[_selectedProvider] = true;
        } else {
          _regenerateRequestJson(_selectedProvider);
          _requestJsonCustomized[_selectedProvider] = false;
        }
        
        if (config.schemaJson != null) {
          _schemaJsonPerProvider[_selectedProvider] = const JsonEncoder.withIndent('  ').convert(config.schemaJson);
        }
        
        _configSyncVersion++;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Imported ${SttProviderConfig.get(_selectedProvider).displayName} configuration'),
          duration: const Duration(seconds: 2),
        ),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Invalid JSON: ${e.toString().split('\n').first}'),
          backgroundColor: Colors.red.shade700,
        ),
      );
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
        actions: [
          if (_useCustomStt) ...[
            IconButton(
              icon: const Icon(Icons.file_download_outlined, size: 20),
              tooltip: 'Import configuration',
              onPressed: _importConfig,
            ),
            IconButton(
              icon: const Icon(Icons.file_upload_outlined, size: 20),
              tooltip: 'Export configuration',
              onPressed: _exportConfig,
            ),
          ],
        ],
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
                    const SizedBox(height: 10),
                    _buildAdvancedSection(),
                    _buildLogsSection(),
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
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(child: _buildSourceOption(false, 'Omi')),
            const SizedBox(width: 10),
            Expanded(child: _buildSourceOption(true, 'Bring your own')),
          ],
        ),
        const SizedBox(height: 12),
        if (_useCustomStt)
          Text(
            'Freely use omi. You only pay your STT provider directly.',
            style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
          )
        else
          GestureDetector(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (context) => const UsagePage(showUpgradeDialog: true)),
            ),
            child: Text.rich(
              TextSpan(
                children: [
                  TextSpan(
                    text: '1,200 free minutes/month included. Unlimited with ',
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
                  ),
                  TextSpan(
                    text: 'Omi Unlimited',
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 12,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                  TextSpan(
                    text: '.',
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildSourceOption(bool isCustom, String title) {
    final isSelected = _useCustomStt == isCustom;
    return GestureDetector(
      onTap: () {
        if (_useCustomStt == isCustom) return;

        setState(() => _useCustomStt = isCustom);

        // Track source selection: 'omi' vs 'custom'
        MixpanelManager().transcriptionSourceSelected(
          source: isCustom ? 'custom' : 'omi',
        );
      },
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
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                title,
                style: TextStyle(
                  color: isSelected ? Colors.black : Colors.grey.shade400,
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCodecWarning() {
    if (_isCodecCompatible || !_useCustomStt) return const SizedBox.shrink();

    final codecReason = _connectedDeviceCodec?.customSttUnsupportedReason ?? 'unsupported format';
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Icon(Icons.warning_amber_rounded, color: Colors.orange.shade700, size: 14),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              '${_connectedDeviceName ?? 'Device'} uses $codecReason. Omi will be used.',
              style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProviderSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildCodecWarning(),
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
              items: [
                ...SttProviderConfig.allProviders.map((config) {
                  return DropdownMenuItem<SttProvider>(
                    value: config.provider,
                    child: Row(
                      children: [
                        Expanded(child: Text(config.displayName)),
                        if (config.isLive)
                          Container(
                            margin: const EdgeInsets.only(left: 8),
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.green.withOpacity(0.2),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: const Text(
                              'Live',
                              style: TextStyle(
                                color: Colors.green,
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                      ],
                    ),
                  );
                }),
                DropdownMenuItem<SttProvider>(
                  value: null,
                  enabled: false,
                  child: Row(
                    children: [
                      const Expanded(child: Text('On Device')),
                      Container(
                        margin: const EdgeInsets.only(left: 8),
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        child: Text(
                          'Coming Soon',
                          style: TextStyle(
                            color: Colors.orange.withOpacity(0.5),
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              onChanged: (provider) async {
                if (provider != null) {
                  // Save current provider's complete config before switching
                  await _saveCurrentProviderConfig();

                  setState(() {
                    _selectedProvider = provider;

                    // Load saved config for new provider
                    _populateUIFromConfig(_configsPerProvider[provider]);

                    // Regenerate JSON if not customized
                    if (_requestJsonCustomized[provider] != true) {
                      _regenerateRequestJson(provider);
                    }

                    // Auto-expand advanced if provider has custom config or is custom type
                    if (provider == SttProvider.custom || _requestJsonCustomized[provider] == true) {
                      _showAdvanced = true;
                    }
                  });

                  // Track which provider was selected (name only, no keys/URLs)
                  MixpanelManager().transcriptionProviderSelected(
                    provider: provider.name,
                  );

                  _validateAndSetError();
                }
              },
            ),
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: Text(
                _currentConfig.description,
                style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
              ),
            ),
            if (_currentConfig.docsUrl != null)
              GestureDetector(
                onTap: () => _launchUrl(_currentConfig.docsUrl!),
                child: Icon(Icons.open_in_new, color: Colors.grey.shade500, size: 14),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildConfigSection() {
    if (_selectedProvider == SttProvider.localWhisper) {
      return _buildLocalWhisperConfig();
    } else if (_selectedProvider == SttProvider.custom) {
      return _buildCustomPollingConfig();
    } else if (_selectedProvider == SttProvider.customLive) {
      return _buildCustomLiveConfig();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildApiKeyInput(),
        const SizedBox(height: 20),
        _buildLanguageSelector(),
      ],
    );
  }

  Widget _buildLanguageSelector() {
    final languages = _currentConfig.supportedLanguages;
    final suggestions = languages.map((lang) {
      final name = SttLanguages.common[lang];
      return name != null ? '$lang ($name)' : lang;
    }).toList();

    return _buildAutocompleteField(
      label: 'Language',
      hint: 'en (English)',
      value: _formatLanguageDisplay(_currentLanguage),
      suggestions: suggestions,
      onChanged: (value) {
        // Extract language code from "en (English)" format
        final code = value.split(' ').first.trim();
        setState(() {
          _onLanguageOrModelChanged(code, null);
        });
      },
    );
  }

  Widget _buildModelSelector() {
    final models = _currentConfig.supportedModels;

    return _buildAutocompleteField(
      label: 'Model',
      hint: _currentConfig.defaultModel,
      value: _currentModel,
      suggestions: models,
      onChanged: (value) {
        setState(() {
          _onLanguageOrModelChanged(null, value.trim());
        });
      },
    );
  }

  String _formatLanguageDisplay(String code) {
    final name = SttLanguages.common[code];
    return name != null ? '$code ($name)' : code;
  }

  Widget _buildAutocompleteField({
    required String label,
    required String hint,
    required String value,
    required List<String> suggestions,
    required ValueChanged<String> onChanged,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(color: Colors.grey.shade500, fontSize: 13)),
        const SizedBox(height: 10),
        Autocomplete<String>(
          key: ValueKey('${_selectedProvider.name}_${label}_$_configSyncVersion'),
          initialValue: TextEditingValue(text: value),
          optionsBuilder: (TextEditingValue textEditingValue) {
            if (textEditingValue.text.isEmpty) {
              return suggestions;
            }
            return suggestions.where((option) => option.toLowerCase().contains(textEditingValue.text.toLowerCase()));
          },
          optionsViewBuilder: (context, onSelected, options) {
            return Align(
              alignment: Alignment.topLeft,
              child: Material(
                elevation: 4,
                color: const Color(0xFF1A1A1A),
                borderRadius: BorderRadius.circular(10),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 200, maxWidth: 300),
                  child: ListView.builder(
                    padding: EdgeInsets.zero,
                    shrinkWrap: true,
                    itemCount: options.length,
                    itemBuilder: (context, index) {
                      final option = options.elementAt(index);
                      return ListTile(
                        dense: true,
                        title: Text(option, style: const TextStyle(color: Colors.white, fontSize: 14)),
                        onTap: () => onSelected(option),
                      );
                    },
                  ),
                ),
              ),
            );
          },
          fieldViewBuilder: (context, controller, focusNode, onFieldSubmitted) {
            return TextField(
              controller: controller,
              focusNode: focusNode,
              style: const TextStyle(color: Colors.white, fontSize: 15),
              onChanged: onChanged,
              onSubmitted: (_) => onFieldSubmitted(),
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
            );
          },
          onSelected: onChanged,
        ),
      ],
    );
  }

  Widget _buildCustomPollingConfig() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildTextField(
          controller: _urlController,
          label: 'API URL',
          hint: 'https://your-stt-api.com/transcribe',
        ),
        const SizedBox(height: 8),
        Text(
          'Enter your STT HTTP endpoint',
          style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
        ),
      ],
    );
  }

  Widget _buildCustomLiveConfig() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildTextField(
          controller: _urlController,
          label: 'WebSocket URL',
          hint: 'wss://your-stt-api.com/live',
        ),
        const SizedBox(height: 8),
        Text(
          'Enter your live STT WebSocket endpoint',
          style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
        ),
      ],
    );
  }

  Widget _buildApiKeyInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              'API Key',
              style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
            ),
            const Spacer(),
            if (_currentConfig.apiKeyUrl != null)
              GestureDetector(
                onTap: () => _launchUrl(_currentConfig.apiKeyUrl!),
                child: Icon(Icons.open_in_new, color: Colors.grey.shade500, size: 14),
              ),
          ],
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
        const SizedBox(height: 20),
        _buildLanguageSelector(),
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
    // Show advanced section for all providers except Omi
    if (_selectedProvider == SttProvider.omi) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => setState(() => _showAdvanced = !_showAdvanced),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
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
                const Spacer(),
              ],
            ),
          ),
        ),
        if (_showAdvanced) ...[
          const SizedBox(height: 4),
          if (_currentConfig.supportedModels.isNotEmpty) ...[
            _buildModelSelector(),
            const SizedBox(height: 16),
          ],
          _buildJsonEditors(),
          if (_requestJsonCustomized[_selectedProvider] == true) ...[
            const SizedBox(height: 12),
            _buildResetToDefaultButton(),
          ],
        ],
      ],
    );
  }

  Widget _buildJsonEditors() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Configuration',
          style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
        ),
        const SizedBox(height: 10),
        _buildJsonEditorButton(
          title: 'Request Configuration',
          jsonContent: _currentRequestJson,
          isCustomized: _requestJsonCustomized[_selectedProvider] == true,
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

  Widget _buildResetToDefaultButton() {
    return GestureDetector(
      onTap: () {
        setState(() {
          _requestJsonCustomized[_selectedProvider] = false;
          // Clear customized request fields from stored config
          final current = _configsPerProvider[_selectedProvider];
          if (current != null) {
            _configsPerProvider[_selectedProvider] = CustomSttConfig(
              provider: _selectedProvider,
              apiKey: current.apiKey,
              language: current.language,
              model: current.model,
              url: current.url,
              host: current.host,
              port: current.port,
              // Clear the customized fields
              requestType: null,
              headers: null,
              params: null,
              audioFieldName: null,
              schemaJson: current.schemaJson,
            );
          }
          _regenerateRequestJson(_selectedProvider);
        });
      },
      child: Row(
        children: [
          Icon(Icons.refresh, color: Colors.grey.shade500, size: 16),
          const SizedBox(width: 6),
          Text(
            'Reset request config to default',
            style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
          ),
        ],
      ),
    );
  }

  Widget _buildJsonEditorButton({
    required String title,
    required String jsonContent,
    required VoidCallback onTap,
    bool isCustomized = false,
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
          border: Border.all(color: isCustomized ? Colors.white : Colors.grey.shade800),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        title,
                        style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                      ),
                      if (isCustomized) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.white.withOpacity(0.15),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'Modified',
                            style: TextStyle(color: Colors.white, fontSize: 10),
                          ),
                        ),
                      ],
                    ],
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
    bool isRequest = false,
  }) async {
    final result = await Navigator.of(context).push<String>(
      MaterialPageRoute(
        builder: (context) => _JsonEditorPage(
          title: title,
          initialJson: jsonContent,
          provider: _selectedProvider,
          isResponseSchema: !isRequest,
          onReset: () {
            if (isRequest) {
              final providerDefaults = SttProviderConfig.get(_selectedProvider);
              final savedConfig = _configsPerProvider[_selectedProvider];
              return providerDefaults.buildRequestConfig(
                apiKey: savedConfig?.apiKey ?? _apiKeyController.text,
                language: savedConfig?.language ?? providerDefaults.defaultLanguage,
                model: savedConfig?.model ?? providerDefaults.defaultModel,
              );
            }
            return CustomSttConfig.getFullTemplateJson(_selectedProvider)['response_schema'];
          },
        ),
      ),
    );

    if (result != null) {
      setState(() {
        if (isRequest) {
          _requestJsonPerProvider[_selectedProvider] = result;

          // Sync UI fields from edited JSON
          String? newLanguage;
          String? newModel;
          try {
            final parsed = jsonDecode(result) as Map<String, dynamic>;
            if (parsed['url'] != null) _urlController.text = parsed['url'].toString();
            if (parsed['params'] is Map) {
              final params = parsed['params'] as Map;
              if (params['language'] != null) newLanguage = params['language'].toString();
              if (params['model'] != null) newModel = params['model'].toString();
            }
          } catch (_) {}

          // Update stored config with values from JSON and force UI sync
          if (newLanguage != null || newModel != null) {
            _updateCurrentProviderConfig(language: newLanguage, model: newModel);
            // Increment version to force autocomplete widgets to rebuild with new values
            _configSyncVersion++;
          }

          // Mark as customized if it differs from auto-generated
          final providerDefaults = SttProviderConfig.get(_selectedProvider);
          final savedConfig = _configsPerProvider[_selectedProvider];
          final autoGenerated = providerDefaults.buildRequestConfig(
            apiKey: savedConfig?.apiKey ?? _apiKeyController.text,
            language: savedConfig?.language ?? providerDefaults.defaultLanguage,
            model: savedConfig?.model ?? providerDefaults.defaultModel,
          );
          final autoGeneratedJson = const JsonEncoder.withIndent('  ').convert(autoGenerated);
          _requestJsonCustomized[_selectedProvider] = result != autoGeneratedJson;
        } else {
          _schemaJsonPerProvider[_selectedProvider] = result;
          // Update stored config with schema
          final current = _configsPerProvider[_selectedProvider];
          if (current != null) {
            try {
              final schemaJson = jsonDecode(result);
              _configsPerProvider[_selectedProvider] = CustomSttConfig(
                provider: current.provider,
                apiKey: current.apiKey,
                language: current.language,
                model: current.model,
                url: current.url,
                host: current.host,
                port: current.port,
                requestType: current.requestType,
                headers: current.headers,
                params: current.params,
                audioFieldName: current.audioFieldName,
                schemaJson: schemaJson,
              );
            } catch (_) {}
          }
        }
      });
      _validateAndSetError();
    }
  }

  Widget _buildLogsSection() {
    final logService = CustomSttLogService.instance;
    final logs = logService.logs;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => setState(() => _showLogs = !_showLogs),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Row(
              children: [
                Text(
                  'Logs',
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                ),
                const SizedBox(width: 8),
                Icon(
                  _showLogs ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                  color: Colors.grey.shade500,
                  size: 18,
                ),
                const Spacer(),
                if (_showLogs && logs.isNotEmpty) ...[
                  GestureDetector(
                    onTap: () {
                      Clipboard.setData(ClipboardData(text: logService.logsAsText));
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Logs copied'), duration: Duration(seconds: 1)),
                      );
                    },
                    child: Icon(Icons.copy, color: Colors.grey.shade500, size: 16),
                  ),
                ],
              ],
            ),
          ),
        ),
        if (_showLogs)
          Container(
            constraints: const BoxConstraints(maxHeight: 200),
            decoration: BoxDecoration(
              color: const Color(0xFF1A1A1A),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Colors.grey.shade800),
            ),
            child: logs.isEmpty
                ? Padding(
                    padding: const EdgeInsets.all(16),
                    child: Center(
                      child: Text(
                        'No logs yet. Start recording to see custom STT activity.',
                        style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  )
                : ListView.builder(
                    shrinkWrap: true,
                    padding: const EdgeInsets.all(8),
                    itemCount: logs.length,
                    itemBuilder: (context, index) {
                      final log = logs[index];
                      final isError = log.level == CustomSttLogLevel.error;
                      final isWarning = log.level == CustomSttLogLevel.warning;
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              log.formattedTime,
                              style: TextStyle(
                                color: Colors.grey.shade600,
                                fontSize: 10,
                                fontFamily: 'monospace',
                              ),
                            ),
                            const SizedBox(width: 6),
                            Icon(
                              isError
                                  ? Icons.error_outline
                                  : isWarning
                                      ? Icons.warning_amber_outlined
                                      : Icons.info_outline,
                              size: 12,
                              color: isError
                                  ? Colors.red.shade400
                                  : isWarning
                                      ? Colors.orange.shade400
                                      : Colors.grey.shade500,
                            ),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                '[${log.source}] ${log.message}',
                                style: TextStyle(
                                  color: isError
                                      ? Colors.red.shade300
                                      : isWarning
                                          ? Colors.orange.shade300
                                          : Colors.grey.shade400,
                                  fontSize: 11,
                                  fontFamily: 'monospace',
                                ),
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
      ],
    );
  }

  Widget _buildOmiFeatures() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Omi\'s built-in live transcription is optimized for real-time conversations with automatic speaker detection and diarization.',
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
    _logRefreshTimer?.cancel();
    _apiKeyController.dispose();
    _hostController.dispose();
    _portController.dispose();
    _urlController.dispose();
    super.dispose();
  }
}

class _JsonEditorPage extends StatefulWidget {
  final String title;
  final String initialJson;
  final SttProvider provider;
  final Map<String, dynamic> Function() onReset;
  final bool isResponseSchema;

  const _JsonEditorPage({
    required this.title,
    required this.initialJson,
    required this.provider,
    required this.onReset,
    this.isResponseSchema = false,
  });

  @override
  State<_JsonEditorPage> createState() => _JsonEditorPageState();
}

class _JsonEditorPageState extends State<_JsonEditorPage> {
  late TextEditingController _controller;
  String? _parseError;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialJson);
    _parseJson();
  }

  void _parseJson() {
    try {
      jsonDecode(_controller.text);
      _parseError = null;
    } catch (e) {
      _parseError = e.toString();
    }
    setState(() {});
  }

  void _resetToTemplate() {
    final template = widget.onReset();
    _controller.text = const JsonEncoder.withIndent('  ').convert(template);
    _parseJson();
  }

  void _applySchemaTemplate(String templateName) {
    final schema = SttResponseSchema.templates[templateName];
    if (schema != null) {
      _controller.text = const JsonEncoder.withIndent('  ').convert(schema.toJson());
      _parseJson();
    }
  }

  void _applyRequestTemplate(String templateName) {
    final template = SttProviderConfig.requestTemplates[templateName];
    if (template != null) {
      _controller.text = const JsonEncoder.withIndent('  ').convert(template);
      _parseJson();
    }
  }

  bool get _showTemplateSelector => widget.provider == SttProvider.custom || widget.provider == SttProvider.customLive;

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
      ),
      body: Column(
        children: [
          Expanded(child: _buildEditorTab()),
          _buildBottomBar(),
        ],
      ),
    );
  }

  Widget _buildTemplateSelector() {
    final isResponseSchema = widget.isResponseSchema;
    final templates =
        isResponseSchema ? SttResponseSchema.templates.keys.toList() : SttProviderConfig.requestTemplates.keys.toList();
    final description = isResponseSchema
        ? 'Quickly populate with a known provider\'s response format'
        : 'Quickly populate with a known provider\'s request format';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Use template from',
          style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
        ),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: const Color(0xFF1A1A1A),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.grey.shade800),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: null,
              hint: Text(
                'Select a provider template...',
                style: TextStyle(color: Colors.grey.shade600, fontSize: 14),
              ),
              isExpanded: true,
              dropdownColor: const Color(0xFF1A1A1A),
              style: const TextStyle(color: Colors.white, fontSize: 14),
              icon: Icon(Icons.keyboard_arrow_down, color: Colors.grey.shade500),
              items: templates.map((name) {
                final isLive = isResponseSchema
                    ? SttResponseSchema.liveTemplates.contains(name)
                    : SttProviderConfig.liveRequestTemplates.contains(name);
                return DropdownMenuItem<String>(
                  value: name,
                  child: Row(
                    children: [
                      Expanded(child: Text(name)),
                      if (isLive)
                        Container(
                          margin: const EdgeInsets.only(left: 8),
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.green.withOpacity(0.2),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'Live',
                            style: TextStyle(
                              color: Colors.green,
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                    ],
                  ),
                );
              }).toList(),
              onChanged: (templateName) {
                if (templateName != null) {
                  if (isResponseSchema) {
                    _applySchemaTemplate(templateName);
                  } else {
                    _applyRequestTemplate(templateName);
                  }
                }
              },
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          description,
          style: TextStyle(color: Colors.grey.shade700, fontSize: 11),
        ),
      ],
    );
  }

  Widget _buildEditorTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_showTemplateSelector) ...[
            _buildTemplateSelector(),
            const SizedBox(height: 16),
          ],
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
    super.dispose();
  }
}
