part of 'usage_page.dart';

extension _UsageSharing on _UsagePageState {
  Future<void> _shareUsage() async {
    // Capture context-dependent values before async gaps
    final session = AuthService.instance.captureSessionSnapshot();
    bool current() => mounted && session != null && AuthService.instance.isSessionSnapshotCurrent(session);
    if (!current()) return;
    final l10n = context.l10n;
    final provider = context.read<UsageProvider>();
    final localeName = l10n.localeName;
    final sharePeriod = _getPeriodForIndex(_tabController.index);

    final ui.Image image;
    final nativeImage = await _nativeUsage.captureImage();
    if (!current()) return;
    if (nativeImage != null) {
      final codec = await ui.instantiateImageCodec(nativeImage);
      image = (await codec.getNextFrame()).image;
      codec.dispose();
    } else {
      final captureContext = _screenshotKeys[_tabController.index].currentContext;
      if (captureContext == null || !captureContext.mounted) return;
      final boundary = captureContext.findRenderObject() as RenderRepaintBoundary;
      image = await boundary.toImage(pixelRatio: 3.0);
    }
    if (!current()) {
      image.dispose();
      return;
    }
    ui.Image? logoImage;
    ui.Image? watermarkedImage;
    File? file;
    try {
      // Load logo
      final ByteData logoData = await rootBundle.load('assets/images/herologo.png');
      final ui.Codec codec = await ui.instantiateImageCodec(logoData.buffer.asUint8List());
      final ui.FrameInfo fi = await codec.getNextFrame();
      logoImage = fi.image;
      codec.dispose();
      if (!current()) return;

      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);

      // Draw the original image
      canvas.drawImage(image, Offset.zero, Paint());

      // Prepare the watermark text
      final textPainter = TextPainter(
        text: TextSpan(
          text: 'omi.me',
          style: OmiType.footnote.apply(fontSizeFactor: 3).copyWith(
                color: OmiColors.textPrimary.withValues(alpha: 0.8),
                fontWeight: FontWeight.w600,
              ),
        ),
        textDirection: ui.TextDirection.ltr,
      );
      textPainter.layout();

      // Define sizes and padding
      const double logoHeight = 20 * 3.0; // Scaled logo height
      final double logoWidth = (logoImage.width / logoImage.height) * logoHeight;
      const double padding = 4 * 3.0;
      final double totalWatermarkWidth = logoWidth + padding + textPainter.width;
      final double totalWatermarkHeight = logoHeight > textPainter.height ? logoHeight : textPainter.height;

      // Position and draw the watermark at the bottom right
      final double xPos = image.width - totalWatermarkWidth - (16 * 3.0);
      final double yPos = image.height - totalWatermarkHeight - (16 * 3.0);

      // Draw logo
      final logoRect = Rect.fromLTWH(xPos, yPos + (totalWatermarkHeight - logoHeight) / 2, logoWidth, logoHeight);
      canvas.drawImageRect(
        logoImage,
        Rect.fromLTWH(0, 0, logoImage.width.toDouble(), logoImage.height.toDouble()),
        logoRect,
        Paint(),
      );

      // Draw text
      textPainter.paint(
        canvas,
        Offset(xPos + logoWidth + padding, yPos + (totalWatermarkHeight - textPainter.height) / 2),
      );

      // Convert the canvas to a new image and then to bytes
      final picture = recorder.endRecording();
      try {
        watermarkedImage = await picture.toImage(image.width, image.height);
      } finally {
        picture.dispose();
      }
      final ByteData? byteData = await watermarkedImage.toByteData(format: ui.ImageByteFormat.png);
      if (byteData == null) {
        if (mounted && current()) OmiFeedback.error(context, l10n.wrappedFailedToShare);
        return;
      }
      final Uint8List pngBytes = byteData.buffer.asUint8List();

      if (!current()) return;
      final tempDir = await getTemporaryDirectory();
      if (!current()) return;
      file = await File('${tempDir.path}/omi_usage.png').create();
      await file.writeAsBytes(pngBytes);

      if (!current()) return;
      final period = sharePeriod;
      UsageStats? stats;
      String periodTitle = l10n.today;
      switch (period) {
        case 'today':
          stats = provider.todayUsage;
          periodTitle = l10n.today;
          break;
        case 'monthly':
          stats = provider.monthlyUsage;
          periodTitle = l10n.thisMonth;
          break;
        case 'yearly':
          stats = provider.yearlyUsage;
          periodTitle = l10n.thisYear;
          break;
        case 'all_time':
          stats = provider.allTimeUsage;
          periodTitle = l10n.allTime;
          break;
      }

      final numberFormatter = NumberFormat.decimalPattern(localeName);

      String shareText;
      final baseText = l10n.shareStatsMessage;

      if (stats != null) {
        final transcriptionMinutes = (stats.transcriptionSeconds / 60).round();
        final List<String> funStats = [];

        if (transcriptionMinutes > 0) {
          funStats.add(l10n.shareStatsListened(numberFormatter.format(transcriptionMinutes)));
        }
        if (stats.wordsTranscribed > 0) {
          funStats.add(l10n.shareStatsWords(numberFormatter.format(stats.wordsTranscribed)));
        }
        if (stats.insightsGained > 0) {
          funStats.add(l10n.shareStatsInsights(numberFormatter.format(stats.insightsGained)));
        }
        if (stats.memoriesCreated > 0) {
          funStats.add(l10n.shareStatsMemories(numberFormatter.format(stats.memoriesCreated)));
        }

        if (funStats.isNotEmpty) {
          String periodText;
          if (periodTitle == l10n.today) {
            periodText = l10n.sharePeriodToday;
          } else if (periodTitle == l10n.thisMonth) {
            periodText = l10n.sharePeriodMonth;
          } else if (periodTitle == l10n.thisYear) {
            periodText = l10n.sharePeriodYear;
          } else if (periodTitle == l10n.allTime) {
            periodText = l10n.sharePeriodAllTime;
          } else {
            periodText = l10n.omiHas;
          }
          shareText = '$baseText\n\n$periodText\n${funStats.join('\n')}';
        } else {
          shareText = baseText;
        }
      } else {
        shareText = baseText;
      }

      if (!current()) return;
      final outcome = await SharePlus.instance.share(
        ShareParams(
          files: [XFile(file.path)],
          subject: periodTitle.isEmpty ? null : periodTitle,
          text: shareText.isEmpty ? null : shareText,
          sharePositionOrigin: shareSheetOrigin(_shareButtonKey),
        ),
      );
      if (!current()) return;
      final targetApp = outcome.status == ShareResultStatus.success ? shareTargetApp(outcome.raw) : null;
      PlatformManager.instance.analytics.track('Usage Stats Shared', properties: {
        'period': sharePeriod,
        'share_status': outcome.status.name,
        if (targetApp != null) 'target_app': targetApp,
      });
    } finally {
      image.dispose();
      logoImage?.dispose();
      watermarkedImage?.dispose();
      if (file != null && await file.exists()) await file.delete();
    }
  }
}
