part of 'import_history_page.dart';

extension _NativeImportHistoryPresentation on _ImportHistoryPageState {
  Widget _nativeImportHistory(Widget classic) {
    if (!iosSwiftUiEnabled) return classic;
    final l10n = context.l10n;
    return Scaffold(
      body: IosNativeSurface(
        title: l10n.importData,
        fallback: classic,
        loading: _isLoading,
        failed: _loadFailed,
        errorMessage: l10n.couldNotLoadImportHistory,
        onRefresh: (_) => _loadJobs(),
        toolbar: [
          NativeRow('import_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
          NativeRow('import_refresh', l10n.refresh, symbol: 'arrow.clockwise', action: (_) => _loadJobs()),
          NativeRow('import_delete', l10n.deleteImportedData,
              symbol: 'trash', destructive: true, action: (_) => _showDeleteLimitlessDialog()),
        ],
        sections: [
          NativeSection('import_sources', [
            NativeRow('import_limitless', 'Limitless',
                subtitle: _isUploading ? l10n.loading : l10n.selectZipFileToImport,
                symbol: 'square.and.arrow.down',
                enabled: !_isUploading,
                action: (_) => _startLimitlessImport()),
            NativeRow('import_other_sources', l10n.otherDevicesComingSoon, kind: 'label', symbol: 'externaldrive'),
          ]),
          NativeSection(
              'import_jobs',
              [
                if (!_isLoading && !_loadFailed && _jobs.isEmpty)
                  NativeRow('import_empty', l10n.noImportsYet, kind: 'label', symbol: 'clock'),
                for (final job in _jobs) ...[
                  NativeRow(
                      'import_job:${job.jobId}',
                      switch (job.status) {
                        ImportJobStatus.pending => l10n.statusPending,
                        ImportJobStatus.processing => l10n.statusProcessing,
                        ImportJobStatus.completed => l10n.statusCompleted,
                        ImportJobStatus.failed => l10n.statusFailed,
                      },
                      kind: 'label',
                      subtitle: [
                        if (job.createdAt != null) importJobTimestampLabel(OmiDateFormat.of(context), job.createdAt!),
                        for (final chip in importJobCountChips(
                            created: job.conversationsCreated, skipped: job.conversationsSkipped))
                          '${l10n.nConversations(chip.count)} · ${chip.skipped ? l10n.skip : l10n.statusCompleted}',
                        if (job.error != null) job.error!,
                      ].join('\n')),
                  if (job.isProcessing && (job.totalFiles ?? 0) > 0)
                    NativeRow('import_progress:${job.jobId}', l10n.statusProcessing,
                        kind: 'progress',
                        value: job.progress.clamp(0, 1),
                        maximumValue: 1,
                        subtitle: '${job.processedFiles ?? 0}/${job.totalFiles}'),
                ],
              ],
              title: l10n.importHistory),
        ],
      ),
    );
  }
}
