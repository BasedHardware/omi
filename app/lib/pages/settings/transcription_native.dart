part of 'transcription_settings_page.dart';

extension _NativeTranscriptionPresentation on _TranscriptionSettingsPageState {
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
          Icon(Icons.warning_amber_rounded, color: OmiColors.warning, size: 14),
          const SizedBox(width: 6),
          Expanded(child: TranscriptionHelpText(warningText)),
        ],
      ),
    );
  }

  Widget _nativeTranscriptionSurface(Widget classic) {
    if (!iosSwiftUiEnabled) return classic;
    final l10n = context.l10n;
    final config = _currentConfig;
    final local = _selectedProvider == SttProvider.localWhisper;
    final onDevice = _selectedProvider == SttProvider.onDeviceWhisper;
    final custom = _selectedProvider == SttProvider.custom || _selectedProvider == SttProvider.customLive;
    final languageName = SttLanguages.common[_currentLanguage] ?? _currentLanguage;
    final primary = _primaryLanguage;
    final overridden = _isLanguageOverridden(_selectedProvider);
    final primaryName = primary.isEmpty ? l10n.notSet : context.read<HomeProvider>().getLanguageName(primary);
    final logs = CustomSttLogService.instance;
    NativeRow text(String id, String title, TextEditingController controller, {String? keyboard}) =>
        NativeRow(id, title, kind: 'text', value: controller.text, keyboard: keyboard, action: (value) {
          _updateNativeStt(() => controller.text = value as String);
        });
    return Scaffold(
        body: IosNativeSurface(
      title: l10n.transcription,
      largeTitle: true,
      fallback: classic,
      toolbar: [
        NativeRow('stt_back', l10n.back,
            symbol: 'chevron.left', enabled: !_isSaving, action: (_) => Navigator.of(context).maybePop()),
        NativeRow('stt_save', l10n.save, enabled: !_isSaving, action: (_) => _saveConfig()),
      ],
      sections: [
        NativeSection('stt_source', [
          NativeRow('stt_source_choice', l10n.transcription,
              kind: 'choice',
              value: _currentMode.name,
              options: {for (final mode in TranscriptionMode.values) mode.name: _modeLabel(mode)},
              enabled: !_isSaving, action: (value) async {
            _updateNativeStt(() {
              _showApiKey = false;
              _nativeKeyRevision++;
            });
            await _selectMode(TranscriptionMode.values.byName(value as String));
          }),
          if (_currentMode == TranscriptionMode.omi) ...[
            NativeRow('stt_omi_description', l10n.omiTranscriptionOptimized, kind: 'label'),
            if (context.watch<UsageProvider>().showSubscriptionUI)
              NativeRow('stt_usage', l10n.viewUsage,
                  subtitle: l10n.premiumMinutesMonth,
                  action: (_) => routeToPage(context, const UsagePage(showUpgradeDialog: true))),
          ] else
            NativeRow(
                'stt_source_description',
                _currentMode == TranscriptionMode.onDevice
                    ? l10n.audioProcessedLocally
                    : _currentMode == TranscriptionMode.omiParakeet
                        ? SttProviderConfig.get(SttProvider.omiParakeet).description
                        : l10n.payYourSttProvider,
                kind: 'label'),
        ]),
        if (_useCustomStt) ...[
          NativeSection('stt_transfer', [
            NativeRow('stt_import', l10n.importConfiguration,
                symbol: 'square.and.arrow.down', enabled: !_isSaving, action: (_) => _importConfig()),
            NativeRow('stt_export', l10n.exportConfiguration,
                symbol: 'square.and.arrow.up', enabled: !_isSaving, action: (_) => _exportConfig()),
          ]),
          if (!onDevice && _selectedProvider != SttProvider.omiParakeet)
            NativeSection('stt_provider', [
              NativeRow('stt_provider_choice', l10n.provider,
                  kind: 'choice',
                  value: _selectedProvider.name,
                  options: {
                    for (final provider in SttProviderConfig.allProviders)
                      if (provider.provider != SttProvider.onDeviceWhisper)
                        provider.provider.name: '${provider.displayName}${provider.isLive ? ' · ${l10n.live}' : ''}'
                  },
                  enabled: !_isSaving, action: (value) async {
                _updateNativeStt(() {
                  _showApiKey = false;
                  _nativeKeyRevision++;
                });
                await _selectProvider(SttProvider.values.byName(value as String));
              }),
              NativeRow('stt_provider_description', config.description, kind: 'label'),
              if (config.docsUrl != null)
                NativeRow('stt_docs', l10n.openProviderDocs,
                    symbol: 'safari', action: (_) => _launchUrl(config.docsUrl!)),
              if (!_isCodecCompatible)
                NativeRow(
                    'stt_codec_warning',
                    _sendRawAudioToOmi
                        ? l10n.deviceUsesCodec(
                            _connectedDeviceName ?? l10n.device, _connectedDeviceCodec!.customSttUnsupportedReason)
                        : l10n.transcriptionUnavailable,
                    kind: 'label',
                    symbol: 'exclamationmark.triangle'),
            ]),
          NativeSection('stt_config', [
            if (local) ...[
              text('stt_host', l10n.host, _hostController),
              text('stt_port', l10n.port, _portController, keyboard: 'decimal'),
              NativeRow('stt_local_endpoint', 'http://${_hostController.text}:${_portController.text}/inference',
                  kind: 'label'),
            ] else if (custom) ...[
              text('stt_url', _selectedProvider == SttProvider.custom ? l10n.apiUrl : l10n.websocketUrl, _urlController,
                  keyboard: 'url'),
              NativeRow('stt_endpoint_help',
                  _selectedProvider == SttProvider.custom ? l10n.enterSttHttpEndpoint : l10n.enterLiveSttWebsocket,
                  kind: 'label'),
            ] else if (onDevice) ...[
              NativeRow('stt_native_engine', l10n.usingNativeIosSpeech,
                  subtitle: l10n.nativeEngineNoDownload, kind: 'label', symbol: 'apple.logo'),
            ] else if (_selectedProvider != SttProvider.omiParakeet) ...[
              // A replacement is typed locally; the saved key never enters the routine snapshot.
              NativeRow('stt_api_key:${_selectedProvider.name}:$_nativeKeyRevision', l10n.enterApiKey,
                  kind: 'text',
                  keyboard: 'password',
                  value: '',
                  subtitle: l10n.storedLocallyNeverShared, action: (value) {
                _apiKeyController.text = value as String;
                _validateAndSetError();
              }),
              if (_apiKeyController.text.isNotEmpty) ...[
                NativeRow('stt_api_key_visibility', _showApiKey ? l10n.hideApiKey : l10n.showApiKey,
                    symbol: _showApiKey ? 'eye.slash' : 'eye',
                    action: (_) => _updateNativeStt(() => _showApiKey = !_showApiKey)),
                NativeRow('stt_api_key_clear', l10n.delete,
                    subtitle: l10n.apiKey, symbol: 'delete.left', destructive: true, action: (_) {
                  _updateNativeStt(() {
                    _apiKeyController.clear();
                    _showApiKey = false;
                    _nativeKeyRevision++;
                  });
                  _validateAndSetError();
                }),
                if (_showApiKey)
                  NativeRow('stt_api_key_revealed', l10n.apiKey, kind: 'label', subtitle: _apiKeyController.text),
              ],
              if (config.apiKeyUrl != null)
                NativeRow('stt_get_key', l10n.getApiKey,
                    symbol: 'safari', action: (_) => _launchUrl(config.apiKeyUrl!)),
            ],
          ]),
          if (!custom)
            NativeSection(
                'stt_language',
                [
                  if (overridden) ...[
                    NativeRow('stt_language_override_value', l10n.languageLabel,
                        kind: 'text',
                        value: _currentLanguage,
                        subtitle: SttLanguage.supported(_selectedProvider).map(sttLanguageLabel).join(' · '),
                        action: (value) => _updateNativeStt(
                            () => _onLanguageOrModelChanged((value as String).split(' ').first.trim(), null))),
                    NativeRow('stt_language_primary', l10n.sttUsePrimaryLanguage,
                        action: (_) => _updateNativeStt(() {
                              _languageOverridden[_selectedProvider] = false;
                              _onLanguageOrModelChanged(SttLanguage.derived(_selectedProvider, primary), null);
                              _configSyncVersion++;
                            })),
                  ] else ...[
                    NativeRow('stt_language_current', languageName,
                        kind: 'label',
                        subtitle: primary.isNotEmpty && SttLanguage.mapPrimary(_selectedProvider, primary) == null
                            ? l10n.sttPrimaryLanguageUnsupported(primaryName, languageName)
                            : l10n.sttLanguageFollowsPrimary),
                    NativeRow('stt_language_override', l10n.sttLanguageOverride,
                        action: (_) => _updateNativeStt(() {
                              _updateCurrentProviderConfig(language: _currentLanguage);
                              _languageOverridden[_selectedProvider] = true;
                              _configSyncVersion++;
                            })),
                  ],
                ],
                title: l10n.languageLabel),
          NativeSection('stt_audio', [
            NativeRow('stt_raw_audio', l10n.sendRawAudioToOmi,
                subtitle: l10n.sendRawAudioToOmiDescription,
                kind: 'toggle',
                value: _sendRawAudioToOmi,
                action: (value) => _updateNativeStt(() {
                      _sendRawAudioToOmi = value as bool;
                      _updateCurrentProviderConfig(sendRawAudioToOmi: value);
                    }))
          ]),
          if (_selectedProvider != SttProvider.omi)
            NativeSection('stt_advanced', [
              NativeRow('stt_advanced_expanded', l10n.advanced,
                  kind: 'toggle',
                  value: _showAdvanced,
                  action: (value) => _updateNativeStt(() => _showAdvanced = value as bool)),
              if (_showAdvanced) ...[
                if (config.supportedModels.isNotEmpty && !onDevice)
                  NativeRow('stt_model', l10n.modelLabel,
                      kind: 'text',
                      value: _currentModel,
                      subtitle: config.supportedModels.join(' · '),
                      action: (value) =>
                          _updateNativeStt(() => _onLanguageOrModelChanged(null, (value as String).trim()))),
                NativeRow('stt_request', l10n.requestConfiguration,
                    kind: 'navigation',
                    symbol: 'curlybraces',
                    action: (_) => _openJsonEditor(
                        title: l10n.requestConfiguration, jsonContent: _currentRequestJson, isRequest: true)),
                NativeRow('stt_schema', l10n.responseSchema,
                    kind: 'navigation',
                    symbol: 'curlybraces',
                    action: (_) => _openJsonEditor(title: l10n.responseSchema, jsonContent: _currentSchemaJson)),
                if (_requestJsonCustomized[_selectedProvider] == true)
                  NativeRow('stt_reset_request', l10n.resetRequestConfig,
                      symbol: 'arrow.counterclockwise', action: (_) => _resetRequestConfig()),
              ],
            ]),
          NativeSection(
              'stt_logs',
              [
                NativeRow('stt_logs_expanded', l10n.logs,
                    kind: 'toggle',
                    value: _nativeSttLogsExpanded,
                    action: (value) => _updateNativeStt(() => _nativeSttLogsExpanded = value as bool)),
                if (_nativeSttLogsExpanded)
                  NativeRow('stt_logs_text', logs.logs.isEmpty ? l10n.noLogsYet : logs.logsAsText, kind: 'label'),
                if (_nativeSttLogsExpanded && logs.logs.isNotEmpty)
                  NativeRow('stt_logs_copy', l10n.copyLogs,
                      symbol: 'doc.on.doc',
                      action: (_) => OmiClipboard.copy(context, logs.logsAsText, what: l10n.logs)),
              ],
              title: l10n.logs),
        ],
        if (_validationError != null)
          NativeSection('stt_validation', [NativeRow('stt_validation_error', _validationError!, kind: 'label')]),
      ],
    ));
  }
}
