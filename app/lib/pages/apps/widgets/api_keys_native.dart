part of 'api_keys_widget.dart';

/// The native Developer API page for one app. Loading, creation and revocation stay with
/// [AddAppProvider] through the same methods as the card; rows carry only each key's label and date.
extension _NativeApiKeysPresentation on _ApiKeysWidgetState {
  Widget _nativeApiKeysSurface(AddAppProvider provider, Widget classic) {
    if (!nativePresentationEnabled) return classic;
    final l10n = context.l10n;
    final loaded = _loadedFor == widget.appId && _sessionCurrent(_loadedOwner);
    final keys = loaded ? provider.apiKeys : const <AppApiKey>[];
    return Scaffold(
      body: IosNativeSurface(
        title: l10n.developerApi,
        fallback: classic,
        loading: _isLoading && keys.isEmpty || !loaded && !_loadFailed,
        failed: !loaded && _loadFailed && !_isLoading,
        errorMessage: l10n.couldNotLoadApiKeys,
        empty: l10n.noApiKeysYet,
        onRefresh: (_) => _loadApiKeys(),
        toolbar: [
          NativeRow('app_keys_back', l10n.back,
              symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
          NativeRow('app_keys_info', l10n.aboutOmiApiKeys,
              symbol: 'info.circle',
              action: (_) =>
                  showOmiAlert(context, title: l10n.omiApiKeys, message: l10n.apiKeysDescription, okLabel: l10n.gotIt)),
          NativeRow('app_keys_create', l10n.createKey,
              symbol: 'plus', enabled: !_creating && !_isLoading, action: (_) => _createNativeApiKey()),
        ],
        sections: [
          NativeSection('app_keys', [
            for (final (index, key) in keys.indexed)
              NativeRow('app_api_key:$index', key.label,
                  kind: 'menu',
                  subtitle: OmiDateFormat.of(context).dateTime(key.createdAt),
                  symbol: 'key',
                  options: {'revoke': l10n.revokeKey},
                  enabled: _deletingKeyId == null,
                  action: (_) => _showDeleteConfirmation(key.id)),
          ]),
        ],
      ),
    );
  }

  /// Creates a key through the provider and reveals it once in the sensitive sheet. Nothing is shown
  /// when the account changed while the key was being created.
  Future<void> _createNativeApiKey() async {
    if (_creating) return;
    final l10n = context.l10n;
    final owner = AuthService.instance.captureSessionSnapshot();
    final provider = context.read<AddAppProvider>();
    _update(() => _creating = true);
    AppApiKey? created;
    try {
      created = await provider.createApiKey(widget.appId);
    } catch (e) {
      if (mounted && _sessionCurrent(owner)) OmiFeedback.error(context, l10n.failedToCreateApiKey(readableError(e)));
    } finally {
      _update(() => _creating = false);
    }
    if (created == null || !mounted || !_sessionCurrent(owner)) return;
    final secret = created.secret ?? '';
    _newKey = created;
    var classic = false;
    await showIosNativeSecretSheet(
      context,
      title: l10n.createAKey,
      message: l10n.yourNewKey,
      warning: '${l10n.pleaseCopyKeyNow}${l10n.willNotSeeAgain}',
      secretLabel: l10n.apiKey,
      secret: secret,
      copyLabel: l10n.copyToClipboard,
      doneLabel: l10n.done,
      onCopy: () => OmiClipboard.copy(context, secret, what: l10n.apiKey),
      showClassic: () async {
        classic = true;
        _showNewKeyDialog();
      },
    );
    // The classic dialog still shows the key and clears it on its own Done.
    if (classic) return;
    _newKey = null;
    _update(() {});
  }
}
