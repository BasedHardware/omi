import 'dart:convert';
import 'dart:io';

import 'package:clock/clock.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/share_sheet.dart';

class DeviceDiagnostics extends StatefulWidget {
  final String deviceId;

  const DeviceDiagnostics({super.key, required this.deviceId});

  @override
  State<DeviceDiagnostics> createState() => _DeviceDiagnosticsState();
}

class _DeviceDiagnosticsState extends State<DeviceDiagnostics> {
  final List<_RssiPoint> _rssiPoints = [];
  static const int _maxRssiPoints = 120;

  List<BleBatteryPoint> _batteryHistory = [];
  bool _batteryDayView = true;

  BleDeviceDiagnostics? _diagnostics;
  bool _isLoading = true;
  bool _isSending = false;

  /// When native started counting reconnections / failed connects. Null while
  /// extended diagnostics are unavailable; the page then shows lifetime counts.
  int? _countersSinceMs;
  final _bleHostApi = BleHostApi();
  final GlobalKey _shareButtonKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.track('Diagnostics Opened');
    _loadAll();
    _startRssiStreaming();
  }

  @override
  void dispose() {
    _stopRssiStreaming();
    super.dispose();
  }

  Future<void> _loadAll() async {
    await Future.wait([_loadDiagnostics(), _loadBatteryHistory(), _loadCountersSince()]);
    if (mounted) {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _loadDiagnostics() async {
    try {
      final diagnostics = await _bleHostApi.getDeviceDiagnostics(widget.deviceId);
      if (mounted) {
        setState(() => _diagnostics = diagnostics);
      }
    } catch (_) {}
  }

  Future<void> _loadCountersSince() async {
    num? since;
    try {
      final extended = jsonDecode(await _bleHostApi.getExtendedDeviceDiagnostics(widget.deviceId));
      since = (extended as Map?)?['counters_since'] as num?;
    } catch (_) {
      // Extended diagnostics are best-effort; the page falls back to lifetime counts.
    }
    if (mounted) {
      setState(() => _countersSinceMs = since?.toInt());
    }
  }

  int _recentWindowStart(int countersSinceMs) {
    final cutoff = clock.now().millisecondsSinceEpoch - const Duration(days: 7).inMilliseconds;
    return countersSinceMs > cutoff ? countersSinceMs : cutoff;
  }

  /// The connection summary the page shows, over the window since [_countersSinceMs] (bounded by
  /// the native history's 7-day retention). Its window counts mirror `reconnection_count_window`
  /// and `fail_to_connect_count_window` in [_buildBundle].
  DiagnosticsSummary get _summary => summarizeDiagnostics(
        _diagnostics?.disconnectHistory ?? const [],
        nowMs: clock.now().millisecondsSinceEpoch,
        sinceMs: _countersSinceMs == null ? null : _recentWindowStart(_countersSinceMs!),
      );

  Future<void> _loadBatteryHistory() async {
    try {
      final history = await _bleHostApi.getBatteryHistory(widget.deviceId);
      if (mounted) {
        setState(() => _batteryHistory = history);
      }
    } catch (e) {
      debugPrint('[DeviceDiagnostics] getBatteryHistory failed: $e');
    }
  }

  void _startRssiStreaming() {
    BleBridge.instance.registerRssiCallback(widget.deviceId, _onRssiUpdate);
    _bleHostApi.startRssiStreaming(widget.deviceId);
  }

  void _stopRssiStreaming() {
    _bleHostApi.stopRssiStreaming(widget.deviceId);
    BleBridge.instance.unregisterRssiCallback(widget.deviceId);
  }

  Future<Map<String, dynamic>> _buildBundle() async {
    final deviceProvider = context.read<DeviceProvider>();
    final device = deviceProvider.pairedDevice ?? deviceProvider.connectedDevice;
    final package = await PackageInfo.fromPlatform();
    final phoneModel = Platform.isIOS
        ? (await DeviceInfoPlugin().iosInfo).utsname.machine
        : (await DeviceInfoPlugin().androidInfo).model;
    final diagnostics = await _bleHostApi.getDeviceDiagnostics(widget.deviceId);
    Map<String, dynamic> extended = {};
    try {
      extended = jsonDecode(await _bleHostApi.getExtendedDeviceDiagnostics(widget.deviceId)) as Map<String, dynamic>;
    } catch (_) {}
    final disconnects = (extended['disconnect_history_v2'] as List? ?? []).whereType<Map>().toList();
    final since = extended['counters_since'] as num?;
    final sinceMs = since?.toInt() ?? DateTime.now().millisecondsSinceEpoch;
    final windowStart = _recentWindowStart(sinceMs);
    return {
      'schema_version': 2,
      'device_id': widget.deviceId,
      'exported_at': DateTime.now().toUtc().toIso8601String(),
      'app_version': package.version,
      'app_build': package.buildNumber,
      'platform': Platform.operatingSystem,
      'os_version': Platform.operatingSystemVersion,
      'phone_model': phoneModel,
      'device_model': device?.modelNumber,
      'hardware_revision': device?.hardwareRevision,
      'firmware': device?.firmwareRevision,
      'timezone_offset_minutes': DateTime.now().timeZoneOffset.inMinutes,
      'battery': deviceProvider.batteryLevel,
      'charging': deviceProvider.isCharging,
      'connected_at': diagnostics.connectedAt,
      'reconnection_count': diagnostics.reconnectionCount,
      'fail_to_connect_count': diagnostics.failToConnectCount,
      'counters_since': {'reconnection_count': sinceMs, 'fail_to_connect_count': sinceMs},
      'reconnection_count_window': disconnects
          .where((e) => (e['timestamp'] as num? ?? 0) >= windowStart && (e['timeToReconnectMs'] as num? ?? 0) > 0)
          .length,
      'fail_to_connect_count_window': disconnects
          .where((e) => (e['timestamp'] as num? ?? 0) >= windowStart && e['eventType'] == 'fail_to_connect')
          .length,
      'rssi_samples': extended['rssi_samples'] ?? [],
      'battery_history': extended['battery_history_v2'] ??
          _batteryHistory.map((p) => {'ts': p.timestamp, 'level': p.level, 'charging': null}).toList(),
      'disconnect_history': disconnects
          .map(
            (e) => {
              'ts': e['timestamp'],
              'reason': e['reason'],
              'code': e['reasonCode'],
              'manual': e['isManual'],
              'event_type': e['eventType'],
              'last_rssi': e['lastRssi'],
              'last_rssi_age_ms': e['lastRssiAgeMs'],
              'connection_duration_ms': e['connectionDurationMs'],
              'app_state': e['appState'],
              'time_to_reconnect_ms': e['timeToReconnectMs'],
              'rssi_trend': e['rssiTrend'],
              'lost_audio_seconds': e['lostAudioSeconds'],
              'audio_packets_received': e['audioPacketsReceived'],
              'audio_packets_expected': e['audioPacketsExpected'],
            },
          )
          .toList(),
      'audio_packets_received_current': extended['audio_packets_received'],
      'audio_packets_expected_current': extended['audio_packets_expected'],
      'offline_storage_used_bytes': deviceProvider.ringStatus?.usedBytes,
      'offline_storage_backlog_bytes': deviceProvider.ringStatus?.usedBytes,
      'offline_storage_unread_packets': deviceProvider.ringStatus?.unreadPackets,
      'firmware_diagnostics': extended['firmware_diagnostics'] ?? [],
      'firmware_diagnostics_latest': (extended['firmware_diagnostics'] as List?)?.lastOrNull,
      'lifecycle_events': extended['lifecycle_events'] ?? [],
      'ble_log': extended['ble_log'] ?? [],
      'capture_health': extended['capture_health'] ?? {},
      'capture_health_history': extended['capture_health_history'] ?? [],
    };
  }

  Future<void> _exportDiagnostics() async {
    // Every step here can fail — temp dir, file write, and the share sheet
    // itself. Unhandled, the whole handler is silent and the button looks dead.
    final shareTitle = context.l10n.diagnosticsExportTitle;
    try {
      final data = await _buildBundle();
      final json = const JsonEncoder.withIndent('  ').convert(data);
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/omi_diagnostics_${DateTime.now().millisecondsSinceEpoch}.json');
      await file.writeAsString(json);
      await SharePlus.instance.share(
        ShareParams(
          files: [XFile(file.path)],
          title: shareTitle,
          subject: shareTitle,
          sharePositionOrigin: shareSheetOrigin(_shareButtonKey),
        ),
      );
      PlatformManager.instance.analytics.track(
        'Diagnostics Exported',
        properties: {
          'disconnect_count': (data['disconnect_history'] as List).length,
          'reconnection_count': data['reconnection_count'],
          'rssi_samples': (data['rssi_samples'] as List).length,
        },
      );
    } catch (e) {
      Logger.debug('Failed to export diagnostics: $e');
      if (!mounted) return;
      OmiFeedback.error(
        context,
        context.l10n.diagnosticsShareFailed,
        actionLabel: context.l10n.tryAgain,
        onAction: _exportDiagnostics,
      );
    }
  }

  /// Failure telemetry for the support send. Sizes and counts only — never
  /// bundle content or device identifiers.
  void _trackSendFailed(
    DiagnosticsSendFailedFailureStage stage,
    String json,
    Map<String, dynamic> bundle, {
    int statusCode = 0,
  }) {
    PlatformManager.instance.analytics.diagnosticsSendFailed(
      failureStage: stage,
      bundleBytes: utf8.encode(json).length,
      disconnectCount: (bundle['disconnect_history'] as List?)?.length ?? 0,
      schemaVersion: (bundle['schema_version'] as num?)?.toInt() ?? 0,
      statusCode: statusCode,
    );
  }

  void _trackSent(String json, Map<String, dynamic> bundle) {
    PlatformManager.instance.analytics.diagnosticsSent(
      bundleBytes: utf8.encode(json).length,
      disconnectCount: (bundle['disconnect_history'] as List?)?.length ?? 0,
      schemaVersion: (bundle['schema_version'] as num?)?.toInt() ?? 0,
    );
  }

  Future<void> _sendToSupport() async {
    if (_isSending) return;
    Map<String, dynamic> bundle;
    String json;
    try {
      bundle = await _buildBundle();
      json = const JsonEncoder.withIndent('  ').convert(bundle);
    } catch (e) {
      Logger.debug('Failed to build diagnostics bundle: $e');
      PlatformManager.instance.analytics.diagnosticsSendFailed(
        failureStage: DiagnosticsSendFailedFailureStage.buildBundle,
      );
      if (mounted) OmiFeedback.error(context, context.l10n.deviceDiagnosticsUploadFailed);
      return;
    }
    if (!mounted) return;
    final send = await showDialog<bool>(
      context: context,
      builder: (context) => OmiAlertDialog(
        title: context.l10n.sendToSupport,
        content: SizedBox(
          width: 520,
          height: 400,
          child: Column(
            children: [
              Text(context.l10n.deviceDiagnosticsUploadDescription),
              const SizedBox(height: 12),
              Expanded(child: SingleChildScrollView(child: SelectableText(json))),
            ],
          ),
        ),
        actions: [
          OmiDialogAction(label: context.l10n.cancel, onPressed: () => Navigator.pop(context, false)),
          OmiDialogAction(label: context.l10n.send, isDefault: true, onPressed: () => Navigator.pop(context, true)),
        ],
      ),
    );
    if (send != true) {
      _trackSendFailed(DiagnosticsSendFailedFailureStage.dialogCancelled, json, bundle);
      return;
    }
    if (!mounted) return;
    setState(() => _isSending = true);
    String ticket;
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/mobile/device-diagnostics',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'bundle_base64': base64Encode(utf8.encode(json))}),
        method: 'POST',
      );
      if (response?.statusCode != 201) {
        throw _SendFailure(DiagnosticsSendFailedFailureStage.upload, response?.statusCode ?? 0);
      }
      try {
        ticket = (jsonDecode(response!.body) as Map<String, dynamic>)['ticket'] as String;
      } catch (_) {
        // A 201 whose body is not a ticket is not an HTTP failure.
        throw const _SendFailure(DiagnosticsSendFailedFailureStage.ticketParse, 0);
      }
    } on _SendFailure catch (failure) {
      // Single choke point: every failed send emits exactly one failure event,
      // whichever branch discovered the failure.
      Logger.debug('Failed to send diagnostics to support: ${failure.stage}');
      _trackSendFailed(failure.stage, json, bundle, statusCode: failure.statusCode);
      if (mounted) OmiFeedback.error(context, context.l10n.deviceDiagnosticsUploadFailed);
      return;
    } catch (e) {
      // A throw out of makeApiCall never produced an HTTP response.
      Logger.debug('Failed to send diagnostics to support: $e');
      _trackSendFailed(DiagnosticsSendFailedFailureStage.upload, json, bundle);
      if (mounted) OmiFeedback.error(context, context.l10n.deviceDiagnosticsUploadFailed);
      return;
    } finally {
      if (mounted) setState(() => _isSending = false);
    }
    _trackSent(json, bundle);
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => OmiAlertDialog(
        title: context.l10n.deviceDiagnosticsTicket,
        content: SelectableText(ticket),
        actions: [OmiDialogAction(label: context.l10n.ok, isDefault: true, onPressed: () => Navigator.pop(context))],
      ),
    );
  }

  void _onRssiUpdate(int rssi) {
    if (!mounted) return;
    setState(() {
      _rssiPoints.add(_RssiPoint(clock.now(), rssi));
      if (_rssiPoints.length > _maxRssiPoints) {
        _rssiPoints.removeAt(0);
      }
    });
  }

  String _formatUptime(int connectedAtMs) {
    if (connectedAtMs == 0) return '--';
    final connected = DateTime.fromMillisecondsSinceEpoch(connectedAtMs);
    return OmiDuration.compact(DateTime.now().difference(connected).inSeconds, context.l10n);
  }

  Color _rssiColor(int rssi) => diagnosticsSignalColor(rssi);

  String _rssiQuality(int rssi) {
    final l10n = context.l10n;
    return switch (diagnosticsSignalFor(rssi)) {
      DiagnosticsSignal.excellent => l10n.excellent,
      DiagnosticsSignal.good => l10n.good,
      DiagnosticsSignal.fair => l10n.fair,
      DiagnosticsSignal.weak => l10n.weak,
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.deviceDiagnostics),
        actions: [
          OmiIconButton(
            icon: const Icon(Icons.support_agent),
            label: context.l10n.sendToSupport,
            onPressed: _isSending ? null : _sendToSupport,
          ),
          OmiIconButton(
            key: _shareButtonKey,
            icon: const Icon(Icons.ios_share),
            label: context.l10n.share,
            onPressed: _exportDiagnostics,
          ),
        ],
      ),
      body: _isLoading
          ? const OmiLoadingState()
          : SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildRightNow(),
                  const SizedBox(height: OmiSpacing.xl),
                  _buildWeek(),
                  const SizedBox(height: OmiSpacing.xl),
                  _buildRssiChart(),
                  const SizedBox(height: OmiSpacing.xl),
                  _buildBatteryChart(),
                  const SizedBox(height: OmiSpacing.xl),
                  _buildDisconnectHistory(),
                  const SizedBox(height: OmiSpacing.xxl),
                ],
              ),
            ),
    );
  }

  Widget _buildRightNow() {
    final l10n = context.l10n;
    final battery = context.watch<DeviceProvider>().batteryLevel;
    final latestRssi = _rssiPoints.isNotEmpty ? _rssiPoints.last.rssi : null;
    return OmiSettingsGroup(
      header: l10n.diagnosticsRightNow,
      children: [
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.clock),
          title: l10n.diagnosticsConnectedFor,
          value: _formatUptime(_diagnostics?.connectedAt ?? 0),
        ),
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.batteryThreeQuarters),
          title: l10n.battery,
          value: battery >= 0 ? '$battery%' : '--',
        ),
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.signal),
          title: l10n.signal,
          value: latestRssi == null ? '--' : null,
          trailing: latestRssi == null
              ? null
              : _valueStack(_rssiQuality(latestRssi), detail: '$latestRssi dBm', dot: _rssiColor(latestRssi)),
        ),
      ],
    );
  }

  /// The week verdict, then neutral counts. Lifetime counters read catastrophic after months of
  /// pairing (10k+ reconnections), so the 7-day window leads and the lifetime numbers sit in the
  /// footnote. Without a window anchor the rows fall back to the lifetime counts, labelled so.
  Widget _buildWeek() {
    final l10n = context.l10n;
    final summary = _summary;
    final windowed = _countersSinceMs != null;
    final lifetimeDrops = _diagnostics?.reconnectionCount ?? 0;
    final lifetimeFails = _diagnostics?.failToConnectCount ?? 0;
    final median = summary.medianReconnectMs;
    final longest = summary.longestGapMs;
    final rate = windowed ? summary.dropsPerHour : null;

    return OmiSettingsGroup(
      header: l10n.diagnosticsLast7Days,
      footer: windowed ? l10n.diagnosticsSincePairingSummary(lifetimeDrops, lifetimeFails) : null,
      children: [
        if (summary.hasTrouble)
          OmiSettingsRow(
            key: const Key('diagnostics_verdict_trouble'),
            leading: FaIcon(FontAwesomeIcons.plugCircleXmark, color: OmiColors.danger),
            title: l10n.diagnosticsVerdictTrouble,
            subtitle: l10n.diagnosticsVerdictTroubleDetail(summary.failedLast24h),
          )
        else
          OmiSettingsRow(
            key: const Key('diagnostics_verdict_ok'),
            leading: FaIcon(FontAwesomeIcons.circleCheck, color: OmiColors.success),
            title: l10n.diagnosticsVerdictReconnects,
            subtitle: median == null
                ? l10n.diagnosticsVerdictNoDrops
                : l10n.diagnosticsVerdictReconnectsDetail(_formatDurationMs(median)),
          ),
        OmiSettingsRow(
          title: l10n.diagnosticsDrops,
          value:
              rate == null ? (windowed ? '${summary.drops}' : l10n.diagnosticsCountSincePairing(lifetimeDrops)) : null,
          trailing: rate == null ? null : _valueStack('${summary.drops}', detail: l10n.diagnosticsDropsPerHour(rate)),
        ),
        OmiSettingsRow(title: l10n.diagnosticsLongestGap, value: longest == null ? '--' : _formatDurationMs(longest)),
        OmiSettingsRow(
          title: l10n.failedConnections,
          value: windowed ? '${summary.failed}' : l10n.diagnosticsCountSincePairing(lifetimeFails),
        ),
      ],
    );
  }

  /// A row's trailing value with an optional second line and leading status dot. The value is
  /// always neutral text; colour only ever appears on the dot.
  Widget _valueStack(String value, {String? detail, Color? dot}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (dot != null) ...[
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(shape: BoxShape.circle, color: dot),
              ),
              const SizedBox(width: 6),
            ],
            Text(value, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ],
        ),
        if (detail != null) Text(detail, style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
      ],
    );
  }

  static const int _rssiWindowSecs = 60;
  static const double _rssiMin = -100;
  static const double _rssiMax = -40;

  Widget _buildRssiChart() {
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        OmiSectionHeader(
          l10n.signalStrength,
          trailing: Text(
            l10n.diagnosticsLastDuration(l10n.timeCompactSecs(_rssiWindowSecs)),
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
          ),
        ),
        Container(
          height: 140,
          padding: const EdgeInsets.all(OmiSpacing.md),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
          child: _rssiPoints.length < 2
              ? Center(
                  child: Text(
                    _rssiPoints.isEmpty ? l10n.noRssiDataYet : l10n.collectingData,
                    style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                  ),
                )
              : LineChart(_buildLineChartData(), duration: Duration.zero),
        ),
      ],
    );
  }

  /// Fixed −100…−40 dBm over the last [_rssiWindowSecs], newest sample at the right edge, with the
  /// axis labels on the left level with their grid lines.
  LineChartData _buildLineChartData() {
    final latest = _rssiPoints.last.time;
    final spots = [
      for (final p in _rssiPoints)
        if (latest.difference(p.time).inMilliseconds <= _rssiWindowSecs * 1000)
          FlSpot(-latest.difference(p.time).inMilliseconds / 1000.0, p.rssi.toDouble().clamp(_rssiMin, _rssiMax)),
    ];
    final color = _rssiColor(_rssiPoints.last.rssi);

    return LineChartData(
      gridData: FlGridData(
        show: true,
        drawVerticalLine: false,
        horizontalInterval: 20,
        getDrawingHorizontalLine: (value) =>
            FlLine(color: OmiColors.textPrimary.withValues(alpha: 0.06), strokeWidth: 1),
      ),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        bottomTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        leftTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 36,
            interval: 20,
            getTitlesWidget: (value, meta) => Text('${value.toInt()}', style: _axisStyle),
          ),
        ),
      ),
      borderData: FlBorderData(show: false),
      clipData: const FlClipData.all(),
      minY: _rssiMin,
      maxY: _rssiMax,
      minX: -_rssiWindowSecs.toDouble(),
      maxX: 0,
      lineTouchData: LineTouchData(
        touchTooltipData: LineTouchTooltipData(
          getTooltipColor: (_) => OmiColors.surface2,
          getTooltipItems: (touchedSpots) {
            return touchedSpots.map((spot) {
              return LineTooltipItem(
                '${spot.y.toInt()} dBm',
                OmiType.footnote.copyWith(color: _rssiColor(spot.y.toInt()), fontWeight: FontWeight.w600),
              );
            }).toList();
          },
        ),
      ),
      lineBarsData: [
        LineChartBarData(
          spots: spots,
          isCurved: true,
          curveSmoothness: 0.2,
          color: color,
          barWidth: 2.5,
          isStrokeCapRound: true,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(
            show: true,
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [color.withValues(alpha: 0.25), color.withValues(alpha: 0.0)],
            ),
          ),
        ),
      ],
    );
  }

  static final TextStyle _axisStyle = OmiType.caption.copyWith(color: OmiColors.textTertiary);

  Color _batteryColor(int level) => diagnosticsBatteryColor(level);

  Widget _buildBatteryChart() {
    final now = DateTime.now().millisecondsSinceEpoch;
    final windowMs = _batteryDayView ? 24 * 3600 * 1000 : 7 * 24 * 3600 * 1000;
    final cutoff = now - windowMs;
    final points = _batteryHistory.where((p) => p.timestamp >= cutoff).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        OmiSectionHeader(
          context.l10n.batteryHistory,
          trailing: Container(
            padding: const EdgeInsets.all(2),
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
            child: Row(
              children: [
                _segmentButton(context.l10n.day, _batteryDayView, () => setState(() => _batteryDayView = true)),
                _segmentButton(context.l10n.week, !_batteryDayView, () => setState(() => _batteryDayView = false)),
              ],
            ),
          ),
        ),
        Container(
          height: 104,
          padding: const EdgeInsets.only(top: OmiSpacing.sm, right: OmiSpacing.md, bottom: OmiSpacing.xxs),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
          child: points.length < 2
              ? Center(
                  child: Text(
                    context.l10n.noBatteryDataYet,
                    style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                  ),
                )
              : LineChart(_buildBatteryLineChartData(points)),
        ),
      ],
    );
  }

  Widget _segmentButton(String label, bool active, VoidCallback onTap) {
    return Semantics(
      button: true,
      selected: active,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          if (active) return;
          OmiHaptics.selection();
          onTap();
        },
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
          decoration: BoxDecoration(
            color: active ? OmiColors.surface3 : Colors.transparent,
            borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.sm - 2)),
          ),
          child: Text(
            label,
            style: OmiType.footnote.copyWith(
              color: active ? OmiColors.textPrimary : OmiColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ),
    );
  }

  LineChartData _buildBatteryLineChartData(List<BleBatteryPoint> points) {
    final now = DateTime.now().millisecondsSinceEpoch;
    final spots = points.map((p) {
      final hoursAgo = (now - p.timestamp) / 3600000.0;
      return FlSpot(-hoursAgo, p.level.toDouble());
    }).toList();

    final minX = spots.first.x;
    final maxX = spots.last.x;
    final lastLevel = points.last.level.toInt();

    return LineChartData(
      gridData: FlGridData(
        show: true,
        drawVerticalLine: false,
        horizontalInterval: 50,
        getDrawingHorizontalLine: (value) =>
            FlLine(color: OmiColors.textPrimary.withValues(alpha: 0.06), strokeWidth: 1),
      ),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        bottomTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 22,
            interval: _batteryDayView ? 4 : 24,
            getTitlesWidget: (value, meta) {
              final h = value.abs();
              final l10n = context.l10n;
              return Text(
                _batteryDayView ? l10n.timeCompactHours(h.toInt()) : l10n.timeCompactDays((h / 24).toInt()),
                style: _axisStyle,
              );
            },
          ),
        ),
        leftTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 36,
            interval: 100,
            getTitlesWidget: (value, meta) {
              return Text('${value.toInt()}', style: _axisStyle);
            },
          ),
        ),
      ),
      borderData: FlBorderData(show: false),
      minY: 0,
      maxY: 100,
      minX: minX,
      maxX: maxX,
      lineTouchData: LineTouchData(
        touchTooltipData: LineTouchTooltipData(
          getTooltipColor: (_) => OmiColors.surface2,
          getTooltipItems: (touchedSpots) {
            return touchedSpots.map((spot) {
              final level = spot.y.toInt();
              final secondsAgo = (spot.x.abs() * 3600).round();
              final timeLabel = context.l10n.durationAgo(OmiDuration.compact(secondsAgo, context.l10n));
              return LineTooltipItem(
                '$level%\n$timeLabel',
                OmiType.footnote.copyWith(color: _batteryColor(level), fontWeight: FontWeight.w600),
              );
            }).toList();
          },
        ),
      ),
      lineBarsData: [
        LineChartBarData(
          spots: spots,
          isCurved: true,
          curveSmoothness: 0.2,
          color: _batteryColor(lastLevel),
          barWidth: 2.5,
          isStrokeCapRound: true,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(
            show: true,
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                _batteryColor(lastLevel).withValues(alpha: 0.3),
                _batteryColor(lastLevel).withValues(alpha: 0.0),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDisconnectHistory() {
    final history = _diagnostics?.disconnectHistory ?? [];

    if (history.isEmpty) {
      return OmiSettingsGroup(
        header: context.l10n.disconnectHistory,
        children: [
          Padding(
            padding: const EdgeInsets.all(OmiSpacing.xl),
            child: Center(
              child: Column(
                children: [
                  FaIcon(FontAwesomeIcons.circleCheck, color: OmiColors.textTertiary, size: 32),
                  const SizedBox(height: OmiSpacing.sm),
                  Text(
                    context.l10n.noDisconnectsRecorded,
                    style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                  ),
                ],
              ),
            ),
          ),
        ],
      );
    }
    return OmiSettingsGroup(
      header: context.l10n.disconnectHistory,
      headerSubtitle: context.l10n.lastNEvents(history.length),
      children: [for (final event in history.reversed) _buildDisconnectRow(event)],
    );
  }

  /// Month, day and time to the second: diagnostics compare events seconds apart, so this is
  /// [OmiDateFormat]'s locale and 24-hour setting with seconds added.
  String _formatEventTime(DateTime time) {
    final dates = OmiDateFormat.of(context);
    final format = DateFormat.MMMd(dates.localeName);
    return (dates.use24HourFormat ? format.add_Hms() : format.add_jms()).format(time);
  }

  Widget _buildDisconnectRow(BleDisconnectEvent event) {
    final l10n = context.l10n;
    final timeStr = _formatEventTime(DateTime.fromMillisecondsSinceEpoch(event.timestamp));
    final isManual = event.isManual;
    final isFail = event.eventType == 'fail_to_connect';
    final reason = _formatReason(event.reason);

    // A drop is routine (the pendant buffers audio through the gap, and a missing reconnect time
    // can just mean the app restarted), so only a failed connect keeps a status colour: red within
    // the verdict's 24-hour window, amber before it.
    final recentFail = isFail && event.timestamp >= clock.now().millisecondsSinceEpoch - 24 * 3600 * 1000;
    final Color dot = recentFail ? OmiColors.danger : (isFail ? OmiColors.warning : OmiColors.textTertiary);

    final metaParts = <String>[];
    if (event.rssiTrend.isNotEmpty) metaParts.add(event.rssiTrend);
    if (event.lastRssi != 0) metaParts.add('${event.lastRssi} dBm');
    if (event.connectionDurationMs > 0) metaParts.add(_formatDurationMs(event.connectionDurationMs));
    if (event.appState.isNotEmpty) metaParts.add(event.appState);
    if (event.timeToReconnectMs > 0) {
      metaParts.add(l10n.diagnosticsReconnectedIn(_formatDurationMs(event.timeToReconnectMs)));
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(shape: BoxShape.circle, color: dot),
            ),
          ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(reason, style: OmiType.subhead),
                const SizedBox(height: 2),
                Text(timeStr, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                if (metaParts.isNotEmpty) ...[
                  const SizedBox(height: OmiSpacing.xxs),
                  Text(metaParts.join(' · '), style: OmiType.caption.copyWith(color: OmiColors.textSecondary)),
                ],
              ],
            ),
          ),
          if (isFail)
            _badge(l10n.diagnosticsFailBadge, OmiColors.warning, OmiColors.warning.withValues(alpha: 0.15))
          else if (isManual)
            _badge(l10n.manual, OmiColors.textTertiary, OmiColors.surface2),
        ],
      ),
    );
  }

  Widget _badge(String label, Color color, Color background) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 3),
      decoration: BoxDecoration(color: background, borderRadius: OmiRadius.smAll),
      child: Text(label, style: OmiType.caption.copyWith(color: color)),
    );
  }

  String _formatDurationMs(int ms) {
    if (ms < 1000) return '$ms ms';
    return OmiDuration.compact((ms / 1000).round(), context.l10n);
  }

  String _formatReason(String reason) {
    switch (reason) {
      case 'clean_disconnect':
        return context.l10n.cleanDisconnect;
      case 'connection_timeout':
        return context.l10n.connectionTimeout;
      case 'remote_device_terminated':
        return context.l10n.remoteDeviceTerminated;
      case 'paired_to_another_phone':
        return context.l10n.pairedToAnotherPhone;
      case 'link_key_mismatch':
        return context.l10n.linkKeyMismatch;
      case 'connection_failed_instant_passed':
        return context.l10n.connectionFailed;
      case 'app_closed':
        return context.l10n.appClosed;
      case 'manual':
        return context.l10n.manualDisconnect;
      default:
        if (reason.startsWith('gatt_error_')) {
          return context.l10n.gattError(reason.replaceFirst('gatt_error_', ''));
        }
        return reason;
    }
  }
}

class _RssiPoint {
  final DateTime time;
  final int rssi;

  _RssiPoint(this.time, this.rssi);
}

/// A failed support send whose failure event has not been emitted yet; the
/// single catch in `_sendToSupport` emits exactly one per failure. [statusCode]
/// is the real HTTP status, or 0 when no HTTP response was involved.
class _SendFailure implements Exception {
  const _SendFailure(this.stage, this.statusCode);

  final DiagnosticsSendFailedFailureStage stage;
  final int statusCode;

  @override
  String toString() => '_SendFailure($stage, statusCode: $statusCode)';
}

/// Signal quality bands. The quality word, the Right Now dot and the chart colour all come from
/// these, so the word and the colour can never disagree.
enum DiagnosticsSignal { excellent, good, fair, weak }

@visibleForTesting
DiagnosticsSignal diagnosticsSignalFor(int rssi) {
  if (rssi >= -60) return DiagnosticsSignal.excellent;
  if (rssi >= -75) return DiagnosticsSignal.good;
  if (rssi >= -85) return DiagnosticsSignal.fair;
  return DiagnosticsSignal.weak;
}

/// Excellent and Good are success, Fair is warning, Weak is danger.
@visibleForTesting
Color diagnosticsSignalColor(int rssi) => switch (diagnosticsSignalFor(rssi)) {
      DiagnosticsSignal.excellent || DiagnosticsSignal.good => OmiColors.success,
      DiagnosticsSignal.fair => OmiColors.warning,
      DiagnosticsSignal.weak => OmiColors.danger,
    };

/// Success above 20%, warning at 11–20%, danger at 10% and below.
@visibleForTesting
Color diagnosticsBatteryColor(int level) {
  if (level > 20) return OmiColors.success;
  if (level > 10) return OmiColors.warning;
  return OmiColors.danger;
}

/// The Last 7 Days numbers and verdict, computed from the native disconnect history.
@visibleForTesting
class DiagnosticsSummary {
  const DiagnosticsSummary({
    required this.drops,
    required this.failed,
    required this.failedLast24h,
    this.medianReconnectMs,
    this.longestGapMs,
    this.dropsPerHour,
  });

  /// Disconnects that reconnected on their own, in the window.
  final int drops;

  /// Connect attempts that never established, in the window.
  final int failed;

  /// Connect attempts that never established in the last 24 hours, whatever the window.
  final int failedLast24h;

  /// Median and longest `timeToReconnectMs` over [drops]; null without drops.
  final int? medianReconnectMs;
  final int? longestGapMs;

  /// Average drops an hour, rounded; null when the window is unknown or under an hour, or the
  /// rate rounds to zero.
  final int? dropsPerHour;

  /// The verdict. Long gaps are informational (the pendant buffers audio and syncs it later), so
  /// only a recent failed connection turns it.
  bool get hasTrouble => failedLast24h > 0;
}

/// Summarises [history] since [sinceMs] (the whole history, which native keeps for 7 days, when
/// null).
@visibleForTesting
DiagnosticsSummary summarizeDiagnostics(List<BleDisconnectEvent> history, {required int nowMs, int? sinceMs}) {
  const hourMs = 3600 * 1000;
  const weekMs = 7 * 24 * hourMs;
  final window = sinceMs == null ? history : history.where((e) => e.timestamp >= sinceMs).toList();
  final gaps = [
    for (final e in window)
      if (e.timeToReconnectMs > 0) e.timeToReconnectMs,
  ]..sort();
  int? median;
  if (gaps.isNotEmpty) {
    final mid = gaps.length ~/ 2;
    median = gaps.length.isOdd ? gaps[mid] : ((gaps[mid - 1] + gaps[mid]) / 2).round();
  }
  int? perHour;
  if (sinceMs != null && gaps.isNotEmpty) {
    final start = sinceMs > nowMs - weekMs ? sinceMs : nowMs - weekMs;
    final hours = (nowMs - start) / hourMs;
    if (hours >= 1) {
      final rate = (gaps.length / hours).round();
      if (rate >= 1) perHour = rate;
    }
  }
  return DiagnosticsSummary(
    drops: gaps.length,
    failed: window.where((e) => e.eventType == 'fail_to_connect').length,
    failedLast24h: history.where((e) => e.eventType == 'fail_to_connect' && e.timestamp >= nowMs - 24 * hourMs).length,
    medianReconnectMs: median,
    longestGapMs: gaps.isEmpty ? null : gaps.last,
    dropsPerHour: perHour,
  );
}
