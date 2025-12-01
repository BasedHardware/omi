import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/stt_response_schema.dart';
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

  // Store settings per provider
  final Map<SttProvider, String> _apiKeysPerProvider = {};
  final Map<SttProvider, String> _languagePerProvider = {};
  final Map<SttProvider, String> _modelPerProvider = {};

  final TextEditingController _apiKeyController = TextEditingController();
  final TextEditingController _hostController = TextEditingController(text: '127.0.0.1');
  final TextEditingController _portController = TextEditingController(text: '8080');
  final TextEditingController _urlController = TextEditingController(text: '');

  // Store JSON configs per provider
  final Map<SttProvider, String> _requestJsonPerProvider = {};
  final Map<SttProvider, String> _schemaJsonPerProvider = {};
  final Map<SttProvider, bool> _requestJsonCustomized = {};

  bool _showApiKey = false;

  SttProviderConfig get _currentConfig => SttProviderConfig.get(_selectedProvider);
  String get _currentLanguage => _languagePerProvider[_selectedProvider] ?? _currentConfig.defaultLanguage;
  String get _currentModel => _modelPerProvider[_selectedProvider] ?? _currentConfig.defaultModel;
  String get _currentRequestJson => _requestJsonPerProvider[_selectedProvider] ?? '{}';
  String get _currentSchemaJson => _schemaJsonPerProvider[_selectedProvider] ?? '{}';

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

      // Load stored settings per provider from preferences
      _loadStoredSettings();

      // Set current provider's settings
      _apiKeyController.text = _apiKeysPerProvider[_selectedProvider] ?? '';
      _hostController.text = config.host ?? '127.0.0.1';
      _portController.text = (config.port ?? 8080).toString();
      _urlController.text = config.url ?? '';

      // Initialize JSON configs for custom providers
      _initializeJsonConfigs();

      // Restore saved custom configuration if it exists
      _restoreSavedConfig(config);
    });
  }

  void _restoreSavedConfig(CustomSttConfig config) {
    if (!config.isEnabled) return;

    // Check if there are customized request values (these are only saved when advanced was customized)
    final hasCustomRequest =
        config.requestType != null || config.headers != null || config.params != null || config.audioFieldName != null;

    if (hasCustomRequest) {
      // Rebuild request JSON from saved config values
      final providerConfig = SttProviderConfig.get(config.provider);
      final defaults = providerConfig.buildRequestConfig(
        apiKey: config.apiKey,
        language: config.language ?? providerConfig.defaultLanguage,
        model: config.model ?? providerConfig.defaultModel,
      );

      final requestConfig = <String, dynamic>{};
      requestConfig['url'] = config.url ?? defaults['url'];
      requestConfig['request_type'] = config.requestType ?? defaults['request_type'];
      requestConfig['headers'] = config.headers ?? defaults['headers'];
      requestConfig['params'] = config.params ?? defaults['params'];
      if (config.audioFieldName != null || defaults['audio_field_name'] != null) {
        requestConfig['audio_field_name'] = config.audioFieldName ?? defaults['audio_field_name'];
      }

      _requestJsonPerProvider[config.provider] = const JsonEncoder.withIndent('  ').convert(requestConfig);
      _requestJsonCustomized[config.provider] = true;
    }

    // Restore custom schema if it exists
    if (config.schemaJson != null) {
      _schemaJsonPerProvider[config.provider] = const JsonEncoder.withIndent('  ').convert(config.schemaJson);
    }
  }

  void _loadStoredSettings() {
    for (final provider in SttProvider.values) {
      if (provider != SttProvider.omi) {
        final storedKey = SharedPreferencesUtil().getString('stt_api_key_${provider.name}');
        if (storedKey.isNotEmpty) {
          _apiKeysPerProvider[provider] = storedKey;
        }
        final storedLang = SharedPreferencesUtil().getString('stt_language_${provider.name}');
        if (storedLang.isNotEmpty) {
          _languagePerProvider[provider] = storedLang;
        }
        final storedModel = SharedPreferencesUtil().getString('stt_model_${provider.name}');
        if (storedModel.isNotEmpty) {
          _modelPerProvider[provider] = storedModel;
        }
      }
    }
  }

  void _initializeJsonConfigs() {
    // Initialize JSON configs for all providers
    for (final config in SttProviderConfig.allProviders) {
      _regenerateRequestJson(config.provider);
      final template = CustomSttConfig.getFullTemplateJson(config.provider);
      _schemaJsonPerProvider[config.provider] = const JsonEncoder.withIndent('  ').convert(template['response_schema']);
      _requestJsonCustomized[config.provider] = false;
    }
  }

  void _regenerateRequestJson(SttProvider provider) {
    final config = SttProviderConfig.get(provider);
    final apiKey = _apiKeysPerProvider[provider] ?? '';
    final language = _languagePerProvider[provider] ?? config.defaultLanguage;
    final model = _modelPerProvider[provider] ?? config.defaultModel;

    final requestConfig = config.buildRequestConfig(
      apiKey: apiKey,
      language: language,
      model: model,
    );
    _requestJsonPerProvider[provider] = const JsonEncoder.withIndent('  ').convert(requestConfig);
  }

  void _onLanguageOrModelChanged() {
    // Only regenerate if user hasn't customized the JSON
    if (_requestJsonCustomized[_selectedProvider] != true) {
      _regenerateRequestJson(_selectedProvider);
    }
  }

  void _saveSettingsForCurrentProvider() {
    if (_apiKeyController.text.isNotEmpty) {
      _apiKeysPerProvider[_selectedProvider] = _apiKeyController.text;
      SharedPreferencesUtil().saveString('stt_api_key_${_selectedProvider.name}', _apiKeyController.text);
    }
    if (_languagePerProvider[_selectedProvider] != null) {
      SharedPreferencesUtil()
          .saveString('stt_language_${_selectedProvider.name}', _languagePerProvider[_selectedProvider]!);
    }
    if (_modelPerProvider[_selectedProvider] != null) {
      SharedPreferencesUtil().saveString('stt_model_${_selectedProvider.name}', _modelPerProvider[_selectedProvider]!);
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
      // Save current settings for this provider
      _saveSettingsForCurrentProvider();

      Map<String, dynamic>? requestJson;
      Map<String, dynamic>? schemaJson;

      if (_showAdvanced && _currentRequestJson.isNotEmpty) {
        requestJson = jsonDecode(_currentRequestJson);
      }
      if (_showAdvanced && _currentSchemaJson.isNotEmpty) {
        schemaJson = jsonDecode(_currentSchemaJson);
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

      final config = CustomSttConfig(
        provider: _useCustomStt ? _selectedProvider : SttProvider.omi,
        apiKey: _apiKeyController.text.isNotEmpty ? _apiKeyController.text : null,
        language: _languagePerProvider[_selectedProvider],
        model: _modelPerProvider[_selectedProvider],
        url: url,
        host: _selectedProvider == SttProvider.localWhisper ? _hostController.text : null,
        port: _selectedProvider == SttProvider.localWhisper ? int.tryParse(_portController.text) : null,
        requestType: requestType,
        headers: headers,
        params: params,
        audioFieldName: audioFieldName,
        schemaJson: schemaJson,
      );

      final previousConfig = SharedPreferencesUtil().customSttConfig;
      final configChanged = previousConfig.sttConfigId != config.sttConfigId;

      await SharedPreferencesUtil().saveCustomSttConfig(config);
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
              }).toList(),
              onChanged: (provider) {
                if (provider != null) {
                  // Save current settings before switching
                  _saveSettingsForCurrentProvider();

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
        if (_currentConfig.supportedModels.isNotEmpty) ...[
          const SizedBox(height: 20),
          _buildModelSelector(),
        ],
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
          _languagePerProvider[_selectedProvider] = code;
          _onLanguageOrModelChanged();
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
          _modelPerProvider[_selectedProvider] = value.trim();
          _onLanguageOrModelChanged();
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
          key: ValueKey('${_selectedProvider.name}_$label'),
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
              final config = SttProviderConfig.get(_selectedProvider);
              return config.buildRequestConfig(
                apiKey: _apiKeysPerProvider[_selectedProvider] ?? '',
                language: _languagePerProvider[_selectedProvider] ?? config.defaultLanguage,
                model: _modelPerProvider[_selectedProvider] ?? config.defaultModel,
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
          try {
            final parsed = jsonDecode(result) as Map<String, dynamic>;
            if (parsed['url'] != null) _urlController.text = parsed['url'].toString();
            if (parsed['params'] is Map) {
              final params = parsed['params'] as Map;
              if (params['language'] != null) _languagePerProvider[_selectedProvider] = params['language'].toString();
              if (params['model'] != null) _modelPerProvider[_selectedProvider] = params['model'].toString();
            }
          } catch (_) {}

          // Mark as customized if it differs from auto-generated
          final config = SttProviderConfig.get(_selectedProvider);
          final autoGenerated = config.buildRequestConfig(
            apiKey: _apiKeysPerProvider[_selectedProvider] ?? '',
            language: _languagePerProvider[_selectedProvider] ?? config.defaultLanguage,
            model: _modelPerProvider[_selectedProvider] ?? config.defaultModel,
          );
          final autoGeneratedJson = const JsonEncoder.withIndent('  ').convert(autoGenerated);
          _requestJsonCustomized[_selectedProvider] = result != autoGeneratedJson;
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
