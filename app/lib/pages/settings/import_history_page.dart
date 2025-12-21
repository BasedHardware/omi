import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_picker/file_picker.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:shimmer/shimmer.dart';
import 'package:omi/backend/http/api/imports.dart';

class ImportHistoryPage extends StatefulWidget {
  const ImportHistoryPage({super.key});

  @override
  State<ImportHistoryPage> createState() => _ImportHistoryPageState();
}

class _ImportHistoryPageState extends State<ImportHistoryPage> {
  List<ImportJobResponse> _jobs = [];
  bool _isLoading = true;
  bool _isUploading = false;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _loadJobs();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadJobs() async {
    setState(() => _isLoading = true);
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
      debugPrint('Error loading import jobs: $e');
      if (mounted) {
        setState(() => _isLoading = false);
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
      debugPrint('Error refreshing jobs: $e');
    }
  }

  Future<void> _startLimitlessImport() async {
    try {
      if (!mounted) return;
      setState(() => _isUploading = true);

      // Pick ZIP file
      debugPrint('Opening file picker for ZIP...');
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['zip'],
      );

      if (result == null || result.files.isEmpty) {
        debugPrint('User cancelled file picker');
        if (mounted) {
          setState(() => _isUploading = false);
        }
        return;
      }

      final filePath = result.files.single.path;
      debugPrint('Selected file path: $filePath');

      if (filePath == null) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Text('Could not access the selected file'),
              backgroundColor: Colors.red.shade700,
            ),
          );
        }
        if (mounted) {
          setState(() => _isUploading = false);
        }
        return;
      }

      final file = File(filePath);

      // Start import
      debugPrint('Starting Limitless import...');
      final response = await startLimitlessImport(file);
      debugPrint('Import response: ${response?.jobId}');

      if (mounted) {
        setState(() => _isUploading = false);
      }

      if (response != null) {
        // Refresh the list and start polling
        await _loadJobs();

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Row(
                children: [
                  Icon(Icons.check_circle, color: Colors.white),
                  SizedBox(width: 12),
                  Expanded(
                    child: Text('Import started! You\'ll be notified when it\'s complete.'),
                  ),
                ],
              ),
              backgroundColor: Colors.green.shade700,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          );
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Row(
                children: [
                  Icon(Icons.error_outline, color: Colors.white),
                  SizedBox(width: 12),
                  Expanded(child: Text('Failed to start import. Please try again.')),
                ],
              ),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          );
        }
      }
    } on PlatformException catch (e) {
      debugPrint('FilePicker PlatformException: ${e.code} - ${e.message}');
      if (mounted) {
        setState(() => _isUploading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error opening file picker: ${e.message}'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e, stackTrace) {
      debugPrint('Import error: $e');
      debugPrint('Stack trace: $stackTrace');
      if (mounted) {
        setState(() => _isUploading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: $e'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    }
  }

  Future<void> _showDeleteLimitlessDialog() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text(
          'Delete All Limitless Conversations?',
          style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        content: Text(
          'This will permanently delete all conversations imported from Limitless. This action cannot be undone.',
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text('Cancel', style: TextStyle(color: Colors.grey.shade400)),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      // Show loading
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => const AlertDialog(
          backgroundColor: Color(0xFF1F1F25),
          content: Row(
            children: [
              CircularProgressIndicator(color: Colors.white),
              SizedBox(width: 16),
              Text('Deleting...', style: TextStyle(color: Colors.white)),
            ],
          ),
        ),
      );

      final deletedCount = await deleteLimitlessConversations();

      if (mounted) {
        Navigator.of(context).pop(); // Close loading dialog

        if (deletedCount != null) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Row(
                children: [
                  const Icon(Icons.check_circle, color: Colors.white),
                  const SizedBox(width: 12),
                  Expanded(child: Text('Deleted $deletedCount Limitless conversations')),
                ],
              ),
              backgroundColor: Colors.green.shade700,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Row(
                children: [
                  Icon(Icons.error_outline, color: Colors.white),
                  SizedBox(width: 12),
                  Expanded(child: Text('Failed to delete conversations')),
                ],
              ),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          );
        }
      }
    }
  }

  Widget _buildImportSourceCard({
    required String name,
    required String logoPath,
    required String description,
    required bool isAvailable,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(12),
          border: isAvailable ? Border.all(color: Colors.deepPurple.withValues(alpha: 0.3), width: 1) : null,
        ),
        child: Row(
          children: [
            // Logo
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Image.asset(
                logoPath,
                width: 48,
                height: 48,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) {
                  return Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: Colors.grey.shade800,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(Icons.device_unknown, color: Colors.grey),
                  );
                },
              ),
            ),
            const SizedBox(width: 16),
            // Text content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        name,
                        style: TextStyle(
                          color: isAvailable ? Colors.white : Colors.grey.shade500,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (!isAvailable) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.grey.shade800,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            'Coming Soon',
                            style: TextStyle(
                              color: Colors.grey.shade400,
                              fontSize: 10,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  if (description.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      description,
                      style: TextStyle(
                        color: Colors.grey.shade500,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            // Arrow or upload indicator
            if (isAvailable)
              _isUploading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.deepPurple,
                      ),
                    )
                  : Container(
                      width: 30,
                      height: 30,
                      decoration: BoxDecoration(
                        color: Colors.deepPurple.withValues(alpha: 0.8),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(
                        FontAwesomeIcons.plus,
                        color: Colors.white,
                        size: 16,
                      ),
                    )
            else
              Icon(
                Icons.lock_outline,
                color: Colors.grey.shade700,
                size: 20,
              ),
          ],
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
          description: 'Select the .zip file to import!',
          isAvailable: true,
          onTap: _isUploading ? () {} : _startLimitlessImport,
        ),
        // Coming soon placeholder
        Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: Colors.grey.shade800,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(Icons.devices_other, color: Colors.grey.shade600, size: 24),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Text(
                  'Other devices coming soon',
                  style: TextStyle(
                    color: Colors.grey.shade500,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildJobCard(ImportJobResponse job) {
    IconData statusIcon;
    Color statusColor;
    String statusText;

    switch (job.status) {
      case ImportJobStatus.pending:
        statusIcon = Icons.hourglass_empty;
        statusColor = Colors.orange;
        statusText = 'Pending';
        break;
      case ImportJobStatus.processing:
        statusIcon = Icons.sync;
        statusColor = Colors.blue;
        statusText = 'Processing';
        break;
      case ImportJobStatus.completed:
        statusIcon = Icons.done;
        statusColor = Colors.green;
        statusText = 'Completed';
        break;
      case ImportJobStatus.failed:
        statusIcon = Icons.error;
        statusColor = Colors.red;
        statusText = 'Failed';
        break;
    }

    // Format date/time
    String dateTimeStr = '';
    if (job.createdAt != null) {
      final now = DateTime.now();
      final today = DateTime(now.year, now.month, now.day);
      final jobDate = DateTime(job.createdAt!.year, job.createdAt!.month, job.createdAt!.day);

      if (jobDate == today) {
        dateTimeStr =
            'Today at ${job.createdAt!.hour.toString().padLeft(2, '0')}:${job.createdAt!.minute.toString().padLeft(2, '0')}';
      } else if (jobDate == today.subtract(const Duration(days: 1))) {
        dateTimeStr =
            'Yesterday at ${job.createdAt!.hour.toString().padLeft(2, '0')}:${job.createdAt!.minute.toString().padLeft(2, '0')}';
      } else {
        dateTimeStr =
            '${job.createdAt!.day}/${job.createdAt!.month}/${job.createdAt!.year} at ${job.createdAt!.hour.toString().padLeft(2, '0')}:${job.createdAt!.minute.toString().padLeft(2, '0')}';
      }
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              // Limitless logo small
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: Image.asset(
                  'assets/competitor-logos/limitless-logo.jpg',
                  width: 26,
                  height: 26,
                  fit: BoxFit.cover,
                ),
              ),
              const SizedBox(width: 8),
              // Status icon (don't show for completed)
              if (job.isProcessing)
                _RotatingSyncIcon(color: statusColor, size: 18)
              else if (job.status != ImportJobStatus.completed)
                Icon(statusIcon, color: statusColor, size: 18),
              if (job.status != ImportJobStatus.completed) const SizedBox(width: 6),
              // Status text and date
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      statusText,
                      style: TextStyle(
                        color: statusColor,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (dateTimeStr.isNotEmpty && job.status == ImportJobStatus.completed)
                      Text(
                        dateTimeStr,
                        style: TextStyle(
                          color: Colors.grey.shade600,
                          fontSize: 10,
                        ),
                      ),
                  ],
                ),
              ),
              // Conversations count badge (extreme right)
              if (job.conversationsCreated != null && job.conversationsCreated! > 0)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.green.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '${job.conversationsCreated} conversations',
                        style: TextStyle(
                          color: Colors.green.shade400,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(width: 4),
                      Icon(Icons.check_circle, color: Colors.green.shade400, size: 14),
                    ],
                  ),
                ),
            ],
          ),
          if (job.isProcessing && job.totalFiles != null && job.totalFiles! > 0) ...[
            const SizedBox(height: 16),
            Builder(builder: (context) {
              final remainingFiles = job.totalFiles! - (job.processedFiles ?? 0);
              final estimatedSeconds = (remainingFiles * 0.5).ceil(); // ~0.5 seconds per file (light import)
              String estimatedTime;
              if (estimatedSeconds < 60) {
                estimatedTime = 'Less than a minute';
              } else if (estimatedSeconds < 3600) {
                final minutes = (estimatedSeconds / 60).ceil();
                estimatedTime = '~$minutes minute${minutes == 1 ? '' : 's'}';
              } else {
                final hours = (estimatedSeconds / 3600).ceil();
                estimatedTime = '~$hours hour${hours == 1 ? '' : 's'}';
              }

              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Estimated: $estimatedTime remaining',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                      ),
                      Text(
                        '${job.processedFiles ?? 0}/${job.totalFiles}',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: job.progress,
                      backgroundColor: Colors.grey.shade800,
                      color: Colors.blue,
                      minHeight: 6,
                    ),
                  ),
                ],
              );
            }),
            const SizedBox(height: 8),
          ],
          if (job.error != null) ...[
            const SizedBox(height: 8),
            Text(
              job.error!,
              style: TextStyle(color: Colors.red.shade300, fontSize: 12),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildShimmerLoading() {
    return Column(
      children: List.generate(3, (index) {
        return Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Shimmer.fromColors(
            baseColor: Colors.grey[800]!,
            highlightColor: Colors.grey[600]!,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    // Logo shimmer
                    Container(
                      width: 26,
                      height: 26,
                      decoration: BoxDecoration(
                        color: Colors.grey[800],
                        borderRadius: BorderRadius.circular(6),
                      ),
                    ),
                    const SizedBox(width: 8),
                    // Status icon shimmer
                    Container(
                      width: 18,
                      height: 18,
                      decoration: BoxDecoration(
                        color: Colors.grey[800],
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    // Status text shimmer
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            width: 80,
                            height: 14,
                            decoration: BoxDecoration(
                              color: Colors.grey[800],
                              borderRadius: BorderRadius.circular(4),
                            ),
                          ),
                          const SizedBox(height: 4),
                          Container(
                            width: 120,
                            height: 10,
                            decoration: BoxDecoration(
                              color: Colors.grey[800],
                              borderRadius: BorderRadius.circular(4),
                            ),
                          ),
                        ],
                      ),
                    ),
                    // Badge shimmer
                    Container(
                      width: 100,
                      height: 24,
                      decoration: BoxDecoration(
                        color: Colors.grey[800],
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                  ],
                ),
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
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Text(
            'Import History',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        // Content based on state
        if (_isLoading)
          _buildShimmerLoading()
        else if (_jobs.isEmpty)
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Icon(Icons.history, color: Colors.grey.shade600, size: 24),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    'No imports yet',
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
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
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: const Text(
          'Import Data',
          style: TextStyle(fontWeight: FontWeight.w600),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, size: 20),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          Container(
            width: 36,
            height: 36,
            margin: const EdgeInsets.only(right: 8),
            child: GestureDetector(
              onTap: () {
                HapticFeedback.mediumImpact();
                _loadJobs();
              },
              child: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: Colors.grey.withValues(alpha: 0.3),
                  shape: BoxShape.circle,
                ),
                child: const Center(
                  child: FaIcon(FontAwesomeIcons.arrowsRotate, size: 16.0, color: Colors.white),
                ),
              ),
            ),
          ),
          Container(
            width: 36,
            height: 36,
            margin: const EdgeInsets.only(right: 8),
            child: PullDownButton(
              itemBuilder: (context) => [
                PullDownMenuItem(
                  title: 'Delete Imported Data',
                  iconWidget: const FaIcon(FontAwesomeIcons.trashCan, size: 16, color: Colors.red),
                  onTap: () {
                    _showDeleteLimitlessDialog();
                  },
                ),
              ],
              buttonBuilder: (context, showMenu) => GestureDetector(
                onTap: () {
                  HapticFeedback.mediumImpact();
                  showMenu();
                },
                child: Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: Colors.grey.withValues(alpha: 0.3),
                    shape: BoxShape.circle,
                  ),
                  child: const Center(
                    child: FaIcon(FontAwesomeIcons.ellipsisVertical, size: 16.0, color: Colors.white),
                  ),
                ),
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
              const SizedBox(height: 8),
              _buildImportSources(),
              const SizedBox(height: 24),
              _buildImportHistory(),
              const SizedBox(height: 32),
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
    _controller = AnimationController(
      duration: const Duration(seconds: 1),
      vsync: this,
    )..repeat();
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
        return Transform.rotate(
          angle: _controller.value * 2 * 3.14159,
          child: child,
        );
      },
      child: Icon(Icons.sync, color: widget.color, size: widget.size),
    );
  }
}
