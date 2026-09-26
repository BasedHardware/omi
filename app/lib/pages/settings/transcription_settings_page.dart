import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:disk_space_2/disk_space_2.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/settings/transcription/json_editor_page.dart';
import 'package:omi/pages/settings/transcription/stt_language.dart';
import 'package:omi/pages/settings/transcription/transcription_dialogs.dart';
import 'package:omi/pages/settings/transcription/transcription_fields.dart';
import 'package:omi/pages/settings/transcription/transcription_sections.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';

/// Top-level transcription source the user picks from the single dropdown.
enum TranscriptionMode { omi, onDevice, cloudProvider, omiParakeet }

class TranscriptionSettingsPage extends StatefulWidget {
  const TranscriptionSettingsPage({super.key});

  @override
  State<TranscriptionSettingsPage> createState() => _TranscriptionSettingsPageState();
}

class _TranscriptionSettingsPageState extends State<TranscriptionSettingsPage> {
  bool _useCustomStt = false;
  // "Omi Parakeet" is an Omi-hosted engine (not custom STT): _useCustomStt stays false and the
  // backend is told via transcriptionModel='parakeet'. This flag distinguishes it from plain Omi.
  bool _omiParakeet = false;
  SttProvider _selectedProvider = SttProvider.openai;
  bool _showAdvanced = false;
  bool _isSaving = false;
  bool _sendRawAudioToOmi = true;
  String? _validationError;

  // On-device model download state
  static bool _hasShownDebugWarning = false;
  bool _isDownloadingModel = false;
  bool _isModelFilePresent = false;
  double _downloadProgress = 0.0;
  String? _modelDownloadStatus;

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

  // Per-provider language override; a provider without one follows the primary language.
  final Map<SttProvider, bool> _languageOverridden = {};

  SttProviderConfig get _currentConfig => SttProviderConfig.get(_selectedProvider);
  CustomSttConfig? get _currentProviderConfig => _configsPerProvider[_selectedProvider];
  String get _currentLanguage => _languageFor(_selectedProvider);
  String get _primaryLanguage => SharedPreferencesUtil().userPrimaryLanguage;

  bool _isLanguageOverridden(SttProvider provider) =>
      _languageOverridden[provider] ??= SttLanguage.isOverridden(provider, saved: _configsPerProvider[provider]);

  /// The provider's own language when overridden, else the primary language in its codes.
  String _languageFor(SttProvider provider) {
    final derived = SttLanguage.derived(provider, _primaryLanguage);
    if (!_isLanguageOverridden(provider)) return derived;
    return _configsPerProvider[provider]?.language ?? derived;
  }

  String get _currentModel => _currentProviderConfig?.model ?? _currentConfig.defaultModel;
  String get _currentRequestJson => _requestJsonPerProvider[_selectedProvider] ?? '{}';
  String get _currentSchemaJson => _schemaJsonPerProvider[_selectedProvider] ?? '{}';

  @override
  void initState() {
    super.initState();
    _urlController.addListener(_updateModelPresence);
    _loadConfig();
    _checkConnectedDevice();
    // Initial check
    WidgetsBinding.instance.addPostFrameCallback((_) => _updateModelPresence());
  }

  @override
  void dispose() {
    _urlController.removeListener(_updateModelPresence);
    _downloadClient?.close();

    // Dispose controllers
    _apiKeyController.dispose();
    _hostController.dispose();
    _portController.dispose();
    _urlController.dispose();

    super.dispose();
  }

  void _updateModelPresence() {
    final path = _urlController.text;
    if (path.isEmpty) {
      if (_isModelFilePresent) setState(() => _isModelFilePresent = false);
      return;
    }
    File(path).exists().then((exists) {
      if (mounted && _isModelFilePresent != exists) {
        setState(() => _isModelFilePresent = exists);
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
        Logger.debug('Error checking device codec: $e');
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
      _omiParakeet = !_useCustomStt && SharedPreferencesUtil().transcriptionModel == 'parakeet';
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
    _sendRawAudioToOmi = config?.sendRawAudioToOmi ?? true;

    // Auto-detect model for on-device whisper if not set
    if (_selectedProvider == SttProvider.onDeviceWhisper && _urlController.text.isEmpty) {
      _checkLocalModel();
    }

    // Check for debug mode and warn user
    if (kDebugMode && _selectedProvider == SttProvider.onDeviceWhisper && !_hasShownDebugWarning) {
      _hasShownDebugWarning = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          OmiFeedback.info(context, '${context.l10n.debugModeDetected}. ${context.l10n.performanceReduced}');
        }
      });
    }

    // Restore JSON configs if customized
    if (config != null) {
      final hasCustomRequest = config.requestType != null ||
          config.headers != null ||
          config.params != null ||
          config.audioFieldName != null;

      if (hasCustomRequest) {
        final defaults = providerDefaults.buildRequestConfig(
          apiKey: config.apiKey,
          language: _languageFor(_selectedProvider),
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

  Future<void> _checkLocalModel() async {
    try {
      final appDir = await getApplicationSupportDirectory();
      final modelName = _currentModel.isEmpty ? 'tiny' : _currentModel;
      final filePath = '${appDir.path}/models/ggml-$modelName.bin';
      if (await File(filePath).exists()) {
        if (mounted) {
          setState(() {
            _urlController.text = filePath;
            _updateCurrentProviderConfig(url: filePath);
          });

          await _saveCurrentProviderConfig();
          if (_useCustomStt && _selectedProvider == SttProvider.onDeviceWhisper) {
            final config = _buildCurrentConfig();
            await SharedPreferencesUtil().saveCustomSttConfig(config);

            if (mounted) {
              await Provider.of<CaptureProvider>(context, listen: false).onTranscriptionSettingsChanged();
            }
          }
        }
      } else {
        // Clear if not found matching current model
        if (mounted && _urlController.text.isNotEmpty) {
          setState(() {
            _urlController.text = '';
          });
        }
      }
    } catch (e, stack) {
      Logger.debug('Error checking local model: $e\n$stack');
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
        _schemaJsonPerProvider[config.provider] = const JsonEncoder.withIndent(
          '  ',
        ).convert(template['response_schema']);
      }
    }
  }

  void _regenerateRequestJson(SttProvider provider) {
    final providerDefaults = SttProviderConfig.get(provider);
    final savedConfig = _configsPerProvider[provider];

    final apiKey = savedConfig?.apiKey ?? _apiKeyController.text;
    final language = _languageFor(provider);
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

    if (_selectedProvider == SttProvider.onDeviceWhisper) {
      _checkLocalModel();
    }
  }

  void _updateCurrentProviderConfig({
    String? apiKey,
    String? language,
    String? model,
    String? url,
    String? host,
    int? port,
    bool? sendRawAudioToOmi,
  }) {
    final current = _configsPerProvider[_selectedProvider];
    final providerDefaults = SttProviderConfig.get(_selectedProvider);

    // Picking a language other than the primary one (in the picker or the request JSON) overrides it.
    if (language != null && language != SttLanguage.derived(_selectedProvider, _primaryLanguage)) {
      _languageOverridden[_selectedProvider] = true;
    }

    _configsPerProvider[_selectedProvider] = CustomSttConfig(
      provider: _selectedProvider,
      apiKey: apiKey ?? current?.apiKey ?? _apiKeyController.text,
      language: language ?? _languageFor(_selectedProvider),
      model: model ?? current?.model ?? providerDefaults.defaultModel,
      url: url ?? current?.url ?? _urlController.text,
      host: host ?? current?.host ?? _hostController.text,
      port: port ?? current?.port ?? int.tryParse(_portController.text),
      requestType: current?.requestType,
      headers: current?.headers,
      params: current?.params,
      audioFieldName: current?.audioFieldName,
      schemaJson: current?.schemaJson,
      sendRawAudioToOmi: sendRawAudioToOmi ?? current?.sendRawAudioToOmi ?? _sendRawAudioToOmi,
    );
  }

  Future<void> _saveCurrentProviderConfig() async {
    // Build complete config from current UI state
    final config = _buildCurrentConfig();
    _configsPerProvider[_selectedProvider] = config;
    await SttLanguage.setOverridden(_selectedProvider, _isLanguageOverridden(_selectedProvider));
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
      url = requestJson['url']?.toString();
      requestType = requestJson['request_type']?.toString();
      headers = requestJson['headers'] is Map
          ? (requestJson['headers'] as Map).map((k, v) => MapEntry(k.toString(), v.toString()))
          : null;
      params = requestJson['params'] is Map
          ? (requestJson['params'] as Map).map((k, v) => MapEntry(k.toString(), v.toString()))
          : null;
      audioFieldName = requestJson['audio_field_name']?.toString();
    }

    // Use URL from text field for custom providers
    if (_selectedProvider == SttProvider.custom ||
        _selectedProvider == SttProvider.customLive ||
        _selectedProvider == SttProvider.onDeviceWhisper) {
      url = _urlController.text.isNotEmpty ? _urlController.text : url;
    }

    final current = _configsPerProvider[_selectedProvider];
    final providerDefaults = SttProviderConfig.get(_selectedProvider);

    return CustomSttConfig(
      provider: _selectedProvider,
      apiKey: _apiKeyController.text.isNotEmpty ? _apiKeyController.text : null,
      language: _languageFor(_selectedProvider),
      model: current?.model ?? providerDefaults.defaultModel,
      url: url,
      host: _selectedProvider == SttProvider.localWhisper ? _hostController.text : null,
      port: _selectedProvider == SttProvider.localWhisper ? int.tryParse(_portController.text) : null,
      requestType: requestType,
      headers: headers,
      params: params,
      audioFieldName: audioFieldName,
      schemaJson: schemaJson,
      sendRawAudioToOmi: _sendRawAudioToOmi,
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
          _validationError = context.l10n.hostRequired;
          return;
        }
        if (_portController.text.isEmpty || int.tryParse(_portController.text) == null) {
          _validationError = context.l10n.validPortRequired;
          return;
        }
      } else if (_selectedProvider == SttProvider.customLive) {
        if (_urlController.text.isEmpty || !_urlController.text.startsWith('wss://')) {
          _validationError = context.l10n.validWebsocketUrlRequired;
          return;
        }
      } else if (_selectedProvider == SttProvider.custom) {
        if (_urlController.text.isEmpty) {
          _validationError = context.l10n.apiUrlRequired;
          return;
        }
      } else if (_selectedProvider != SttProvider.custom) {
        if (_currentConfig.requiresApiKey && _apiKeyController.text.isEmpty) {
          _validationError = context.l10n.apiKeyRequired;
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
          _validationError = context.l10n.invalidJsonConfig;
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
      OmiFeedback.error(context, _validationError!);
      return;
    }

    // Validate On-Device model presence
    if (_selectedProvider == SttProvider.onDeviceWhisper && !Platform.isIOS) {
      final modelPath = _urlController.text;
      final hasModel = modelPath.isNotEmpty && await File(modelPath).exists();
      if (!hasModel) {
        if (!mounted) return;
        await showOmiAlert(context, title: context.l10n.modelRequired, message: context.l10n.downloadWhisperModel);
        return;
      }
    }

    setState(() => _isSaving = true);

    try {
      // Save current provider's complete config
      await _saveCurrentProviderConfig();

      // Build the active config (with correct provider based on _useCustomStt)
      final currentConfig = _buildCurrentConfig();
      final activeConfig = _useCustomStt ? currentConfig : const CustomSttConfig(provider: SttProvider.omi);

      // Omi-hosted engine choice (server-side): pick Parakeet vs the default via transcriptionModel.
      // The backend reads this as stt_service and routes to the self-hosted Parakeet service.
      final prevModel = SharedPreferencesUtil().transcriptionModel;
      if (!_useCustomStt) {
        SharedPreferencesUtil().transcriptionModel = _omiParakeet ? 'parakeet' : 'soniox';
      }
      final modelChanged = SharedPreferencesUtil().transcriptionModel != prevModel;

      final previousConfig = SharedPreferencesUtil().customSttConfig;
      final configChanged = previousConfig.sttConfigId != activeConfig.sttConfigId;

      await SharedPreferencesUtil().saveCustomSttConfig(activeConfig);
      Logger.debug(SharedPreferencesUtil().customSttConfig.provider.toString());

      if ((configChanged || modelChanged) && mounted) {
        await Provider.of<CaptureProvider>(context, listen: false).onTranscriptionSettingsChanged();
      }

      if (mounted) {
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        OmiFeedback.error(
          context,
          context.l10n.errorSaving(readableError(e)),
          actionLabel: context.l10n.tryAgain,
          onAction: _saveConfig,
        );
      }
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
      'send_raw_audio_to_omi': config.sendRawAudioToOmi,
    };

    final jsonString = const JsonEncoder.withIndent('  ').convert(exportableConfig);

    if (!mounted) return;
    await OmiClipboard.copy(context, jsonString, what: context.l10n.configuration);
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
    final result = await showImportConfigDialog(context);
    if (result != null && result.isNotEmpty && mounted) _parseAndApplyConfig(result);
  }

  void _parseAndApplyConfig(String jsonString) {
    try {
      final json = jsonDecode(jsonString) as Map<String, dynamic>;
      final config = CustomSttConfig.fromJson(json);

      // Validate provider
      if (config.provider == SttProvider.omi) {
        OmiFeedback.error(context, context.l10n.invalidProviderInConfig);
        return;
      }

      setState(() {
        _selectedProvider = config.provider;
        _configsPerProvider[_selectedProvider] = config;
        final language = config.language;
        _languageOverridden[_selectedProvider] =
            language != null && language != SttLanguage.derived(_selectedProvider, _primaryLanguage);

        // Update UI fields
        _apiKeyController.text = config.apiKey ?? '';
        _urlController.text = config.url ?? '';
        _hostController.text = config.host ?? '127.0.0.1';
        _portController.text = (config.port ?? 8080).toString();
        _sendRawAudioToOmi = config.sendRawAudioToOmi;

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

      OmiFeedback.confirm(context, context.l10n.importedConfig(SttProviderConfig.get(_selectedProvider).displayName));
    } catch (e) {
      OmiFeedback.error(context, context.l10n.invalidJson(e.toString().split('\n').first));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.transcription),
        actions: [
          if (_useCustomStt) ...[
            OmiIconButton(
              icon: const Icon(Icons.file_download_outlined, size: 20),
              label: context.l10n.importConfiguration,
              onPressed: _importConfig,
            ),
            OmiIconButton(
              icon: const Icon(Icons.file_upload_outlined, size: 20),
              label: context.l10n.exportConfiguration,
              onPressed: _exportConfig,
            ),
          ],
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildSourceSelector(),
                  const SizedBox(height: OmiSpacing.xl),
                  if (_useCustomStt) ...[
                    _buildProviderSection(),
                    const SizedBox(height: OmiSpacing.lg),
                    _buildConfigSection(),
                    const SizedBox(height: OmiSpacing.lg),
                    OmiSettingsGroup(
                      children: [
                        OmiSettingsRow.toggle(
                          leading: const Icon(Icons.cloud_upload_outlined),
                          title: context.l10n.sendRawAudioToOmi,
                          subtitle: context.l10n.sendRawAudioToOmiDescription,
                          value: _sendRawAudioToOmi,
                          onChanged: (value) => setState(() {
                            _sendRawAudioToOmi = value;
                            _updateCurrentProviderConfig(sendRawAudioToOmi: value);
                          }),
                        ),
                      ],
                    ),
                    const SizedBox(height: OmiSpacing.xs),
                    _buildAdvancedSection(),
                    const CustomSttLogsSection(),
                  ] else
                    Text(
                      context.l10n.omiTranscriptionOptimized,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.5),
                    ),
                  const SizedBox(height: 100),
                ],
              ),
            ),
          ),
          TranscriptionSaveBar(onPressed: _isSaving ? null : _saveConfig, isLoading: _isSaving),
        ],
      ),
    );
  }

  Future<void> _switchToOnDevice() async {
    bool isLowSpec = false;
    String specDetails = '';
    bool isIOS = Platform.isIOS;

    final deviceInfo = DeviceInfoPlugin();
    final l10n = context.l10n;

    if (Platform.isAndroid) {
      // Check RAM using /proc/meminfo as reliable fallback
      try {
        final memInfo = await File('/proc/meminfo').readAsString();
        final totalMemLine = memInfo.split('\n').firstWhere((l) => l.startsWith('MemTotal:'), orElse: () => '');
        if (totalMemLine.isNotEmpty) {
          final parts = totalMemLine.split(RegExp(r'\s+'));
          if (parts.length >= 2) {
            final kb = int.tryParse(parts[1]);
            if (kb != null) {
              final gb = kb / 1024 / 1024;
              if (gb < 3.5) {
                isLowSpec = true;
                specDetails = l10n.deviceRamBelowMinimum(gb.toStringAsFixed(1));
              }
            }
          }
        }
      } catch (e) {
        Logger.debug('Error reading meminfo: $e');
      }
    } else if (Platform.isIOS) {
      final iosInfo = await deviceInfo.iosInfo;
      final machine = iosInfo.utsname.machine;
      Logger.debug('Device Model: $machine');

      if (machine.startsWith('iPhone')) {
        final match = RegExp(r'iPhone(\d+),').firstMatch(machine);
        if (match != null) {
          final version = int.tryParse(match.group(1) ?? '0') ?? 0;
          if (version < 11) {
            isLowSpec = true;
            specDetails = l10n.olderIphoneModelDetected(machine);
          }
        }
      }
    }

    if (!mounted) return;
    final proceed = await confirmOnDeviceTranscription(
      context,
      lowSpec: isLowSpec,
      isIOS: isIOS,
      specDetails: specDetails,
    );
    if (!proceed) return;

    await _saveCurrentProviderConfig();
    if (!mounted) return;

    setState(() {
      _useCustomStt = true;
      _selectedProvider = SttProvider.onDeviceWhisper;
      _populateUIFromConfig(_configsPerProvider[_selectedProvider]);
      PlatformManager.instance.analytics.transcriptionSourceSelected(
        source: isIOS ? 'custom_on_device_ios' : 'custom_on_device',
      );
    });
  }

  /// Current transcription source, derived from the persisted STT state.
  TranscriptionMode get _currentMode {
    if (!_useCustomStt) return _omiParakeet ? TranscriptionMode.omiParakeet : TranscriptionMode.omi;
    if (_selectedProvider == SttProvider.onDeviceWhisper) return TranscriptionMode.onDevice;
    return TranscriptionMode.cloudProvider;
  }

  String _modeLabel(TranscriptionMode mode) {
    switch (mode) {
      case TranscriptionMode.omi:
        return context.l10n.transcriptionSourceOmi;
      case TranscriptionMode.onDevice:
        return context.l10n.onDevice;
      case TranscriptionMode.cloudProvider:
        return context.l10n.cloudProvider;
      case TranscriptionMode.omiParakeet:
        return SttProviderConfig.get(SttProvider.omiParakeet).displayName;
    }
  }

  Future<void> _selectMode(TranscriptionMode mode) async {
    switch (mode) {
      case TranscriptionMode.omi:
        setState(() {
          _useCustomStt = false;
          _omiParakeet = false;
        });
        PlatformManager.instance.analytics.transcriptionSourceSelected(source: 'omi');
        break;
      case TranscriptionMode.onDevice:
        await _switchToOnDevice();
        break;
      case TranscriptionMode.cloudProvider:
        if (_selectedProvider == SttProvider.onDeviceWhisper) {
          await _saveCurrentProviderConfig();
          if (!mounted) return;
        }
        setState(() {
          _useCustomStt = true;
          _omiParakeet = false;
          // Leaving on-device: fall back to a real BYO cloud provider.
          if (_selectedProvider == SttProvider.onDeviceWhisper) {
            _selectedProvider = SttProvider.openai;
            _populateUIFromConfig(_configsPerProvider[_selectedProvider]);
          }
        });
        PlatformManager.instance.analytics.transcriptionSourceSelected(source: 'custom_cloud');
        _validateAndSetError();
        break;
      case TranscriptionMode.omiParakeet:
        // Omi-hosted Parakeet — server-routed (transcriptionModel='parakeet' on save), not custom STT.
        setState(() {
          _useCustomStt = false;
          _omiParakeet = true;
        });
        PlatformManager.instance.analytics.transcriptionSourceSelected(source: 'omi_parakeet');
        break;
    }
  }

  Widget _buildSourceSelector() {
    final mode = _currentMode;
    final l10n = context.l10n;
    final secondary = OmiType.footnote.copyWith(color: OmiColors.textTertiary);

    Widget? description;
    if (mode == TranscriptionMode.omi && context.watch<UsageProvider>().showSubscriptionUI) {
      description = Semantics(
        link: true,
        child: InkWell(
          onTap: () => routeToPage(context, const UsagePage(showUpgradeDialog: true)),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text.rich(
                TextSpan(
                  children: [
                    TextSpan(text: l10n.premiumMinutesMonth, style: secondary),
                    TextSpan(
                      text: l10n.viewUsage,
                      style: secondary.copyWith(
                        color: OmiColors.textSecondary,
                        decoration: TextDecoration.underline,
                      ),
                    ),
                    TextSpan(text: '.', style: secondary),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
    } else if (mode == TranscriptionMode.onDevice) {
      description = TranscriptionHelpText(l10n.audioProcessedLocally);
    } else if (mode == TranscriptionMode.omiParakeet) {
      description = TranscriptionHelpText(SttProviderConfig.get(SttProvider.omiParakeet).description);
    } else if (mode == TranscriptionMode.cloudProvider) {
      description = TranscriptionHelpText(l10n.payYourSttProvider);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 10),
        TranscriptionDropdown<TranscriptionMode>(
          value: mode,
          items: [
            for (final m in TranscriptionMode.values)
              DropdownMenuItem<TranscriptionMode>(value: m, child: Text(_modeLabel(m))),
          ],
          onChanged: (m) async {
            if (m != null && m != mode) await _selectMode(m);
          },
        ),
        const SizedBox(height: OmiSpacing.sm),
        if (description != null) description,
      ],
    );
  }

  Widget _buildCodecWarning() {
    if (_isCodecCompatible || !_useCustomStt) return const SizedBox.shrink();

    final codecReason = _connectedDeviceCodec?.customSttUnsupportedReason ?? 'unsupported format';
    final warningText = _sendRawAudioToOmi
        ? context.l10n.deviceUsesCodec(_connectedDeviceName ?? context.l10n.device, codecReason)
        : context.l10n.transcriptionUnavailable;
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded, color: OmiColors.warning, size: 14),
          const SizedBox(width: 6),
          Expanded(child: TranscriptionHelpText(warningText)),
        ],
      ),
    );
  }

  Future<void> _selectProvider(SttProvider provider) async {
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
    PlatformManager.instance.analytics.transcriptionProviderSelected(provider: provider.name);

    _validateAndSetError();
  }

  Widget _buildProviderSection() {
    // On-Device Whisper and Omi Parakeet are fixed providers chosen from the
    // top dropdown — there's no sub-provider to pick, so hide this section.
    if (_selectedProvider == SttProvider.onDeviceWhisper || _selectedProvider == SttProvider.omiParakeet) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildCodecWarning(),
        TranscriptionFieldLabel(context.l10n.provider),
        TranscriptionDropdown<SttProvider>(
          value: _selectedProvider,
          items: [
            for (final config in SttProviderConfig.allProviders)
              if (config.provider != SttProvider.onDeviceWhisper)
                DropdownMenuItem<SttProvider>(
                  value: config.provider,
                  child: TranscriptionOptionLabel(config.displayName, isLive: config.isLive),
                ),
          ],
          onChanged: (provider) async {
            if (provider != null) await _selectProvider(provider);
          },
        ),
        const SizedBox(height: OmiSpacing.xxs),
        Row(
          children: [
            Expanded(child: TranscriptionHelpText(_currentConfig.description)),
            if (_currentConfig.docsUrl != null)
              OmiIconButton(
                icon: const Icon(Icons.open_in_new, size: 16),
                label: context.l10n.openProviderDocs,
                color: OmiColors.textTertiary,
                onPressed: () => _launchUrl(_currentConfig.docsUrl!),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildConfigSection() {
    if (_selectedProvider == SttProvider.localWhisper) {
      return _buildLocalWhisperConfig();
    } else if (_selectedProvider == SttProvider.onDeviceWhisper) {
      return _buildOnDeviceWhisperConfig();
    } else if (_selectedProvider == SttProvider.custom) {
      return _buildUrlConfig(
          context.l10n.apiUrl, 'https://your-stt-api.com/transcribe', context.l10n.enterSttHttpEndpoint);
    } else if (_selectedProvider == SttProvider.customLive) {
      return _buildUrlConfig(
          context.l10n.websocketUrl, 'wss://your-stt-api.com/live', context.l10n.enterLiveSttWebsocket);
    } else if (_selectedProvider == SttProvider.omiParakeet) {
      // Omi-hosted — no API key needed, just language.
      return _buildLanguageSelector();
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [_buildApiKeyInput(), const SizedBox(height: OmiSpacing.lg), _buildLanguageSelector()],
    );
  }

  Widget _buildLanguageSelector() {
    final primary = _primaryLanguage;
    final overridden = _isLanguageOverridden(_selectedProvider);
    return SttLanguageSection(
      provider: _selectedProvider,
      overridden: overridden,
      language: _currentLanguage,
      primaryLanguage: primary,
      primaryLanguageName:
          primary.isEmpty ? context.l10n.notSet : context.read<HomeProvider>().getLanguageName(primary),
      pickerKey: ValueKey('${_selectedProvider.name}_language_$_configSyncVersion'),
      onOverride: () => setState(() {
        // Start the picker from the language in use.
        _updateCurrentProviderConfig(language: _currentLanguage);
        _languageOverridden[_selectedProvider] = true;
        _configSyncVersion++;
      }),
      onUsePrimary: () => setState(() {
        _languageOverridden[_selectedProvider] = false;
        _onLanguageOrModelChanged(SttLanguage.derived(_selectedProvider, primary), null);
        _configSyncVersion++;
      }),
      onChanged: (code) => setState(() => _onLanguageOrModelChanged(code, null)),
    );
  }

  Widget _buildModelSelector() {
    return TranscriptionAutocompleteField(
      key: ValueKey('${_selectedProvider.name}_model_$_configSyncVersion'),
      label: context.l10n.modelLabel,
      hint: _currentConfig.defaultModel,
      value: _currentModel,
      suggestions: _currentConfig.supportedModels,
      onChanged: (value) {
        final newModel = value.trim();
        if (_selectedProvider == SttProvider.onDeviceWhisper && ['medium', 'large-v1', 'large-v2'].contains(newModel)) {
          showOmiAlert(context, title: context.l10n.performanceWarning, message: context.l10n.modelTooLargeWarning);
        }
        setState(() {
          _onLanguageOrModelChanged(null, newModel);
        });
      },
    );
  }

  Widget _buildUrlConfig(String label, String hint, String help) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TranscriptionTextField(
          controller: _urlController,
          label: label,
          hint: hint,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: OmiSpacing.xs),
        TranscriptionHelpText(help),
      ],
    );
  }

  Widget _buildApiKeyInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TranscriptionFieldLabel(
          context.l10n.apiKey,
          trailing: _currentConfig.apiKeyUrl == null
              ? null
              : OmiIconButton(
                  icon: const Icon(Icons.open_in_new, size: 16),
                  label: context.l10n.getApiKey,
                  color: OmiColors.textTertiary,
                  onPressed: () => _launchUrl(_currentConfig.apiKeyUrl!),
                ),
        ),
        TextField(
          controller: _apiKeyController,
          obscureText: !_showApiKey,
          style: OmiType.subhead,
          onChanged: (_) => _validateAndSetError(),
          decoration: transcriptionInputDecoration(
            hint: context.l10n.enterApiKey,
            suffixIcon: OmiIconButton(
              icon: Icon(_showApiKey ? Icons.visibility_off : Icons.visibility, size: 20),
              label: _showApiKey ? context.l10n.hideApiKey : context.l10n.showApiKey,
              color: OmiColors.textTertiary,
              onPressed: () => setState(() => _showApiKey = !_showApiKey),
            ),
          ),
        ),
        const SizedBox(height: OmiSpacing.xs),
        TranscriptionHelpText(context.l10n.storedLocallyNeverShared),
      ],
    );
  }

  Widget _buildLocalWhisperConfig() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 3,
              child: TranscriptionTextField(
                controller: _hostController,
                label: context.l10n.host,
                hint: '127.0.0.1',
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              flex: 2,
              child: TranscriptionTextField(
                controller: _portController,
                label: context.l10n.port,
                hint: '8080',
                keyboardType: TextInputType.number,
                onChanged: (_) => setState(() {}),
              ),
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.sm),
        TranscriptionHelpText('http://${_hostController.text}:${_portController.text}/inference', monospace: true),
        const SizedBox(height: OmiSpacing.lg),
        _buildLanguageSelector(),
      ],
    );
  }

  /// UI for On-Device Whisper Configuration
  Widget _buildOnDeviceWhisperConfig() {
    // If iOS, show simplified Apple Speech UI
    if (Theme.of(context).platform == TargetPlatform.iOS) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(OmiSpacing.sm),
            decoration: BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: OmiRadius.smAll,
              border: Border.all(color: OmiColors.border),
            ),
            child: Row(
              children: [
                const Icon(Icons.apple, color: OmiColors.textPrimary, size: 24),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Text(context.l10n.usingNativeIosSpeech,
                      style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500)),
                ),
              ],
            ),
          ),
          const SizedBox(height: OmiSpacing.sm),
          TranscriptionHelpText(context.l10n.nativeEngineNoDownload),
          const SizedBox(height: OmiSpacing.lg),
          _buildLanguageSelector(),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        WhisperModelStatus(
          modelFile: 'ggml-${_currentModel.isEmpty ? 'tiny' : _currentModel}.bin',
          hasModel: _isModelFilePresent,
          isDownloading: _isDownloadingModel,
          progress: _downloadProgress,
          status: _modelDownloadStatus,
          onDownload: _downloadModel,
          onCancel: _cancelDownload,
        ),
        const SizedBox(height: OmiSpacing.lg),
        _buildModelSelector(),
        const SizedBox(height: OmiSpacing.lg),
        _buildLanguageSelector(),
      ],
    );
  }

  // Add this field to the State class
  http.Client? _downloadClient;

  Future<void> _downloadModel() async {
    final modelName = _currentModel.isEmpty ? 'tiny' : _currentModel;

    double estimatedSizeMB = 1500;
    switch (modelName) {
      case 'tiny':
        estimatedSizeMB = 75;
        break;
      case 'base':
        estimatedSizeMB = 142;
        break;
      case 'small':
        estimatedSizeMB = 466;
        break;
      case 'medium':
        estimatedSizeMB = 1500;
        break;
      case 'large-v1':
      case 'large-v2':
        estimatedSizeMB = 2900;
        break;
    }

    final appDir = await getApplicationSupportDirectory();
    final modelDir = Directory('${appDir.path}/models');

    double? freeSpaceMB = await DiskSpace.getFreeDiskSpaceForPath(appDir.path);

    if (!mounted) return;
    final confirmed = await confirmModelDownload(
      context,
      modelName: modelName,
      estimatedSizeMB: estimatedSizeMB,
      freeSpaceMB: freeSpaceMB,
    );

    if (!confirmed || !mounted) return;

    setState(() {
      _isDownloadingModel = true;
      _downloadProgress = 0.0;
      _modelDownloadStatus = context.l10n.preparingModel(modelName);
    });

    try {
      if (!await modelDir.exists()) {
        await modelDir.create(recursive: true);
      }

      final fileName = 'ggml-$modelName.bin';
      final filePath = '${modelDir.path}/$fileName';
      final url = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$fileName';

      _downloadClient = http.Client();
      final request = http.Request('GET', Uri.parse(url));
      final response = await _downloadClient!.send(request);

      if (response.statusCode != 200) {
        throw Exception('Download failed: ${response.statusCode}');
      }

      final contentLength = response.contentLength ?? (estimatedSizeMB * 1024 * 1024).toInt();
      int received = 0;

      final file = File(filePath);
      final sink = file.openWrite();

      try {
        await response.stream.listen((chunk) {
          sink.add(chunk);
          received += chunk.length;
          if (mounted) {
            setState(() {
              _downloadProgress = received / contentLength;
              _modelDownloadStatus = context.l10n.downloadingModelProgress(
                modelName,
                (received / 1024 / 1024).toStringAsFixed(1),
                (contentLength / 1024 / 1024).toStringAsFixed(1),
              );
            });
          }
        }, cancelOnError: true).asFuture();
      } finally {
        await sink.close();
      }

      if (mounted) {
        setState(() {
          _urlController.text = filePath;
          _isDownloadingModel = false;
          _modelDownloadStatus = context.l10n.done;
        });
      }

      _updateCurrentProviderConfig(url: filePath);

      await _saveCurrentProviderConfig();
      if (!mounted) return;
      if (_useCustomStt && _selectedProvider == SttProvider.onDeviceWhisper) {
        final config = _buildCurrentConfig();
        await SharedPreferencesUtil().saveCustomSttConfig(config);
        if (!mounted) return;
        await Provider.of<CaptureProvider>(context, listen: false).onTranscriptionSettingsChanged();
      }

      // Auto-delete unused models
      try {
        final List<FileSystemEntity> files = modelDir.listSync();
        for (final file in files) {
          if (file is File && file.path.endsWith('.bin') && file.path != filePath) {
            await file.delete();
            Logger.debug('Deleted unused model: ${file.path}');
          }
        }
      } catch (e) {
        Logger.debug('Error cleaning up models: $e');
      }
    } catch (e) {
      if (e is http.ClientException) {
        if (mounted) {
          setState(() {
            _isDownloadingModel = false;
            _modelDownloadStatus = context.l10n.cancelled;
          });
        }
      } else {
        if (mounted) {
          setState(() {
            _isDownloadingModel = false;
            _modelDownloadStatus = context.l10n.errorWithMessage(readableError(e));
          });
          OmiFeedback.error(
            context,
            context.l10n.downloadErrorWithMessage(readableError(e)),
            actionLabel: context.l10n.tryAgain,
            onAction: _downloadModel,
          );
        }
      }
    } finally {
      _downloadClient?.close();
      _downloadClient = null;
    }
  }

  void _cancelDownload() {
    _downloadClient?.close();
    setState(() {
      _isDownloadingModel = false;
      _modelDownloadStatus = context.l10n.cancelled;
    });
  }

  Widget _buildAdvancedSection() {
    // Show advanced section for all providers except Omi
    if (_selectedProvider == SttProvider.omi) return const SizedBox.shrink();
    final isCustomized = _requestJsonCustomized[_selectedProvider] == true;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TranscriptionDisclosureHeader(
          title: context.l10n.advanced,
          expanded: _showAdvanced,
          onToggle: () => setState(() => _showAdvanced = !_showAdvanced),
        ),
        if (_showAdvanced) ...[
          const SizedBox(height: OmiSpacing.xxs),
          // Hide generic model selector for OnDeviceWhisper as it has a specific UI
          if (_currentConfig.supportedModels.isNotEmpty && _selectedProvider != SttProvider.onDeviceWhisper) ...[
            _buildModelSelector(),
            const SizedBox(height: OmiSpacing.md),
          ],
          TranscriptionFieldLabel(context.l10n.configuration),
          TranscriptionJsonCard(
            title: context.l10n.requestConfiguration,
            jsonContent: _currentRequestJson,
            isCustomized: isCustomized,
            onTap: () => _openJsonEditor(
              title: context.l10n.requestConfiguration,
              jsonContent: _currentRequestJson,
              isRequest: true,
            ),
          ),
          const SizedBox(height: OmiSpacing.sm),
          TranscriptionJsonCard(
            title: context.l10n.responseSchema,
            jsonContent: _currentSchemaJson,
            onTap: () =>
                _openJsonEditor(title: context.l10n.responseSchema, jsonContent: _currentSchemaJson, isRequest: false),
          ),
          if (isCustomized) ...[
            const SizedBox(height: OmiSpacing.xs),
            OmiButton.tertiary(
              label: context.l10n.resetRequestConfig,
              icon: Icons.refresh,
              size: OmiButtonSize.compact,
              onPressed: _resetRequestConfig,
            ),
          ],
        ],
      ],
    );
  }

  void _resetRequestConfig() {
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
          sendRawAudioToOmi: current.sendRawAudioToOmi,
        );
      }
      _regenerateRequestJson(_selectedProvider);
    });
  }

  Map<String, dynamic> _defaultRequestConfig() {
    final providerDefaults = SttProviderConfig.get(_selectedProvider);
    final savedConfig = _configsPerProvider[_selectedProvider];
    return providerDefaults.buildRequestConfig(
      apiKey: savedConfig?.apiKey ?? _apiKeyController.text,
      language: _languageFor(_selectedProvider),
      model: savedConfig?.model ?? providerDefaults.defaultModel,
    );
  }

  Future<void> _openJsonEditor({required String title, required String jsonContent, bool isRequest = false}) async {
    final result = await Navigator.of(context).push<String>(
      omiPageRoute(
        builder: (context) => TranscriptionJsonEditorPage(
          title: title,
          initialJson: jsonContent,
          provider: _selectedProvider,
          isResponseSchema: !isRequest,
          onReset: () => isRequest
              ? _defaultRequestConfig()
              : CustomSttConfig.getFullTemplateJson(_selectedProvider)['response_schema'],
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
          final autoGeneratedJson = const JsonEncoder.withIndent('  ').convert(_defaultRequestConfig());
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
                sendRawAudioToOmi: current.sendRawAudioToOmi,
              );
            } catch (_) {}
          }
        }
      });
      _validateAndSetError();
    }
  }
}
