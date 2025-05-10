import 'package:json_annotation/json_annotation.dart';

part 'manifest.g.dart';

@JsonSerializable(fieldRename: FieldRename.snake)
class Manifest {
  @JsonKey(name: 'format-version')
  int formatVersion;
  int time;
  List<ManifestFile> files;

  factory Manifest.fromJson(Map<String, dynamic> json) {
    final manifest = _$ManifestFromJson(json);

    if (manifest.files.length > 1) {
      for (final file in manifest.files) {
        if (file.imageIndex == null) {
          throw Exception('imageIndex is required for multi-image firmware');
        }
      }
    }

    return manifest;
  }

  Manifest({
    required this.formatVersion,
    required this.time,
    required this.files,
  });
}

@JsonSerializable(fieldRename: FieldRename.snake)
class ManifestFile {
  String? type;
  String? board;
  String? soc;
  int? loadAddress;
  @JsonKey(name: 'version_MCUBOOT')
  String? versionMcuboot;
  String? serialRecoveryIndex;
  int? size;
  int? modtime;
  String? version;

  // Required properties
  String file;
  String? imageIndex;

  int get image => int.parse(imageIndex ?? "0");

  factory ManifestFile.fromJson(Map<String, dynamic> json) =>
      _$ManifestFileFromJson(json);

  ManifestFile({
    this.type,
    this.board,
    this.soc,
    this.loadAddress,
    this.versionMcuboot,
    this.serialRecoveryIndex,
    this.size,
    this.modtime,
    this.version,
    required this.file,
    required this.imageIndex,
  });
}
