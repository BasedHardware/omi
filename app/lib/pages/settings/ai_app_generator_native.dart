part of 'ai_app_generator_page.dart';

/// The largest generated icon that crosses to the native preview as a temporary PNG.
const _nativeIconByteLimit = 8 * 1024 * 1024;

/// Longest prompt or description excerpt a native row shows; the owner keeps the full text.
const _nativeLabelLimit = 2000;

String _nativeExcerpt(String text) =>
    text.characters.length <= _nativeLabelLimit ? text : '${text.characters.take(_nativeLabelLimit)}…';

extension _NativeAiAppGenerator on _AiAppGeneratorPageState {
  /// Follows the owner's icon bytes only while the native preview may be used. The bytes never cross
  /// the bridge: the preview reads a temporary PNG fenced to the account session that opened the page.
  void _startNativeIcon() {
    _nativeSessionOwner = AuthService.instance.captureSessionSnapshot();
    _nativeOwner = context.read<AiAppGeneratorProvider>()
      ..addListener(_syncNativeIcon)
      ..addListener(_syncNativePrice);
    // Icons an interrupted earlier page left behind (the app was killed before dispose).
    _nativePurge = _purgeNativeIcons();
    _nativeSession = AuthService.instance.sessionGenerationEvents.listen((_) {
      _nativeIconGeneration++;
      _deleteNativeIcon();
      if (mounted) _updateNative(() {});
    });
  }

  void _stopNativeIcon() {
    _nativeIconGeneration++;
    _nativeOwner?.removeListener(_syncNativeIcon);
    _nativeOwner?.removeListener(_syncNativePrice);
    _nativeOwner = null;
    unawaited(_nativeSession?.cancel());
    _deleteNativeIcon();
  }

  bool get _nativeSessionCurrent {
    final owner = _nativeSessionOwner;
    return owner != null && AuthService.instance.isSessionSnapshotCurrent(owner);
  }

  /// The price field reappears empty once the app is free again (the toggle or a clear), as the
  /// classic field does. Follows the owner instead of assigning during build.
  void _syncNativePrice() {
    if (_nativeOwner?.isPaid == false && _nativePrice.isNotEmpty) _updateNative(() => _nativePrice = '');
  }

  /// A new icon (generate or regenerate) replaces the file under a new name; clearing deletes it.
  void _syncNativeIcon() {
    final bytes = _nativeOwner?.generatedIconBytes;
    if (identical(bytes, _nativeIconBytes)) return;
    _nativeIconBytes = bytes;
    final generation = ++_nativeIconGeneration;
    _deleteNativeIcon();
    if (bytes == null || bytes.isEmpty || bytes.length > _nativeIconByteLimit || !_nativeSessionCurrent) return;
    unawaited(_writeNativeIcon(bytes, generation));
  }

  Future<void> _writeNativeIcon(Uint8List bytes, int generation) async {
    File? file;
    try {
      if (!await supportsNativePresentation()) return;
      // A new icon is written only after the leftover purge, which would otherwise delete it.
      await _nativePurge;
      final directory = Directory('${(await getTemporaryDirectory()).path}/omi_ai_generator');
      await directory.create(recursive: true);
      file = File('${directory.path}/icon_${DateTime.now().microsecondsSinceEpoch}_$generation.png');
      await file.writeAsBytes(bytes, flush: true);
    } catch (_) {
      if (file != null) unawaited(_deleteQuietly(file));
      return;
    }
    // A stale completion (a newer icon, a clear, disposal or another account) leaves nothing behind.
    final uri = nativeImageUri(file.path);
    if (!mounted || generation != _nativeIconGeneration || !_nativeSessionCurrent || uri == null) {
      unawaited(_deleteQuietly(file));
      return;
    }
    _updateNative(() {
      _nativeIconFile = file;
      _nativeIconUri = uri;
    });
  }

  void _deleteNativeIcon() {
    final file = _nativeIconFile;
    _nativeIconFile = null;
    _nativeIconUri = null;
    if (file != null) unawaited(_deleteQuietly(file));
  }

  Widget _nativeGeneratorSurface(AiAppGeneratorProvider provider, Widget classic) {
    if (!nativePresentationEnabled) return classic;
    final l10n = context.l10n;
    final generated = provider.hasGeneratedApp;
    return Scaffold(
      body: IosNativeSurface(
        title: generated ? _nativeExcerpt(provider.generatedName ?? l10n.appName) : l10n.aiAppGeneratorBannerTitle,
        fallback: classic,
        loading: !generated && provider.isGenerating,
        loadingLabel: !generated && provider.isGenerating ? _nativeGeneratingLabel(provider) : null,
        toolbar: [
          NativeRow('ai_gen_back', l10n.back, symbol: 'chevron.left', action: (_) async {
            // The prompt leaves the page (clearing it, as the classic back does); the generated
            // app steps back to the prompt through the page's PopScope.
            if (!provider.hasGeneratedApp) provider.clear();
            await Navigator.of(context).maybePop();
          }),
        ],
        sections: generated
            ? _nativeGeneratedSections(provider)
            : provider.isGenerating
                ? _nativeGeneratingSections(provider)
                : _nativePromptSections(provider),
      ),
    );
  }

  String _nativeGeneratingLabel(AiAppGeneratorProvider provider) =>
      provider.state == GenerationState.generatingApp ? context.l10n.creatingYourApp : context.l10n.generatingIcon;

  List<NativeSection> _nativePromptSections(AiAppGeneratorProvider provider) {
    final l10n = context.l10n;
    final hasText = _promptController.text.trim().isNotEmpty;
    return [
      NativeSection('ai_gen_suggestions', title: l10n.trySomethingLike, [
        if (provider.isLoadingPrompts)
          NativeRow('ai_gen_prompts_loading', l10n.loading, kind: 'label')
        else
          for (final (index, prompt) in provider.samplePrompts.indexed)
            NativeRow('ai_gen_prompt:$index', _nativeExcerpt(prompt),
                subtitle: l10n.tryIt, symbol: 'sparkles', enabled: !provider.isGenerating, action: (_) {
              OmiHaptics.light();
              _updateNative(() => _promptController.text = prompt);
            }),
      ]),
      NativeSection('ai_gen_compose', [
        NativeRow('ai_gen_prompt_text', l10n.whatShouldWeMake,
            kind: 'text',
            value: _promptController.text,
            enabled: !provider.isGenerating,
            action: (value) => _updateNative(() => _promptController.text = value as String)),
        NativeRow('ai_gen_send', l10n.send,
            symbol: 'arrow.up.circle.fill',
            enabled: hasText && !provider.isGenerating,
            action: (_) => _generateApp(provider)),
        if (provider.errorMessage != null)
          NativeRow('ai_gen_error', _nativeExcerpt(provider.errorMessage!),
              kind: 'label', symbol: 'exclamationmark.triangle', destructive: true),
      ]),
    ];
  }

  List<NativeSection> _nativeGeneratingSections(AiAppGeneratorProvider provider) {
    final l10n = context.l10n;
    final steps = [
      (l10n.creatingPlan, GenerationStep.creatingPlan),
      (l10n.developingLogic, GenerationStep.developingLogic),
      (l10n.designingApp, GenerationStep.designingApp),
      (l10n.generatingIconStep, GenerationStep.generatingIcon),
      (l10n.finalTouches, GenerationStep.finalTouches),
    ];
    final total = steps.length;
    final done = (provider.currentStepIndex + 1).clamp(0, total);
    final capabilities = provider.generatedCapabilities;
    return [
      NativeSection('ai_gen_generating', [
        NativeRow('ai_gen_progress', _nativeGeneratingLabel(provider),
            kind: 'progress',
            value: done.toDouble(),
            maximumValue: total.toDouble(),
            subtitle: '${(done / total * 100).round()}%'),
        NativeRow('ai_gen_preview', _nativeExcerpt(provider.generatedName ?? l10n.processing),
            kind: 'label',
            subtitle: provider.generatedCategory != null ? _categoryName(provider) : '',
            imageUri: _nativeIconUri),
      ]),
      NativeSection('ai_gen_steps', [
        for (final (name, step) in steps)
          NativeRow('ai_gen_step:${step.name}', name,
              kind: 'label',
              symbol: provider.currentStep.index > step.index
                  ? 'checkmark.circle.fill'
                  : provider.currentStep == step
                      ? 'circle.dotted'
                      : 'circle',
              subtitle: provider.currentStep == step ? l10n.processing : ''),
      ]),
      if (capabilities != null && capabilities.isNotEmpty)
        NativeSection('ai_gen_features', [
          NativeRow('ai_gen_features_list', l10n.features,
              kind: 'label', subtitle: _nativeExcerpt(_capabilityNames(provider).join(', '))),
        ]),
    ];
  }

  List<NativeSection> _nativeGeneratedSections(AiAppGeneratorProvider provider) {
    final l10n = context.l10n;
    final capabilities = provider.generatedCapabilities ?? const <String>[];
    final submitting = provider.state == GenerationState.submitting;
    final visibility = provider.makePublic ? l10n.publicLabel : l10n.privateLabel;
    final price = provider.isPaid ? '${provider.price.toStringAsFixed(0)} ${l10n.perMonth}' : l10n.free;
    return [
      NativeSection('ai_gen_app', [
        NativeRow('ai_gen_beta', l10n.beta, kind: 'label'),
        NativeRow('ai_gen_preview', _nativeExcerpt(provider.generatedName ?? l10n.appName),
            kind: 'label', subtitle: '${_categoryName(provider)} · $visibility · $price', imageUri: _nativeIconUri),
        NativeRow('ai_gen_regenerate_icon', l10n.aiGenRegenerateIcon,
            symbol: 'arrow.clockwise', enabled: !provider.isLoading, action: (_) => provider.regenerateIcon()),
        NativeRow('ai_gen_description', l10n.description,
            kind: 'label', subtitle: _nativeExcerpt(provider.generatedDescription ?? '')),
      ]),
      if (capabilities.contains('memories') || capabilities.contains('chat'))
        NativeSection('ai_gen_feature_list', title: l10n.features, [
          if (capabilities.contains('memories'))
            NativeRow('ai_gen_feature:memories', l10n.tailoredConversationSummaries, kind: 'label', symbol: 'doc.text'),
          if (capabilities.contains('chat'))
            NativeRow('ai_gen_feature:chat', l10n.customChatbotPersonality,
                kind: 'label', symbol: 'bubble.left.and.bubble.right'),
        ]),
      NativeSection('ai_gen_settings', footer: provider.isPaid ? l10n.perMonthLabel : '', [
        NativeRow('ai_gen_public', l10n.makePublic,
            kind: 'toggle',
            value: provider.makePublic,
            subtitle: provider.makePublic ? l10n.anyoneCanDiscover : l10n.onlyYouCanUse,
            action: (value) => provider.setMakePublic(value as bool)),
        NativeRow('ai_gen_paid', l10n.paidApp,
            kind: 'toggle',
            value: provider.isPaid,
            subtitle: provider.isPaid ? l10n.usersPayToUse : l10n.freeForEveryone,
            action: (value) => provider.setIsPaid(value as bool)),
        if (provider.isPaid)
          NativeRow('ai_gen_price', '\$ ${l10n.pricePlaceholder}',
              kind: 'text',
              value: _nativePrice,
              subtitle: l10n.perMonthLabel,
              keyboard: 'decimal',
              maximumLength: 32, action: (value) {
            _updateNative(() => _nativePrice = value as String);
            provider.setPrice(double.tryParse(value as String) ?? 0.0);
          }),
      ]),
      NativeSection('ai_gen_submit', [
        NativeRow('ai_gen_create', submitting ? l10n.creating : l10n.createApp,
            symbol: 'checkmark.circle',
            enabled: !provider.isLoading && provider.generatedIconBytes != null,
            action: (_) => _submitApp(provider)),
      ]),
    ];
  }
}

Future<void> _purgeNativeIcons() async {
  try {
    if (!await supportsNativePresentation()) return;
    final directory = Directory('${(await getTemporaryDirectory()).path}/omi_ai_generator');
    if (!await directory.exists()) return;
    // Only this page writes here, and it has written nothing yet: its first icon follows a generation.
    await for (final entry in directory.list()) {
      if (entry is File) await _deleteQuietly(entry);
    }
  } catch (_) {
    /* Best effort: the system purges its temporary directory. */
  }
}

Future<void> _deleteQuietly(File file) async {
  try {
    if (await file.exists()) await file.delete();
  } catch (_) {
    /* Best effort: the system purges its temporary directory. */
  }
}
