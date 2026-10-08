import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:version/version.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/omiglass_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:provider/provider.dart';

class OmiGlassOtaUpdate extends StatefulWidget {
  final BtDevice? device;
  final Map<String, dynamic>? latestFirmwareDetails;

  /// Test seam: answers the device connection in place of the device service. Production passes nothing.
  @visibleForTesting
  final Future<DeviceConnection?> Function(String deviceId)? connect;

  const OmiGlassOtaUpdate({super.key, this.device, this.latestFirmwareDetails, this.connect});

  @override
  State<OmiGlassOtaUpdate> createState() => _OmiGlassOtaUpdateState();
}

class _OmiGlassOtaUpdateState extends State<OmiGlassOtaUpdate> {
  final TextEditingController _ssidController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();

  bool _isLoading = false;
  bool _isUpdating = false;
  bool _isSuccess = false;
  bool _isFailed = false;

  /// What the page says under the progress ring or in the failed state. Resolved to localized text
  /// at build time ([_statusText]); raw exceptions are never shown.
  _OtaMessage _status = _OtaMessage.checking;
  OmiGlassOtaStatus? _lastOtaStatus;
  int _progress = 0;
  bool _obscurePassword = true;

  /// Native password input: the saved password stays in the controller but never in a snapshot. The
  /// row starts blank; typing or Clear marks it edited, and only an edited draft can be revealed.
  /// Clear bumps the revision so the native field starts blank again.
  int _nativePasswordRevision = 0;
  bool _nativePasswordEdited = false;
  bool _nativePasswordRevealed = false;
  StreamSubscription<int>? _sessionEvents;

  StreamSubscription? _otaStatusSubscription;
  OmiGlassConnection? _connection;
  DeviceProvider? _deviceProvider;

  // Track high progress for handling device reboot/disconnection
  bool _reachedHighProgress = false;
  Timer? _successTimer;
  static const int _highProgressThreshold = 90;
  static const Duration _successTimeout = Duration(seconds: 5);

  // Version checking state
  bool _hasUpdate = false;
  String _latestVersion = '';
  String _currentVersion = '';
  String _downloadUrl = '';
  String _changelog = '';

  @override
  void initState() {
    super.initState();
    _ssidController.text = SharedPreferencesUtil().otaWifiSsid;
    _passwordController.text = SharedPreferencesUtil().otaWifiPassword;
    _currentVersion = widget.device?.firmwareRevision ?? '';
    if (nativePresentationEnabled) {
      // A revealed draft never outlives the account session it was typed in.
      _sessionEvents = AuthService.instance.sessionGenerationEvents.listen((_) {
        if (!mounted) return;
        setState(() {
          _nativePasswordRevealed = false;
          // The previous session's draft can no longer be revealed; the field starts blank again.
          _nativePasswordEdited = false;
          _nativePasswordRevision++;
        });
      });
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
      _deviceProvider!.setOnFirmwareUpdatePage(true);
    });
    _initializeAndCheck();
  }

  @override
  void dispose() {
    _otaStatusSubscription?.cancel();
    _sessionEvents?.cancel();
    _successTimer?.cancel();
    _ssidController.dispose();
    _passwordController.dispose();
    final provider = _deviceProvider;
    if (provider != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        provider.setOnFirmwareUpdatePage(false);
        provider.resetFirmwareUpdateState();
      });
    }
    super.dispose();
  }

  Future<DeviceConnection?> _connect(String deviceId) =>
      widget.connect?.call(deviceId) ?? ServiceManager.instance().device.ensureConnection(deviceId, force: true);

  Future<void> _initializeAndCheck() async {
    setState(() {
      _isLoading = true;
      _status = _OtaMessage.checking;
    });

    try {
      // Check OTA support
      final connection = await _connect(widget.device!.id);
      if (connection is OmiGlassConnection) {
        _connection = connection;
        final isSupported = await connection.isOtaSupported();
        if (!isSupported) {
          if (mounted) {
            setState(() {
              _isFailed = true;
              _status = _OtaMessage.notSupported;
              _isLoading = false;
            });
          }
          return;
        }
      } else {
        if (mounted) {
          setState(() {
            Logger.debug('OmiGlassOtaUpdate: connection type mismatch: ${connection.runtimeType}');
            _isFailed = true;
            _status = _OtaMessage.connectFailed;
            _isLoading = false;
          });
        }
        return;
      }

      // Check for firmware updates - use provider's data if widget didn't receive details
      Map<String, dynamic> details = widget.latestFirmwareDetails ?? {};
      if (details.isEmpty && _deviceProvider != null) {
        details = _deviceProvider!.latestOmiGlassFirmwareDetails;
      }

      if (details.isNotEmpty && details['version'] != null) {
        _latestVersion = details['version'];
        _downloadUrl = details['download_url'] ?? '';
        _changelog = details['changelog'] ?? '';

        try {
          final current = Version.parse(_currentVersion);
          final latest = Version.parse(_latestVersion);
          _hasUpdate = latest > current;
        } catch (e) {
          Logger.debug('OmiGlassOtaUpdate: Version parse error: $e');
          // If we can't parse, assume update available if versions differ
          _hasUpdate = _currentVersion != _latestVersion;
        }
      }
    } catch (e) {
      Logger.debug('OmiGlassOtaUpdate: Error during init: $e');
      if (mounted) {
        setState(() {
          _isFailed = true;
          _status = _OtaMessage.connectFailed;
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _startOtaUpdate() async {
    final ssid = _ssidController.text.trim();
    final password = _passwordController.text;

    if (ssid.isEmpty) {
      OmiFeedback.error(context, context.l10n.enterWifiNetworkName);
      return;
    }

    if (password.isEmpty) {
      OmiFeedback.error(context, context.l10n.enterWifiPassword);
      return;
    }

    if (_downloadUrl.isEmpty) {
      OmiFeedback.error(context, context.l10n.otaUpdateUnavailable);
      return;
    }

    // Save credentials for next time
    SharedPreferencesUtil().otaWifiSsid = ssid;
    SharedPreferencesUtil().otaWifiPassword = password;

    setState(() {
      _isUpdating = true;
      _status = _OtaMessage.starting;
      _lastOtaStatus = null;
      _progress = 0;
      _reachedHighProgress = false;
    });
    _successTimer?.cancel();

    try {
      if (_connection == null) {
        final connection = await _connect(widget.device!.id);
        if (connection is! OmiGlassConnection) {
          throw Exception('Connection type mismatch: expected OmiGlassConnection, got ${connection.runtimeType}');
        }
        _connection = connection;
      }

      Logger.debug('OmiGlassOtaUpdate: Calling performOtaUpdate...');
      final success = await _connection!.performOtaUpdate(
        ssid: ssid,
        password: password,
        firmwareUrl: _downloadUrl,
        onStatusUpdate: _handleOtaStatus,
        onConnectionLost: _handleConnectionLost,
      );

      if (!success) {
        if (mounted) {
          setState(() {
            _isUpdating = false;
            _isFailed = true;
            _status = _OtaMessage.startFailed;
          });
        }
      }
    } catch (e) {
      Logger.debug('OmiGlassOtaUpdate: Error during OTA: $e');
      if (_reachedHighProgress) {
        _handleConnectionLost();
      } else if (mounted) {
        setState(() {
          _isUpdating = false;
          _isFailed = true;
          _status = _OtaMessage.startFailed;
        });
      }
    }
  }

  void _handleOtaStatus(OmiGlassOtaStatus status) {
    if (!mounted) return;
    _successTimer?.cancel();

    setState(() {
      _lastOtaStatus = status;
      _status = _OtaMessage.device;
      _progress = status.progress;

      if (status.progress >= _highProgressThreshold || status.isInstallComplete || status.isRebooting) {
        _reachedHighProgress = true;
      }

      if (status.isSuccess) {
        _isUpdating = false;
        _isSuccess = true;
      } else if (status.isFailed) {
        _isUpdating = false;
        _isFailed = true;
      } else if (_reachedHighProgress) {
        _startSuccessTimer();
      }
    });
  }

  void _startSuccessTimer() {
    _successTimer?.cancel();
    _successTimer = Timer(_successTimeout, () {
      if (!mounted) return;
      if (_reachedHighProgress && _isUpdating && !_isSuccess && !_isFailed) {
        setState(() {
          _isUpdating = false;
          _isSuccess = true;
        });
      }
    });
  }

  void _handleConnectionLost() {
    if (!mounted) return;
    if (_reachedHighProgress && _isUpdating && !_isSuccess && !_isFailed) {
      setState(() {
        _isUpdating = false;
        _isSuccess = true;
      });
    }
  }

  void _retry() {
    final wasConnectionProblem = _status == _OtaMessage.connectFailed;
    setState(() {
      _isFailed = false;
      _progress = 0;
    });
    if (wasConnectionProblem) _initializeAndCheck();
  }

  Future<void> _cancelUpdate() async {
    if (_connection != null) {
      await _connection!.cancelOtaUpdate();
    }
    if (!mounted) return;
    setState(() => _isUpdating = false);
    OmiFeedback.info(context, context.l10n.otaUpdateCancelled);
  }

  String get _deviceName => widget.device?.name ?? 'OmiGlass';

  /// Human, localized text for the current state; device status codes map to causes, never raw
  /// exceptions (onboarding-home #18).
  String _statusText(BuildContext context) {
    final l10n = context.l10n;
    switch (_status) {
      case _OtaMessage.checking:
        return l10n.checkingForUpdates;
      case _OtaMessage.notSupported:
        return l10n.otaNotSupported;
      case _OtaMessage.connectFailed:
        return l10n.otaConnectFailed(_deviceName);
      case _OtaMessage.starting:
        return l10n.otaStarting;
      case _OtaMessage.startFailed:
        return l10n.otaStartFailed;
      case _OtaMessage.device:
        final status = _lastOtaStatus;
        if (status == null) return l10n.otaStarting;
        if (status.isWifiConnecting) return l10n.otaWifiConnecting;
        if (status.isWifiConnected) return l10n.otaWifiConnected;
        if (status.isWifiFailed) return l10n.otaWifiFailed;
        if (status.isDownloading) return l10n.downloadingFirmware;
        if (status.isDownloadComplete || status.isInstalling) return l10n.installingFirmware;
        if (status.isDownloadFailed) return l10n.otaDownloadFailed;
        if (status.isInstallFailed) return l10n.otaInstallFailed;
        if (status.isInstallComplete || status.isRebooting) return l10n.otaRebooting(_deviceName);
        if (status.isError) return l10n.firmwareUpdateFailedMessage;
        return l10n.otaStarting;
    }
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    required String hint,
    required FaIconData icon,
    bool obscureText = false,
    Widget? suffixIcon,
  }) {
    return Container(
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
      child: TextField(
        controller: controller,
        obscureText: obscureText,
        style: OmiType.body,
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
          labelStyle: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
          prefixIcon: SizedBox(
            width: 48,
            child: Center(child: FaIcon(icon, color: OmiColors.textTertiary, size: 18)),
          ),
          prefixIconConstraints: const BoxConstraints(minWidth: 48, minHeight: 48),
          suffixIcon: suffixIcon,
          border: InputBorder.none,
          contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 18),
        ),
      ),
    );
  }

  Widget _card({required Widget child, EdgeInsetsGeometry padding = EdgeInsets.zero}) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
      child: child,
    );
  }

  Widget _warningCard(String text) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.warning.withValues(alpha: 0.12),
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.warning.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          ExcludeSemantics(
            child: FaIcon(FontAwesomeIcons.triangleExclamation, color: OmiColors.warning, size: 18),
          ),
          const SizedBox(width: 14),
          Expanded(child: Text(text, style: OmiType.subhead.copyWith(height: 1.4))),
        ],
      ),
    );
  }

  Widget _buildVersionItem(
      {required FaIconData icon, required String label, required String version, Color? chipColor}) {
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: Row(
        children: [
          SizedBox(width: 24, height: 24, child: FaIcon(icon, color: OmiColors.textTertiary, size: 18)),
          const SizedBox(width: OmiSpacing.md),
          Expanded(child: Text(label, style: OmiType.body)),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
            decoration: BoxDecoration(color: chipColor ?? OmiColors.surface2, borderRadius: OmiRadius.pillAll),
            child: Text(version, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500)),
          ),
        ],
      ),
    );
  }

  Widget _buildUpdateSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Version cards
        _card(
          child: Column(
            children: [
              _buildVersionItem(
                icon: FontAwesomeIcons.microchip,
                label: context.l10n.currentVersion,
                version: _currentVersion,
                chipColor: _hasUpdate ? OmiColors.dangerSurface : null,
              ),
              if (_hasUpdate) ...[
                Divider(height: 1, color: OmiColors.border),
                _buildVersionItem(
                  icon: FontAwesomeIcons.cloudArrowDown,
                  label: context.l10n.latestVersion,
                  version: _latestVersion,
                  chipColor: OmiColors.successSurface,
                ),
              ],
            ],
          ),
        ),

        // Up to date status line (only when not needing update)
        if (!_hasUpdate) ...[
          const SizedBox(height: OmiSpacing.md),
          Padding(
            padding: const EdgeInsets.only(left: OmiSpacing.xxs),
            child: Row(
              children: [
                Flexible(
                  child: Text(context.l10n.deviceUpToDate,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                ),
                const SizedBox(width: OmiSpacing.xs),
                FaIcon(FontAwesomeIcons.circleCheck, color: OmiColors.success, size: 14),
              ],
            ),
          ),
        ],

        // Changelog
        if (_hasUpdate && _changelog.isNotEmpty) ...[
          const SizedBox(height: OmiSpacing.xl),
          OmiSectionHeader(context.l10n.whatsNew),
          _card(
            padding: const EdgeInsets.all(OmiSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: _changelog
                  .split('\n')
                  .where((line) => line.trim().isNotEmpty)
                  .map(
                    (change) => Padding(
                      padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            margin: const EdgeInsets.only(top: 6),
                            width: 6,
                            height: 6,
                            decoration: BoxDecoration(color: OmiColors.textTertiary, shape: BoxShape.circle),
                          ),
                          const SizedBox(width: OmiSpacing.sm),
                          Expanded(
                            child: Text(
                              change.trim(),
                              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
                            ),
                          ),
                        ],
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],

        if (_hasUpdate) ...[
          const SizedBox(height: OmiSpacing.xl),
          // WiFi credentials section
          OmiSectionHeader(context.l10n.wifiConfiguration, subtitle: context.l10n.wifiConfigurationSubtitle),
          const SizedBox(height: OmiSpacing.xxs),
          _buildTextField(
            controller: _ssidController,
            label: context.l10n.networkNameSsid,
            hint: context.l10n.enterWifiNetworkName,
            icon: FontAwesomeIcons.wifi,
          ),
          const SizedBox(height: OmiSpacing.sm),
          _buildTextField(
            controller: _passwordController,
            label: context.l10n.password,
            hint: context.l10n.enterWifiPassword,
            icon: FontAwesomeIcons.lock,
            obscureText: _obscurePassword,
            suffixIcon: OmiIconButton(
              icon: FaIcon(_obscurePassword ? FontAwesomeIcons.eye : FontAwesomeIcons.eyeSlash, size: 16),
              label: _obscurePassword ? context.l10n.showPassword : context.l10n.hidePassword,
              color: OmiColors.textTertiary,
              onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
            ),
          ),
          const SizedBox(height: OmiSpacing.xl),
          // Before starting: what to do during the update.
          _warningCard(context.l10n.otaKeepNearby),
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            key: const Key('omiglass_ota_install'),
            label: context.l10n.installUpdate,
            leading: const FaIcon(FontAwesomeIcons.download),
            expand: true,
            onPressed: _startOtaUpdate,
          ),
        ],
      ],
    );
  }

  Widget _buildProgressSection() {
    final status = _statusText(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          padding: const EdgeInsets.all(OmiSpacing.xxl),
          child: Semantics(
            liveRegion: true,
            label: _progress > 0 ? '$status, $_progress%' : status,
            excludeSemantics: true,
            child: Column(
              children: [
                SizedBox(
                  width: 120,
                  height: 120,
                  child: Stack(
                    children: [
                      SizedBox(
                        width: 120,
                        height: 120,
                        child: CircularProgressIndicator(
                          // omi-ux-allow: raw-spinner -- progress ring (determinate once the device reports)
                          value: _progress > 0 ? _progress / 100 : null,
                          strokeWidth: 8,
                          backgroundColor: OmiColors.surface2,
                          valueColor: AlwaysStoppedAnimation<Color>(OmiColors.textPrimary),
                        ),
                      ),
                      if (_progress > 0) Center(child: Text('$_progress%', style: OmiType.title1)),
                    ],
                  ),
                ),
                const SizedBox(height: OmiSpacing.xl),
                Text(status, textAlign: TextAlign.center, style: OmiType.headline),
              ],
            ),
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
        _warningCard(context.l10n.firmwareUpdateWarning),
        const SizedBox(height: OmiSpacing.xl),
        OmiButton.destructive(
          key: const Key('omiglass_ota_cancel'),
          label: context.l10n.cancelUpdate,
          leading: const FaIcon(FontAwesomeIcons.xmark),
          expand: true,
          onPressed: _cancelUpdate,
        ),
      ],
    );
  }

  Widget _buildSuccessSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          padding: const EdgeInsets.all(OmiSpacing.xxl),
          child: Column(
            children: [
              Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(color: OmiColors.successSurface, shape: BoxShape.circle),
                child: Center(child: FaIcon(FontAwesomeIcons.check, color: OmiColors.success, size: 32)),
              ),
              const SizedBox(height: OmiSpacing.xl),
              Semantics(header: true, child: Text(context.l10n.firmwareUpdated, style: OmiType.title3)),
              const SizedBox(height: OmiSpacing.xs),
              Text(
                context.l10n.otaUpdatedMessage(_deviceName),
                textAlign: TextAlign.center,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
              ),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiButton(
          label: context.l10n.done,
          expand: true,
          // Back to the Home underneath, not a second Home on top of the stack.
          onPressed: () => HomeNavigation.returnHome(context),
        ),
      ],
    );
  }

  Widget _buildFailedSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          padding: const EdgeInsets.all(OmiSpacing.xxl),
          child: Semantics(
            liveRegion: true,
            child: Column(
              children: [
                Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(color: OmiColors.dangerSurface, shape: BoxShape.circle),
                  child: Center(child: FaIcon(FontAwesomeIcons.xmark, color: OmiColors.danger, size: 32)),
                ),
                const SizedBox(height: OmiSpacing.xl),
                Semantics(header: true, child: Text(context.l10n.firmwareUpdateFailedTitle, style: OmiType.title3)),
                const SizedBox(height: OmiSpacing.xs),
                Text(
                  _statusText(context),
                  textAlign: TextAlign.center,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiButton(
          label: context.l10n.tryAgain,
          leading: const FaIcon(FontAwesomeIcons.arrowRotateLeft),
          expand: true,
          onPressed: _retry,
        ),
        const SizedBox(height: OmiSpacing.xs),
        OmiButton.secondary(
          label: context.l10n.contactSupportAction,
          expand: true,
          onPressed: () => IntercomManager.instance.intercom.displayMessenger(),
        ),
      ],
    );
  }

  Widget _buildLoadingSection() {
    return _card(
      padding: const EdgeInsets.all(48),
      child: OmiSpinner(label: _statusText(context)),
    );
  }

  Widget _buildContent() {
    if (_isLoading) return _buildLoadingSection();
    if (_isSuccess) return _buildSuccessSection();
    if (_isFailed) return _buildFailedSection();
    if (_isUpdating) return _buildProgressSection();
    return _buildUpdateSection();
  }

  List<NativeRow> _nativeUpdateRows() {
    final l10n = context.l10n;
    return [
      NativeRow('ota_current', l10n.currentVersion,
          kind: 'label', subtitle: _currentVersion, symbol: 'cpu', destructive: _hasUpdate),
      if (_hasUpdate)
        NativeRow('ota_latest', l10n.latestVersion,
            kind: 'label', subtitle: _latestVersion, symbol: 'icloud.and.arrow.down'),
      if (!_hasUpdate) NativeRow('ota_up_to_date', l10n.deviceUpToDate, kind: 'label', symbol: 'checkmark.circle'),
    ];
  }

  /// One section per [_buildContent] branch, built from this State; every action calls its existing handler.
  List<NativeSection> _nativeSections() {
    final l10n = context.l10n;
    if (_isLoading) return const [];
    if (_isSuccess) {
      return [
        NativeSection('ota_result', [
          NativeRow('ota_success', l10n.firmwareUpdated,
              kind: 'label', subtitle: l10n.otaUpdatedMessage(_deviceName), symbol: 'checkmark.circle'),
          // Back to the Home underneath, not a second Home on top of the stack.
          NativeRow('ota_done', l10n.done, symbol: 'checkmark', action: (_) => HomeNavigation.returnHome(context)),
        ]),
      ];
    }
    if (_isFailed) {
      return [
        NativeSection('ota_result', [
          NativeRow('ota_failed', l10n.firmwareUpdateFailedTitle,
              kind: 'label', subtitle: _statusText(context), symbol: 'xmark.circle', destructive: true),
          NativeRow('ota_retry', l10n.tryAgain, symbol: 'arrow.counterclockwise', action: (_) => _retry()),
          NativeRow('ota_support', l10n.contactSupportAction,
              symbol: 'questionmark.bubble', action: (_) => IntercomManager.instance.intercom.displayMessenger()),
        ]),
      ];
    }
    if (_isUpdating) {
      final status = _statusText(context);
      final progress = _progress.clamp(0, 100);
      return [
        NativeSection('ota_status', [
          if (_progress > 0)
            NativeRow('ota_progress', status,
                kind: 'progress', subtitle: '$progress%', value: progress.toDouble(), maximumValue: 100)
          else
            NativeRow('ota_status_text', status, kind: 'label'),
          NativeRow('ota_warning', l10n.firmwareUpdateWarning, kind: 'label', symbol: 'exclamationmark.triangle'),
          NativeRow('ota_cancel', l10n.cancelUpdate,
              symbol: 'xmark', destructive: true, action: (_) => _cancelUpdate()),
        ]),
      ];
    }
    final changes = _changelog.split('\n').where((line) => line.trim().isNotEmpty).map((line) => line.trim()).toList();
    final password = _passwordController.text;
    final savedUntouched = password.isNotEmpty && !_nativePasswordEdited;
    final ssidLength = _ssidController.text.characters.length;
    return [
      NativeSection('ota_versions', _nativeUpdateRows()),
      if (_hasUpdate && changes.isNotEmpty)
        NativeSection(
            'ota_changelog',
            [
              NativeRow('ota_changes', changes.join('\n'), kind: 'rich_text', blocks: [
                for (final change in changes)
                  {
                    'kind': 'text',
                    // Literal release-note text: Markdown punctuation is escaped, never interpreted.
                    'text': change.replaceAllMapped(RegExp(r'[\\`*_\[\]<~&]'), (match) => '\\${match[0]}'),
                    'indent': 0,
                    'prefix': '•',
                  },
              ]),
            ],
            title: l10n.whatsNew),
      if (_hasUpdate) ...[
        NativeSection(
            'ota_wifi',
            [
              NativeRow('ota_ssid', l10n.networkNameSsid,
                  kind: 'text',
                  value: _ssidController.text,
                  subtitle: l10n.enterWifiNetworkName,
                  // A longer saved name stays editable rather than invalidating the screen.
                  maximumLength: math.max(128, ssidLength),
                  action: (value) => setState(() => _ssidController.text = value as String)),
              // A replacement is typed natively; the saved password never enters a snapshot.
              NativeRow('ota_password:$_nativePasswordRevision', l10n.password,
                  kind: 'text',
                  keyboard: 'password',
                  value: '',
                  subtitle: savedUntouched ? l10n.saved : l10n.enterWifiPassword, action: (value) {
                setState(() {
                  _passwordController.text = value as String;
                  _nativePasswordEdited = true;
                });
              }),
              // The native field draws only its title, so the saved-password cue is its own row.
              if (savedUntouched)
                NativeRow('ota_password_saved', l10n.password, kind: 'label', subtitle: l10n.saved, symbol: 'lock'),
              if (_nativePasswordEdited && password.isNotEmpty)
                NativeRow('ota_password_visibility', _nativePasswordRevealed ? l10n.hidePassword : l10n.showPassword,
                    symbol: _nativePasswordRevealed ? 'eye.slash' : 'eye',
                    action: (_) => setState(() => _nativePasswordRevealed = !_nativePasswordRevealed)),
              if (password.isNotEmpty)
                NativeRow('ota_password_clear', l10n.clear,
                    subtitle: l10n.password, symbol: 'delete.left', destructive: true, action: (_) {
                  setState(() {
                    _passwordController.clear();
                    _nativePasswordEdited = true;
                    _nativePasswordRevealed = false;
                    _nativePasswordRevision++;
                  });
                }),
              if (_nativePasswordRevealed && _nativePasswordEdited && password.isNotEmpty)
                NativeRow('ota_password_revealed', l10n.password, kind: 'label', subtitle: password),
            ],
            title: l10n.wifiConfiguration,
            footer: l10n.wifiConfigurationSubtitle),
        NativeSection('ota_actions', [
          NativeRow('ota_keep_nearby', l10n.otaKeepNearby, kind: 'label', symbol: 'exclamationmark.triangle'),
          NativeRow('ota_install', l10n.installUpdate, symbol: 'arrow.down.circle', action: (_) {
            setState(() => _nativePasswordRevealed = false);
            // The update outlives this command; its progress arrives in later snapshots.
            unawaited(_startOtaUpdate());
          }),
        ]),
      ],
    ];
  }

  @override
  Widget build(BuildContext context) {
    final classic = Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        automaticallyImplyLeading: false,
        leading: _isUpdating ? null : const OmiBackButton(),
        title: Text(context.l10n.firmwareUpdate),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.md),
          child: _buildContent(),
        ),
      ),
    );
    // Without a device report the progress branch has no percentage: the native spinner stands in.
    final waiting = !_isLoading && !_isSuccess && !_isFailed && _isUpdating && _progress <= 0;
    return PopScope(
      canPop: !_isUpdating,
      child: !nativePresentationEnabled
          ? classic
          : Scaffold(
              body: IosNativeSurface(
                title: context.l10n.firmwareUpdate,
                fallback: classic,
                loading: _isLoading || waiting,
                // While waiting, the status label row already names the step.
                loadingLabel: waiting ? context.l10n.pleaseWait : _statusText(context),
                toolbar: _isUpdating
                    ? const []
                    : [
                        NativeRow('ota_back', context.l10n.back,
                            symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
                      ],
                sections: _nativeSections(),
              ),
            ),
    );
  }
}

enum _OtaMessage { checking, notSupported, connectFailed, starting, startFailed, device }
