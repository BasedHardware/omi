/// WAL (Write-Ahead Log) Service for managing audio recordings
///
/// This barrel file exports all WAL-related types and services.
/// The implementation is split across multiple files for maintainability:
/// - wal.dart: Core Wal class, WalStats, enums, constants
/// - wal_interfaces.dart: Abstract interfaces for sync services
/// - local_wal_sync.dart: Phone storage sync implementation
/// - sdcard_wal_sync.dart: SD card sync implementation
/// - flash_page_wal_sync.dart: Limitless flash page sync implementation
/// - wal_syncs.dart: Orchestrator for all sync types
/// - wal_service.dart: Main service class

library wals;

// Core types
export 'wals/wal.dart';
export 'wals/wal_interfaces.dart';

// Sync implementations
export 'wals/local_wal_sync.dart';
export 'wals/sdcard_wal_sync.dart';
export 'wals/flash_page_wal_sync.dart';
export 'wals/wal_syncs.dart';
export 'wals/wal_service.dart';
