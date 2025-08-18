
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/capture_provider.dart';

class DownloadedFilesWidget extends StatefulWidget {
  const DownloadedFilesWidget({super.key});

  @override
  State<DownloadedFilesWidget> createState() => _DownloadedFilesWidgetState();
}

class _DownloadedFilesWidgetState extends State<DownloadedFilesWidget> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
      captureProvider.loadDownloadedFiles();
    });
  }

  String _formatFileSize(String fileName) {
    // Try to get actual file size (this would require additional implementation)
    return 'Downloaded';
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<CaptureProvider>(
      builder: (context, captureProvider, child) {
        final downloadedFiles = captureProvider.downloadedChunkFiles;
        
        if (downloadedFiles.isEmpty) {
          return const SizedBox.shrink();
        }
        
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Downloaded Files',
                    style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  Text(
                    '${downloadedFiles.length} files',
                    style: const TextStyle(color: Colors.grey, fontSize: 14),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1F25),
                  borderRadius: BorderRadius.circular(16.0),
                ),
                child: Column(
                  children: [
                    const Padding(
                      padding: EdgeInsets.all(16.0),
                      child: Row(
                        children: [
                          Icon(Icons.folder_copy, color: Colors.green, size: 20),
                          SizedBox(width: 8),
                          Text(
                            'Files saved to device storage',
                            style: TextStyle(color: Colors.white70, fontSize: 14),
                          ),
                        ],
                      ),
                    ),
                    const Divider(color: Color(0xFF35343B), height: 1),
                    SizedBox(
                      height: math.min(200, downloadedFiles.length * 60.0),
                      child: ListView.builder(
                        itemCount: downloadedFiles.length,
                        itemBuilder: (context, index) {
                          final fileName = downloadedFiles[index];
                          
                          return ListTile(
                            leading: const Icon(
                              Icons.file_download_done,
                              color: Colors.green,
                              size: 20
                            ),
                            title: Text(
                              fileName,
                              style: const TextStyle(color: Colors.white70, fontSize: 14),
                            ),
                            subtitle: Text(
                              _formatFileSize(fileName),
                              style: const TextStyle(color: Colors.grey, fontSize: 12),
                            ),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.share, color: Colors.blue, size: 18),
                                  onPressed: () {
                                    // TODO: Implement file sharing
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(
                                        content: Text('Share functionality for $fileName coming soon'),
                                        backgroundColor: Colors.blue,
                                      ),
                                    );
                                  },
                                ),
                                IconButton(
                                  icon: const Icon(Icons.delete, color: Colors.red, size: 18),
                                  onPressed: () async {
                                    final confirmed = await showDialog<bool>(
                                      context: context,
                                      builder: (context) => AlertDialog(
                                        backgroundColor: const Color(0xFF1F1F25),
                                        title: const Text('Delete File', style: TextStyle(color: Colors.white)),
                                        content: Text(
                                          'Are you sure you want to delete $fileName?',
                                          style: const TextStyle(color: Colors.white70),
                                        ),
                                        actions: [
                                          TextButton(
                                            onPressed: () => Navigator.of(context).pop(false),
                                            child: const Text('Cancel'),
                                          ),
                                          TextButton(
                                            onPressed: () => Navigator.of(context).pop(true),
                                            child: const Text('Delete', style: TextStyle(color: Colors.red)),
                                          ),
                                        ],
                                      ),
                                    );
                                    
                                    if (confirmed == true) {
                                      await captureProvider.deleteDownloadedFile(fileName);
                                      if (context.mounted) {
                                        ScaffoldMessenger.of(context).showSnackBar(
                                          SnackBar(
                                            content: Text('Deleted $fileName'),
                                            backgroundColor: Colors.red,
                                          ),
                                        );
                                      }
                                    }
                                  },
                                ),
                              ],
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
            ],
          ),
        );
      },
    );
  }
}
