import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:file_picker/file_picker.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/backend/http/api/imports.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// The label an import-history row shows for [createdAt]: the time today, "Yesterday at …", then
/// the date and time — in the reader's locale and clock (docs/ux-contract.md §8).
///
/// [createdAt] is a server timestamp and parses as UTC; it is projected to local time first so the
/// row lands on the reader's day.
String importJobTimestampLabel(OmiDateFormat dates, DateTime createdAt) => dates.timestamp(createdAt.toLocal());

class ImportJobCountChip {
  final int count;
  final bool skipped;

  const ImportJobCountChip({required this.count, required this.skipped});
}

List<ImportJobCountChip> importJobCountChips({int? created, int? skipped}) {
  return [
    if ((created ?? 0) > 0) ImportJobCountChip(count: created!, skipped: false),
    if ((skipped ?? 0) > 0) ImportJobCountChip(count: skipped!, skipped: true),
  ];
}

class ImportHistoryPage extends StatefulWidget {
  const ImportHistoryPage({super.key});

  @override
  State<ImportHistoryPage> createState() => _ImportHistoryPageState();
}

class _ImportHistoryPageState extends State<ImportHistoryPage> {
  List<ImportJobResponse> _jobs = [];
  bool _isLoading = true;
  bool _loadFailed = false;
  bool _isUploading = false;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.importHistoryPageOpened();
    _loadJobs();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadJobs() async {
    setState(() {
      _isLoading = true;
      _loadFailed = false;
    });
    try {
      final jobs = await getImportJobs();
      if (mounted) {
        setState(() {
          _jobs = jobs;
          _isLoading = false;
        });
        _startPollingIfNeeded();
      }
    } catch (e) {
      Logger.debug('Error loading import jobs: $e');
      if (mounted) {
        setState(() {
          _isLoading = false;
          _loadFailed = true;
        });
      }
    }
  }

  void _startPollingIfNeeded() {
    _pollTimer?.cancel();

    // Check if any jobs are still processing
    final hasProcessingJobs = _jobs.any((job) => job.isProcessing);

    if (hasProcessingJobs) {
      _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) {
        _refreshJobs();
      });
    }
  }

  Future<void> _refreshJobs() async {
    try {
      final jobs = await getImportJobs();
      if (mounted) {
        setState(() => _jobs = jobs);

        // Stop polling if no more processing jobs
        final hasProcessingJobs = jobs.any((job) => job.isProcessing);
        if (!hasProcessingJobs) {
          _pollTimer?.cancel();
        }
      }
    } catch (e) {
      Logger.debug('Error refreshing jobs: $e');
    }
  }

  Future<void> _startLimitlessImport() async {
    try {
      if (!mounted) return;
      PlatformManager.instance.analytics.importStarted(source: 'limitless');
      setState(() => _isUploading = true);

      // Pick ZIP file
      Logger.debug('Opening file picker for ZIP…');
      final result = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['zip']);

      if (result == null || result.files.isEmpty) {
        Logger.debug('User cancelled file picker');
        if (mounted) {
          setState(() => _isUploading = false);
        }
        return;
      }

      final filePath = result.files.single.path;
      Logger.debug('Selected file path: $filePath');

      if (filePath == null) {
        if (mounted) {
          OmiFeedback.error(context, context.l10n.couldNotAccessFile);
          setState(() => _isUploading = false);
        }
        return;
      }

      final file = File(filePath);

      // Start import
      Logger.debug('Starting Limitless import…');
      final response = await startLimitlessImport(file);
      Logger.debug('Import response: ${response?.jobId}');

      if (mounted) {
        setState(() => _isUploading = false);
      }

      if (response != null) {
        // Refresh the list and start polling
        await _loadJobs();
        if (mounted) OmiFeedback.confirm(context, context.l10n.importStarted);
      } else {
        if (mounted) {
          OmiFeedback.error(
            context,
            context.l10n.failedToStartImport,
            actionLabel: context.l10n.tryAgain,
            onAction: _startLimitlessImport,
          );
        }
      }
    } on PlatformException catch (e) {
      Logger.debug('FilePicker PlatformException: ${e.code} - ${e.message}');
      if (mounted) {
        setState(() => _isUploading = false);
        OmiFeedback.error(context, context.l10n.importErrorOpeningFilePicker(e.message ?? ''));
      }
    } catch (e, stackTrace) {
      Logger.debug('Import error: $e');
      Logger.debug('Stack trace: $stackTrace');
      if (mounted) {
        setState(() => _isUploading = false);
        OmiFeedback.error(context, context.l10n.importErrorGeneric(readableError(e)));
      }
    }
  }

  /// Deleting imported conversations cannot be undone, so it always confirms (contract §4).
  Future<void> _showDeleteLimitlessDialog() async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deleteAllLimitlessConversations,
      message: context.l10n.deleteAllLimitlessWarning,
      confirmLabel: context.l10n.delete,
      destructive: true,
    );
    if (!confirmed || !mounted) return;

    // Progress toast, replaced by the result.
    OmiFeedback.progress(context, context.l10n.deleting);
    final deletedCount = await deleteLimitlessConversations();
    if (!mounted) return;

    if (deletedCount != null) {
      OmiFeedback.confirm(context, context.l10n.deletedLimitlessConversations(deletedCount));
    } else {
      OmiFeedback.error(context, context.l10n.failedToDeleteConversations);
    }
  }

  Widget _buildImportSourceCard({
    required String name,
    required String logoPath,
    required String description,
    required bool isAvailable,
    required VoidCallback? onTap,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 6),
      child: MergeSemantics(
        child: Semantics(
          button: true,
          child: Material(
            color: OmiColors.surface1,
            shape: RoundedRectangleBorder(
              borderRadius: OmiRadius.mdAll,
              side: isAvailable ? const BorderSide(color: OmiColors.border) : BorderSide.none,
            ),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: onTap,
              child: Padding(
                padding: const EdgeInsets.all(OmiSpacing.md),
                child: Row(
                  children: [
                    // Logo
                    ExcludeSemantics(
                      child: ClipRRect(
                        borderRadius: OmiRadius.smAll,
                        child: Image.asset(
                          logoPath,
                          width: 48,
                          height: 48,
                          fit: BoxFit.cover,
                          errorBuilder: (context, error, stackTrace) {
                            return Container(
                              width: 48,
                              height: 48,
                              color: OmiColors.surface2,
                              child: const Icon(Icons.device_unknown, color: OmiColors.textTertiary),
                            );
                          },
                        ),
                      ),
                    ),
                    const SizedBox(width: OmiSpacing.md),
                    // Text content
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Flexible(
                                child: Text(
                                  name,
                                  style: OmiType.callout.copyWith(
                                    color: isAvailable ? OmiColors.textPrimary : OmiColors.textTertiary,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                              if (!isAvailable) ...[
                                const SizedBox(width: OmiSpacing.xs),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 2),
                                  decoration: const BoxDecoration(
                                    color: OmiColors.surface2,
                                    borderRadius: OmiRadius.smAll,
                                  ),
                                  child: Text(
                                    context.l10n.comingSoon,
                                    style: OmiType.caption.copyWith(
                                      color: OmiColors.textSecondary,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ],
                            ],
                          ),
                          if (description.isNotEmpty) ...[
                            const SizedBox(height: OmiSpacing.xxs),
                            Text(description, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                          ],
                        ],
                      ),
                    ),
                    // Arrow or upload indicator
                    if (isAvailable)
                      _isUploading
                          ? const OmiSpinner(size: OmiSpinnerSize.small)
                          : Container(
                              width: 30,
                              height: 30,
                              decoration: const BoxDecoration(color: OmiColors.accent, borderRadius: OmiRadius.smAll),
                              child: const Center(
                                child: FaIcon(FontAwesomeIcons.plus, color: OmiColors.onAccent, size: 16),
                              ),
                            )
                    else
                      const Icon(Icons.lock_outline, color: OmiColors.textTertiary, size: 20),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildImportSources() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildImportSourceCard(
          name: 'Limitless',
          logoPath: 'assets/competitor-logos/limitless-logo.jpg',
          description: context.l10n.selectZipFileToImport,
          isAvailable: true,
          onTap: _isUploading ? null : _startLimitlessImport,
        ),
        // Coming soon placeholder
        Container(
          margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 6),
          padding: const EdgeInsets.all(OmiSpacing.md),
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
                child: const Icon(Icons.devices_other, color: OmiColors.textTertiary, size: 24),
              ),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Text(
                  context.l10n.otherDevicesComingSoon,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildJobCard(ImportJobResponse job) {
    FaIconData statusIcon;
    Color statusColor;
    String statusText;

    switch (job.status) {
      case ImportJobStatus.pending:
        statusIcon = FontAwesomeIcons.hourglass;
        statusColor = OmiColors.warning;
        statusText = context.l10n.statusPending;
        break;
      case ImportJobStatus.processing:
        statusIcon = FontAwesomeIcons.arrowsRotate;
        statusColor = OmiColors.textPrimary;
        statusText = context.l10n.statusProcessing;
        break;
      case ImportJobStatus.completed:
        statusIcon = FontAwesomeIcons.check;
        statusColor = OmiColors.success;
        statusText = context.l10n.statusCompleted;
        break;
      case ImportJobStatus.failed:
        statusIcon = FontAwesomeIcons.circleExclamation;
        statusColor = OmiColors.danger;
        statusText = context.l10n.statusFailed;
        break;
    }

    final createdAt = job.createdAt;
    final String dateTimeStr = createdAt == null ? '' : importJobTimestampLabel(OmiDateFormat.of(context), createdAt);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 6),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              // Limitless logo small
              ClipRRect(
                borderRadius: const BorderRadius.all(Radius.circular(6)),
                child: Image.asset(
                  'assets/competitor-logos/limitless-logo.jpg',
                  width: 26,
                  height: 26,
                  fit: BoxFit.cover,
                ),
              ),
              const SizedBox(width: OmiSpacing.xs),
              // Status icon (don't show for completed)
              if (job.isProcessing)
                _RotatingSyncIcon(color: statusColor, size: 18)
              else if (job.status != ImportJobStatus.completed)
                FaIcon(statusIcon, color: statusColor, size: 18),
              if (job.status != ImportJobStatus.completed) const SizedBox(width: 6),
              // Status text and date
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(statusText, style: OmiType.subhead.copyWith(color: statusColor, fontWeight: FontWeight.w600)),
                    if (dateTimeStr.isNotEmpty && job.status == ImportJobStatus.completed)
                      Text(dateTimeStr, style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
              for (final chip in importJobCountChips(
                created: job.conversationsCreated,
                skipped: job.conversationsSkipped,
              ))
                Padding(
                  padding: EdgeInsets.only(left: chip.skipped && (job.conversationsCreated ?? 0) > 0 ? 6 : 0),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: OmiSpacing.xxs),
                    decoration: BoxDecoration(
                      color: chip.skipped ? OmiColors.surface2 : OmiColors.successSurface,
                      borderRadius: OmiRadius.smAll,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          context.l10n.nConversations(chip.count),
                          style: OmiType.footnote.copyWith(
                            color: chip.skipped ? OmiColors.textSecondary : OmiColors.success,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        const SizedBox(width: OmiSpacing.xxs),
                        Icon(
                          chip.skipped ? Icons.history : Icons.check_circle,
                          color: chip.skipped ? OmiColors.textSecondary : OmiColors.success,
                          size: 14,
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
          if (job.isProcessing && job.totalFiles != null && job.totalFiles! > 0) ...[
            const SizedBox(height: OmiSpacing.md),
            Builder(
              builder: (context) {
                final remainingFiles = job.totalFiles! - (job.processedFiles ?? 0);
                final estimatedSeconds = (remainingFiles * 0.5).ceil(); // ~0.5 seconds per file (light import)
                String estimatedTime;
                if (estimatedSeconds < 60) {
                  estimatedTime = context.l10n.lessThanAMinute;
                } else if (estimatedSeconds < 3600) {
                  final minutes = (estimatedSeconds / 60).ceil();
                  estimatedTime = context.l10n.estimatedMinutes(minutes);
                } else {
                  final hours = (estimatedSeconds / 3600).ceil();
                  estimatedTime = context.l10n.estimatedHours(hours);
                }

                final captionStyle = OmiType.footnote.copyWith(color: OmiColors.textSecondary);
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Flexible(child: Text(context.l10n.estimatedTimeRemaining(estimatedTime), style: captionStyle)),
                        Text('${job.processedFiles ?? 0}/${job.totalFiles}', style: captionStyle),
                      ],
                    ),
                    const SizedBox(height: OmiSpacing.sm),
                    ClipRRect(
                      borderRadius: const BorderRadius.all(Radius.circular(OmiSpacing.xxs)),
                      child: LinearProgressIndicator(
                        value: job.progress,
                        backgroundColor: OmiColors.surface3,
                        color: OmiColors.accent,
                        minHeight: 6,
                      ),
                    ),
                  ],
                );
              },
            ),
            const SizedBox(height: OmiSpacing.xs),
          ],
          if (job.error != null) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(
              job.error!,
              style: OmiType.footnote.copyWith(color: OmiColors.danger),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }

  Widget _shimmerBlock(double width, double height, {BoxShape shape = BoxShape.rectangle}) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: OmiColors.surface2,
        shape: shape,
        borderRadius: shape == BoxShape.circle ? null : const BorderRadius.all(Radius.circular(OmiSpacing.xxs)),
      ),
    );
  }

  Widget _buildShimmerLoading() {
    return Column(
      children: List.generate(3, (index) {
        return Container(
          margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 6),
          padding: const EdgeInsets.all(OmiSpacing.md),
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
          child: ShimmerWithTimeout(
            baseColor: OmiColors.surface2,
            highlightColor: OmiColors.surface3,
            child: Row(
              children: [
                _shimmerBlock(26, 26),
                const SizedBox(width: OmiSpacing.xs),
                _shimmerBlock(18, 18, shape: BoxShape.circle),
                const SizedBox(width: 6),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _shimmerBlock(80, 14),
                      const SizedBox(height: OmiSpacing.xxs),
                      _shimmerBlock(120, 10),
                    ],
                  ),
                ),
                _shimmerBlock(100, 24),
              ],
            ),
          ),
        );
      }),
    );
  }

  Widget _buildImportHistory() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Always show the header
        OmiSectionHeader(context.l10n.importHistory),
        // Content based on state
        if (_isLoading)
          _buildShimmerLoading()
        else if (_loadFailed)
          OmiErrorState(message: context.l10n.couldNotLoadImportHistory, onRetry: _loadJobs)
        else if (_jobs.isEmpty)
          Container(
            margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 6),
            padding: const EdgeInsets.all(OmiSpacing.xl),
            decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
            child: Row(
              children: [
                const Icon(Icons.history, color: OmiColors.textTertiary, size: 24),
                const SizedBox(width: OmiSpacing.md),
                Expanded(
                  child: Text(
                    context.l10n.noImportsYet,
                    style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                  ),
                ),
              ],
            ),
          )
        else
          ..._jobs.map(_buildJobCard),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.importData),
        actions: [
          OmiIconButton.filled(
            icon: const FaIcon(FontAwesomeIcons.arrowsRotate, size: 16),
            label: context.l10n.refresh,
            onPressed: () {
              OmiHaptics.medium();
              _loadJobs();
            },
          ),
          Padding(
            padding: const EdgeInsets.only(right: OmiSpacing.xxs),
            child: PullDownButton(
              itemBuilder: (context) => [
                PullDownMenuItem(
                  title: context.l10n.deleteImportedData,
                  isDestructive: true,
                  iconWidget: const FaIcon(FontAwesomeIcons.trashCan, size: 16, color: OmiColors.danger),
                  onTap: () {
                    _showDeleteLimitlessDialog();
                  },
                ),
              ],
              buttonBuilder: (context, showMenu) => OmiIconButton.filled(
                icon: const FaIcon(FontAwesomeIcons.ellipsisVertical, size: 16),
                label: context.l10n.moreOptions,
                onPressed: () {
                  OmiHaptics.medium();
                  showMenu();
                },
              ),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadJobs,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: OmiSpacing.xs),
              _buildImportSources(),
              const SizedBox(height: OmiSpacing.xl),
              _buildImportHistory(),
              const SizedBox(height: OmiSpacing.xxl),
            ],
          ),
        ),
      ),
    );
  }
}

class _RotatingSyncIcon extends StatefulWidget {
  final Color color;
  final double size;

  const _RotatingSyncIcon({required this.color, required this.size});

  @override
  State<_RotatingSyncIcon> createState() => _RotatingSyncIconState();
}

class _RotatingSyncIconState extends State<_RotatingSyncIcon> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(duration: const Duration(seconds: 1), vsync: this)..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Transform.rotate(angle: _controller.value * 2 * 3.14159, child: child);
      },
      child: Icon(Icons.sync, color: widget.color, size: widget.size),
    );
  }
}
