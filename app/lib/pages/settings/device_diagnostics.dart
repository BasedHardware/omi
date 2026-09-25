import 'dart:convert';
import 'dart:io';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
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
    await Future.wait([_loadDiagnostics(), _loadBatteryHistory()]);
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

  Future<void> _exportDiagnostics() async {
    final deviceProvider = context.read<DeviceProvider>();
    final data = {
      'device_id': widget.deviceId,
      'exported_at': DateTime.now().toUtc().toIso8601String(),
      'firmware': deviceProvider.connectedDevice?.firmwareRevision ?? 'unknown',
      'battery': deviceProvider.batteryLevel,
      'connected_at': _diagnostics?.connectedAt ?? 0,
      'reconnection_count': _diagnostics?.reconnectionCount ?? 0,
      'fail_to_connect_count': _diagnostics?.failToConnectCount ?? 0,
      'rssi_samples': _rssiPoints.map((p) => {'ts': p.time.millisecondsSinceEpoch, 'rssi': p.rssi}).toList(),
      'battery_history': _batteryHistory.map((p) => {'ts': p.timestamp, 'level': p.level}).toList(),
      'disconnect_history': (_diagnostics?.disconnectHistory ?? [])
          .map(
            (e) => {
              'ts': e.timestamp,
              'reason': e.reason,
              'code': e.reasonCode,
              'manual': e.isManual,
              'event_type': e.eventType,
              'last_rssi': e.lastRssi,
              'connection_duration_ms': e.connectionDurationMs,
              'app_state': e.appState,
              'time_to_reconnect_ms': e.timeToReconnectMs,
              'rssi_trend': e.rssiTrend,
            },
          )
          .toList(),
    };

    // Every step here can fail — temp dir, file write, and the share sheet
    // itself. Unhandled, the whole handler is silent and the button looks dead.
    final shareTitle = context.l10n.diagnosticsExportTitle;
    try {
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
          'disconnect_count': (_diagnostics?.disconnectHistory ?? []).length,
          'reconnection_count': _diagnostics?.reconnectionCount ?? 0,
          'rssi_samples': _rssiPoints.length,
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

  void _onRssiUpdate(int rssi) {
    if (!mounted) return;
    setState(() {
      _rssiPoints.add(_RssiPoint(DateTime.now(), rssi));
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

  Color _rssiColor(int rssi) {
    if (rssi >= -60) return OmiColors.success;
    if (rssi >= -75) return OmiColors.warning;
    return OmiColors.danger;
  }

  String _rssiQuality(int rssi) {
    if (rssi >= -60) return context.l10n.excellent;
    if (rssi >= -75) return context.l10n.good;
    if (rssi >= -85) return context.l10n.fair;
    return context.l10n.weak;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.deviceDiagnostics),
        actions: [
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
                  _buildStatusCards(),
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

  Widget _buildStatusCards() {
    final deviceProvider = context.watch<DeviceProvider>();
    final battery = deviceProvider.batteryLevel;
    final connectedAt = _diagnostics?.connectedAt ?? 0;
    final reconnections = _diagnostics?.reconnectionCount ?? 0;
    final latestRssi = _rssiPoints.isNotEmpty ? _rssiPoints.last.rssi : null;

    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _statusCard(
                icon: FontAwesomeIcons.clock,
                label: context.l10n.connectionUptime,
                value: _formatUptime(connectedAt),
              ),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: _statusCard(
                icon: FontAwesomeIcons.arrowsRotate,
                label: context.l10n.reconnections,
                value: '$reconnections',
                valueColor: reconnections > 5 ? OmiColors.danger : null,
              ),
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.sm),
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: _statusCard(
                  icon: FontAwesomeIcons.batteryThreeQuarters,
                  label: context.l10n.battery,
                  value: battery >= 0 ? '$battery%' : '--',
                ),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: _statusCard(
                  icon: FontAwesomeIcons.signal,
                  label: context.l10n.signal,
                  value: latestRssi != null ? '$latestRssi dBm' : '--',
                  valueColor: latestRssi != null ? _rssiColor(latestRssi) : null,
                  subtitle: latestRssi != null ? _rssiQuality(latestRssi) : null,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _statusCard({
    required FaIconData icon,
    required String label,
    required String value,
    Color? valueColor,
    String? subtitle,
  }) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              FaIcon(icon, color: OmiColors.textTertiary, size: 14),
              const SizedBox(width: OmiSpacing.xs),
              Flexible(
                child: Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.xs),
          Text(value, style: OmiType.title3.copyWith(color: valueColor ?? OmiColors.textPrimary)),
          if (subtitle != null) ...[
            const SizedBox(height: 2),
            Text(subtitle, style: OmiType.footnote.copyWith(color: valueColor ?? OmiColors.textSecondary)),
          ],
        ],
      ),
    );
  }

  Widget _buildRssiChart() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        OmiSectionHeader(context.l10n.signalStrength),
        Container(
          height: 200,
          padding: const EdgeInsets.only(top: OmiSpacing.md, right: OmiSpacing.md, bottom: OmiSpacing.xs),
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
          child: _rssiPoints.length < 2
              ? Center(
                  child: Text(
                    _rssiPoints.isEmpty ? context.l10n.noRssiDataYet : context.l10n.collectingData,
                    style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                  ),
                )
              : LineChart(_buildLineChartData()),
        ),
      ],
    );
  }

  LineChartData _buildLineChartData() {
    final baseTime = _rssiPoints.first.time;
    final spots = _rssiPoints.asMap().entries.map((e) {
      final seconds = e.value.time.difference(baseTime).inMilliseconds / 1000.0;
      return FlSpot(seconds, e.value.rssi.toDouble());
    }).toList();

    final maxX = spots.last.x;
    final minX = spots.first.x;

    return LineChartData(
      gridData: FlGridData(
        show: true,
        drawVerticalLine: false,
        horizontalInterval: 25,
        getDrawingHorizontalLine: (value) =>
            FlLine(color: OmiColors.textPrimary.withValues(alpha: 0.06), strokeWidth: 1),
      ),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        bottomTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 28,
            interval: _xInterval(maxX - minX),
            getTitlesWidget: (value, meta) {
              return Text(context.l10n.timeCompactSecs(value.toInt()), style: _axisStyle);
            },
          ),
        ),
        leftTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 44,
            interval: 25,
            getTitlesWidget: (value, meta) {
              return Text('${value.toInt()}', style: _axisStyle);
            },
          ),
        ),
      ),
      borderData: FlBorderData(show: false),
      minY: -100,
      maxY: -25,
      minX: minX,
      maxX: maxX,
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
          color: _rssiPoints.isNotEmpty ? _rssiColor(_rssiPoints.last.rssi) : OmiColors.accent,
          barWidth: 2.5,
          isStrokeCapRound: true,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(
            show: true,
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                (_rssiPoints.isNotEmpty ? _rssiColor(_rssiPoints.last.rssi) : OmiColors.accent).withValues(alpha: 0.3),
                (_rssiPoints.isNotEmpty ? _rssiColor(_rssiPoints.last.rssi) : OmiColors.accent).withValues(alpha: 0.0),
              ],
            ),
          ),
        ),
      ],
    );
  }

  double _xInterval(double range) {
    if (range <= 15) return 5;
    if (range <= 30) return 10;
    if (range <= 60) return 15;
    return 30;
  }

  static final TextStyle _axisStyle = OmiType.caption.copyWith(color: OmiColors.textTertiary);

  Color _batteryColor(int level) {
    if (level > 50) return OmiColors.success;
    if (level > 20) return OmiColors.warning;
    return OmiColors.danger;
  }

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
            decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
            child: Row(
              children: [
                _segmentButton(context.l10n.day, _batteryDayView, () => setState(() => _batteryDayView = true)),
                _segmentButton(context.l10n.week, !_batteryDayView, () => setState(() => _batteryDayView = false)),
              ],
            ),
          ),
        ),
        Container(
          height: 200,
          padding: const EdgeInsets.only(top: OmiSpacing.md, right: OmiSpacing.md, bottom: OmiSpacing.xs),
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
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
        horizontalInterval: 25,
        getDrawingHorizontalLine: (value) =>
            FlLine(color: OmiColors.textPrimary.withValues(alpha: 0.06), strokeWidth: 1),
      ),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        bottomTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 28,
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
            interval: 25,
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
                  const FaIcon(FontAwesomeIcons.circleCheck, color: OmiColors.textTertiary, size: 32),
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

    final Color dot = isManual ? OmiColors.textTertiary : (isFail ? OmiColors.warning : OmiColors.danger);

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
