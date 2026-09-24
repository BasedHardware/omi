import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  late Directory tempDir;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = Directory.systemTemp.createTempSync('audio_import_test_');
  });

  tearDown(() {
    if (tempDir.existsSync()) {
      tempDir.deleteSync(recursive: true);
    }
  });

  File createTestFile(String name, {int byteCount = 1024}) {
    final file = File('${tempDir.path}/$name');
    if (byteCount > 0) {
      file.writeAsBytesSync(List<int>.filled(byteCount, 42));
    } else {
      file.createSync();
    }
    return file;
  }

  test('rejects unsupported file extensions', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final txtFile = createTestFile('notes.txt');
    final result = await provider.importAudioFile(txtFile);

    expect(result, isNull);
    expect(provider.audioImportError, contains('Unsupported audio format: .txt'));
    expect(provider.isImportingAudio, isFalse);

    final pdfFile = createTestFile('document.pdf');
    final result2 = await provider.importAudioFile(pdfFile);
    expect(result2, isNull);
    expect(provider.audioImportError, contains('Unsupported audio format: .pdf'));
  });

  test('accepts supported extensions case-insensitively', () async {
    var uploadCalled = false;
    final expectedConvo = ServerConversation(
      id: 'audio_conv_1',
      createdAt: DateTime.utc(2026, 9, 23),
      structured: Structured('Audio Summary', 'Overview text'),
    );

    Future<CreateConversationResponse?> mockUploader(
      File file, {
      String? language,
      UploadProgressCallback? onUploadProgress,
    }) async {
      uploadCalled = true;
      return CreateConversationResponse(conversation: expectedConvo, messages: <ServerMessage>[]);
    }

    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
      audioUploader: mockUploader,
    );
    addTearDown(provider.dispose);

    for (final ext in ['.mp3', '.m4a', '.wav', '.aac', '.ogg', '.flac', '.MP3', '.WAV']) {
      uploadCalled = false;
      final file = createTestFile('sample$ext');
      final result = await provider.importAudioFile(file);

      expect(uploadCalled, isTrue, reason: 'Failed for extension $ext');
      expect(result, isNotNull);
      expect(result!.id, equals('audio_conv_1'));
      expect(provider.audioImportError, isNull);
    }
  });

  test('rejects empty (0 byte) files', () async {
    var uploadCalled = false;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
      audioUploader: (file, {language, onUploadProgress}) async {
        uploadCalled = true;
        return null;
      },
    );
    addTearDown(provider.dispose);

    final emptyFile = createTestFile('empty.mp3', byteCount: 0);
    final result = await provider.importAudioFile(emptyFile);

    expect(result, isNull);
    expect(uploadCalled, isFalse);
    expect(provider.audioImportError, equals('File is empty'));
    expect(provider.isImportingAudio, isFalse);
  });

  test('rejects file with no extension', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final noExtFile = createTestFile('no_extension_file');
    final result = await provider.importAudioFile(noExtFile);

    expect(result, isNull);
    expect(provider.audioImportError, equals('File has no extension'));
    expect(provider.isImportingAudio, isFalse);
  });

  test('rejects file exceeding 200MB limit', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final oversizedFile = _FakeOversizedFile('${tempDir.path}/huge.mp3', 200000001);
    final result = await provider.importAudioFile(oversizedFile);

    expect(result, isNull);
    expect(provider.audioImportError, equals('File exceeds maximum size of 200MB'));
    expect(provider.isImportingAudio, isFalse);
  });

  test('successful audio import upserts conversation and tracks progress', () async {
    final expectedConvo = ServerConversation(
      id: 'conv_imported_42',
      createdAt: DateTime.utc(2026, 9, 23, 14, 0),
      structured: Structured('Imported Interview', 'A great conversation'),
    );

    final progressUpdates = <double>[];
    Future<CreateConversationResponse?> mockUploader(
      File file, {
      String? language,
      UploadProgressCallback? onUploadProgress,
    }) async {
      onUploadProgress?.call(250, 1000, 50.0);
      onUploadProgress?.call(750, 1000, 50.0);
      onUploadProgress?.call(1000, 1000, 50.0);
      return CreateConversationResponse(conversation: expectedConvo, messages: <ServerMessage>[]);
    }

    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
      audioUploader: mockUploader,
    );
    addTearDown(provider.dispose);

    provider.addListener(() {
      if (provider.isImportingAudio && provider.audioImportProgress > 0) {
        progressUpdates.add(provider.audioImportProgress);
      }
    });

    final audioFile = createTestFile('interview.m4a', byteCount: 2048);
    final result = await provider.importAudioFile(audioFile, language: 'en');

    expect(result, isNotNull);
    expect(result!.id, equals('conv_imported_42'));
    expect(provider.isImportingAudio, isFalse);
    expect(provider.audioImportProgress, equals(1.0));
    expect(provider.audioImportError, isNull);

    // Verify conversation was upserted into provider
    expect(provider.conversations.any((c) => c.id == 'conv_imported_42'), isTrue);
    expect(
      provider.conversations.firstWhere((c) => c.id == 'conv_imported_42').structured.title,
      equals('Imported Interview'),
    );

    // Verify progress callbacks fired
    expect(progressUpdates, containsAllInOrder([0.25, 0.75, 1.0]));
  });

  test('handles uploader exception gracefully', () async {
    Future<CreateConversationResponse?> failingUploader(
      File file, {
      String? language,
      UploadProgressCallback? onUploadProgress,
    }) async {
      throw Exception('Server 502: Speech-to-text transcription failed');
    }

    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
      audioUploader: failingUploader,
    );
    addTearDown(provider.dispose);

    final audioFile = createTestFile('meeting.wav');
    final result = await provider.importAudioFile(audioFile);

    expect(result, isNull);
    expect(provider.isImportingAudio, isFalse);
    expect(provider.audioImportProgress, equals(0.0));
    expect(provider.audioImportError, contains('Speech-to-text transcription failed'));
  });

  test('handles uploader returning null gracefully', () async {
    Future<CreateConversationResponse?> nullUploader(
      File file, {
      String? language,
      UploadProgressCallback? onUploadProgress,
    }) async {
      return null;
    }

    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
      audioUploader: nullUploader,
    );
    addTearDown(provider.dispose);

    final audioFile = createTestFile('meeting.flac');
    final result = await provider.importAudioFile(audioFile);

    expect(result, isNull);
    expect(provider.isImportingAudio, isFalse);
    expect(provider.audioImportError, equals('Failed to process audio conversation'));
  });
}

class _FakeOversizedFile extends Fake implements File {
  @override
  final String path;
  final int bytes;

  _FakeOversizedFile(this.path, this.bytes);

  @override
  Future<int> length() async => bytes;

  @override
  int lengthSync() => bytes;
}
