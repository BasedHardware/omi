part of 'app_detail.dart';

/// App-detail owns status adoption, polling intent and automatic-install receipt.
/// Presentation widgets never start probes or publish connection state.
mixin _AppSetupOwner on State<AppDetailPage>, WidgetsBindingObserver {
  App get app;
  set app(App value);
  void setIsLoading(bool value);
  Future<void> _loadSubscriptionData();
  ConnectionRead<App?>? _detailRead;
  bool _detailFailed = false;
  Future<void> _tryAutoInstallAfterSetup();
  bool setupCompleted = false;
  ConnectionWait? _setupWait;
  Future<ConnectionProbe>? _setupRead;
  ConnectionRead<ApiResult<AppSetupStatus>>? _ownedRead;
  bool _setupFailed = false;
  bool _setupWaiting = false;
  bool _autoInstallAfterSetup = false;
  int _setupCheckGeneration = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  void _resetSetup() {
    _setupCheckGeneration++;
    _setupWait?.cancel();
    _setupWait = null;
    _ownedRead?.cancel();
    _ownedRead = null;
    _setupRead = null;
    _setupWaiting = false;
    _setupFailed = false;
    setupCompleted = false;
    _autoInstallAfterSetup = false;
  }

  @override
  void dispose() {
    _detailRead?.cancel();
    _detailRead = null;
    _resetSetup();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<bool> _refreshAppDetails() async {
    if (!mounted) return false;
    final provider = context.read<AppProvider>();
    final uid = SharedPreferencesUtil().uid;
    final id = app.id;
    _detailRead?.cancel();
    final read =
        ConnectionRead(() => widget.detailReader?.call(id) ?? provider.getAppDetails(id), widget.setupProbeTimeout);
    _detailRead = read;
    setIsLoading(true);
    bool current() => mounted && identical(_detailRead, read) && app.id == id && SharedPreferencesUtil().uid == uid;
    try {
      final fresh = await read.future;
      if (!current()) return false;
      setState(() {
        _detailFailed = fresh == null;
        if (fresh != null) app = fresh;
      });
      if (fresh == null) return false;
      provider.checkIsAppOwner(app.uid);
      provider.setIsAppPublicToggled(!app.private);
      if (app.isPaid) unawaited(_loadSubscriptionData());
      return true;
    } catch (_) {
      if (current()) setState(() => _detailFailed = true);
      return false;
    } finally {
      if (current()) {
        _detailRead = null;
        setIsLoading(false);
      }
    }
  }

  Future<ConnectionProbe> _readSetup() {
    final current = _setupRead;
    if (current != null) return current;
    final generation = _setupCheckGeneration;
    final appId = app.id;
    final uid = SharedPreferencesUtil().uid;
    final url = app.externalIntegration?.setupCompletedUrl;
    bool isCurrent() =>
        mounted &&
        generation == _setupCheckGeneration &&
        app.id == appId &&
        SharedPreferencesUtil().uid == uid &&
        app.externalIntegration?.setupCompletedUrl == url;
    final owned = ConnectionRead(() => widget.setupChecker(url), widget.setupProbeTimeout);
    _ownedRead = owned;
    late final Future<ConnectionProbe> read;
    read = (() async {
      ApiResult<AppSetupStatus> result;
      try {
        result = await owned.future;
      } catch (_) {
        result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
      }
      if (!isCurrent()) return ConnectionProbe.pending;
      final completed = result is ApiSuccess<AppSetupStatus> && result.data == AppSetupStatus.completed;
      setState(() {
        if (result is ApiSuccess<AppSetupStatus>) {
          setupCompleted = completed;
        }
        _setupFailed = result is ApiFailure;
      });
      if (result is ApiFailure || (result is ApiSuccess<AppSetupStatus> && result.data == AppSetupStatus.notRequired)) {
        return ConnectionProbe.failed;
      }
      return completed ? ConnectionProbe.connected : ConnectionProbe.pending;
    })()
        .whenComplete(() {
      if (identical(_setupRead, read)) {
        _setupRead = null;
        _ownedRead = null;
      }
    });
    _setupRead = read;
    return read;
  }

  Future<void> checkSetupCompleted({bool autoInstallIfCompleted = false}) async {
    if (!app.worksExternally()) return;
    final result = await _readSetup();
    if (mounted && autoInstallIfCompleted && result == ConnectionProbe.connected && !app.enabled) {
      await _tryAutoInstallAfterSetup();
    }
  }

  void _startSetupCompletionCheck({bool autoInstallIfCompleted = false}) {
    if (!mounted) return;
    _setupWait?.cancel();
    _autoInstallAfterSetup = autoInstallIfCompleted;
    final uid = SharedPreferencesUtil().uid;
    final appId = app.id;
    final url = app.externalIntegration?.setupCompletedUrl;
    setState(() {
      _setupWaiting = true;
      _setupFailed = false;
    });
    final wait = ConnectionWait(
      probe: _readSetup,
      isCurrent: () =>
          mounted &&
          app.id == appId &&
          SharedPreferencesUtil().uid == uid &&
          app.externalIntegration?.setupCompletedUrl == url,
      probeTimeout: widget.setupProbeTimeout,
      waitTimeout: widget.setupWaitTimeout,
    );
    _setupWait = wait;
    unawaited(wait.start().then((outcome) async {
      if (!mounted || !identical(_setupWait, wait)) return;
      setState(() {
        _setupWaiting = false;
        _setupFailed = outcome == ConnectionWaitOutcome.failed || outcome == ConnectionWaitOutcome.timedOut;
      });
      if (outcome == ConnectionWaitOutcome.connected && _autoInstallAfterSetup && !app.enabled) {
        _autoInstallAfterSetup = false;
        await _tryAutoInstallAfterSetup();
      }
    }));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || !app.worksExternally()) return;
    if (_setupWait?.isActive == true) {
      _setupWait!.refresh();
    } else {
      unawaited(checkSetupCompleted());
    }
  }
}
