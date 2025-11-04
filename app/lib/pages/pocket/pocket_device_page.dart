import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/pocket/pocket_models.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/pocket_connection.dart';

class PocketDevicePage extends StatefulWidget {
  final BtDevice device;
  final PocketDeviceConnection connection;

  const PocketDevicePage({
    super.key,
    required this.device,
    required this.connection,
  });

  @override
  State<PocketDevicePage> createState() => _PocketDevicePageState();
}

class _PocketDevicePageState extends State<PocketDevicePage> {
  PocketDeviceInfo? _deviceInfo;
  List<PocketRecording> _recordings = [];
  Set<String> _selectedRecordings = {};
  bool _isLoading = true; // Start with loading state
  bool _isSyncing = false;
  String? _errorMessage;
  String? _successMessage;

  @override
  void initState() {
    super.initState();
    _loadDeviceInfoThenRecordings();
  }

  Future<void> _loadDeviceInfoThenRecordings() async {
    // Load device info first
    await _loadDeviceInfo();
    // Then load recordings after device info is displayed
    if (mounted) {
      _loadRecordings();
    }
  }

  Future<void> _loadDeviceInfo() async {
    try {
      final info = await widget.connection.getDeviceInfo();
      if (mounted) {
        setState(() {
          _deviceInfo = info;
        });
      }
    } catch (e) {
      debugPrint('Error loading device info: $e');
    }
  }

  Future<void> _loadRecordings() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final recordings = await widget.connection.listRecordings();
      if (mounted) {
        setState(() {
          _recordings = recordings;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Failed to load recordings: $e';
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _downloadRecordings() async {
    if (_selectedRecordings.isEmpty && _recordings.isNotEmpty) {
      // Ask if user wants to download all
      final confirm = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Download All Recordings?'),
          content: Text('Download all ${_recordings.length} recordings?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Download All'),
            ),
          ],
        ),
      );

      if (confirm != true) return;
    }

    setState(() {
      _isSyncing = true;
      _errorMessage = null;
      _successMessage = null;
    });

    final recordingsToDownload = _selectedRecordings.isEmpty
        ? _recordings
        : _recordings.where((r) => _selectedRecordings.contains(r.recordingId)).toList();

    int successCount = 0;
    int failCount = 0;

    for (final recording in recordingsToDownload) {
      try {
        debugPrint('Downloading ${recording.filename}...');
        
        final mp3Data = await widget.connection.downloadRecording(recording);

        if (mp3Data != null) {
          // TODO: Save MP3 and create conversation
          // For now, just count as success
          successCount++;
          debugPrint('Downloaded ${recording.filename}: ${mp3Data.length} bytes');
        } else {
          failCount++;
        }
      } catch (e) {
        debugPrint('Failed to download ${recording.filename}: $e');
        failCount++;
      }
    }

    if (mounted) {
      setState(() {
        _isSyncing = false;
        _successMessage = 'Downloaded $successCount recordings';
        if (failCount > 0) {
          _errorMessage = '$failCount recordings failed';
        }
        _selectedRecordings.clear();
      });

      if (successCount > 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('✅ $_successMessage'),
            backgroundColor: Colors.green,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.device.name),
        actions: [
          if (_deviceInfo?.battery != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                children: [
                  Icon(
                    Icons.battery_std,
                    color: _deviceInfo!.battery! > 20 ? Colors.green : Colors.red,
                  ),
                  const SizedBox(width: 4),
                  Text('${_deviceInfo!.battery}%'),
                ],
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          // Device info card
          if (_deviceInfo != null)
            Card(
              margin: const EdgeInsets.all(16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.mic, size: 32),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Pocket Device',
                                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                              ),
                              if (_deviceInfo!.firmware != null)
                                Text(
                                  'Firmware: ${_deviceInfo!.firmware}',
                                  style: const TextStyle(color: Colors.grey),
                                ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    if (_deviceInfo!.storageUsedMB != null && _deviceInfo!.storageTotalMB != null) ...[
                      const SizedBox(height: 12),
                      const Divider(),
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Storage:'),
                          Text(
                            '${_deviceInfo!.storageUsedMB!.toStringAsFixed(1)} MB / '
                            '${_deviceInfo!.storageTotalMB!.toStringAsFixed(1)} MB',
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      LinearProgressIndicator(
                        value: _deviceInfo!.storageUsedPercent! / 100,
                        backgroundColor: Colors.grey[300],
                        valueColor: AlwaysStoppedAnimation<Color>(
                          _deviceInfo!.storageUsedPercent! > 80 ? Colors.red : Colors.blue,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),

          // Error/Success messages
          if (_errorMessage != null)
            Container(
              margin: const EdgeInsets.symmetric(horizontal: 16),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.red.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Icon(Icons.error_outline, color: Colors.red),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(_errorMessage!, style: const TextStyle(color: Colors.red)),
                  ),
                ],
              ),
            ),

          const SizedBox(height: 8),

          // Recordings header
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Recordings (${_recordings.length})',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                if (!_isLoading)
                  IconButton(
                    icon: const Icon(Icons.refresh),
                    onPressed: _loadRecordings,
                    tooltip: 'Refresh',
                  ),
              ],
            ),
          ),

          // Recordings list
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _recordings.isEmpty
                    ? const Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.mic_off, size: 64, color: Colors.grey),
                            SizedBox(height: 16),
                            Text('No recordings found'),
                          ],
                        ),
                      )
                    : ListView.builder(
                        itemCount: _recordings.length,
                        itemBuilder: (context, index) {
                          final recording = _recordings[index];
                          final isSelected = _selectedRecordings.contains(recording.recordingId);

                          return CheckboxListTile(
                            value: isSelected,
                            onChanged: (selected) {
                              setState(() {
                                if (selected == true) {
                                  _selectedRecordings.add(recording.recordingId);
                                } else {
                                  _selectedRecordings.remove(recording.recordingId);
                                }
                              });
                            },
                            title: Text(recording.displayName),
                            subtitle: Text(
                              'Duration: ${recording.durationDisplay} • ${recording.directory}',
                            ),
                            secondary: const Icon(Icons.audiotrack, color: Colors.blue),
                          );
                        },
                      ),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _isLoading || _isSyncing
                      ? null
                      : () {
                          if (_selectedRecordings.isNotEmpty) {
                            setState(() {
                              _selectedRecordings.clear();
                            });
                          } else if (_recordings.isNotEmpty) {
                            setState(() {
                              _selectedRecordings.addAll(_recordings.map((r) => r.recordingId));
                            });
                          }
                        },
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: const BorderSide(color: Colors.white54),
                  ),
                  icon: Icon(_selectedRecordings.isEmpty ? Icons.check_box_outline_blank : Icons.check_box),
                  label: Text(_selectedRecordings.isEmpty ? 'Select All' : 'Deselect All'),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                flex: 2,
                child: ElevatedButton.icon(
                  onPressed: _isLoading || _isSyncing || _recordings.isEmpty
                      ? null
                      : _downloadRecordings,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blue,
                    foregroundColor: Colors.white,
                  ),
                  icon: _isSyncing
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Icon(Icons.download),
                  label: Text(
                    _selectedRecordings.isEmpty
                        ? 'Download All (${_recordings.length})'
                        : 'Download Selected (${_selectedRecordings.length})',
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
