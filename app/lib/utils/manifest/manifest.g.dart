// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'manifest.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

Manifest _$ManifestFromJson(Map<String, dynamic> json) => Manifest(
      formatVersion: json['format-version'] as int,
      time: json['time'] as int,
      files: (json['files'] as List<dynamic>)
          .map((e) => ManifestFile.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$ManifestToJson(Manifest instance) => <String, dynamic>{
      'format-version': instance.formatVersion,
      'time': instance.time,
      'files': instance.files,
    };

ManifestFile _$ManifestFileFromJson(Map<String, dynamic> json) => ManifestFile(
      type: json['type'] as String?,
      board: json['board'] as String?,
      soc: json['soc'] as String?,
      loadAddress: json['load_address'] as int?,
      versionMcuboot: json['version_MCUBOOT'] as String?,
      serialRecoveryIndex: json['serial_recovery_index'] as String?,
      size: json['size'] as int?,
      modtime: json['modtime'] as int?,
      version: json['version'] as String?,
      file: json['file'] as String,
      imageIndex: json['image_index'] as String?,
    );

Map<String, dynamic> _$ManifestFileToJson(ManifestFile instance) =>
    <String, dynamic>{
      'type': instance.type,
      'board': instance.board,
      'soc': instance.soc,
      'load_address': instance.loadAddress,
      'version_MCUBOOT': instance.versionMcuboot,
      'serial_recovery_index': instance.serialRecoveryIndex,
      'size': instance.size,
      'modtime': instance.modtime,
      'version': instance.version,
      'file': instance.file,
      'image_index': instance.imageIndex,
    };
