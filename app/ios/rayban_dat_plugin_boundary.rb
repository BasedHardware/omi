# frozen_string_literal: true

require 'fileutils'
require 'json'
require 'tempfile'
require 'tmpdir'

# Keeps mcumgr_flutter out of the generated iOS plugin graph for Ray-Ban DAT
# builds. The Android plugin graph is deliberately left intact.
module RayBanDatPluginBoundary
  DAT_FLAG = 'OMI_RAYBAN_DAT'
  BACKUP_DIRECTORY = File.join('.dart_tool', 'rayban_dat_plugin_boundary')
  METADATA_RELATIVE_PATH = '.flutter-plugins-dependencies'
  REGISTRANT_RELATIVE_PATH = File.join('ios', 'Runner', 'GeneratedPluginRegistrant.m')
  METADATA_BACKUP_NAME = 'flutter-plugins-dependencies.original'
  REGISTRANT_BACKUP_NAME = 'GeneratedPluginRegistrant.m.original'

  MCUMGR_IMPORT_BLOCK = <<~OBJC.freeze
    #if __has_include(<mcumgr_flutter/McumgrFlutterPlugin.h>)
    #import <mcumgr_flutter/McumgrFlutterPlugin.h>
    #else
    @import mcumgr_flutter;
    #endif

  OBJC

  MCUMGR_REGISTRATION =
    '  [McumgrFlutterPlugin registerWithRegistrar:[registry registrarForPlugin:@"McumgrFlutterPlugin"]];'

  class BoundaryError < StandardError; end

  module_function

  def prepare!(app_root:, env: ENV)
    return :inactive unless env[DAT_FLAG] == '1'

    paths = paths_for(app_root)
    originals, transformed = load_or_create_snapshot(paths)
    current = read_generated_files(paths)
    validate_known_files!(paths, current, originals, transformed)
    write_pair(paths, prepare_pair(current, originals))
    :prepared
  end

  def restore!(app_root:)
    paths = paths_for(app_root)
    return :not_prepared unless Dir.exist?(paths.fetch(:backup_directory))

    originals = read_snapshot(paths)
    transformed = transform_pair(originals)
    current = read_generated_files(paths)
    validate_known_files!(paths, current, originals, transformed)
    write_pair(paths, originals)
    remove_snapshot(paths)
    :restored
  end

  def load_or_create_snapshot(paths)
    if Dir.exist?(paths.fetch(:backup_directory))
      originals = read_snapshot(paths)
      return [originals, transform_pair(originals)]
    end

    originals = read_generated_files(paths)
    transformed = transform_pair(originals)
    create_snapshot(paths, originals)
    [originals, transformed]
  end
  private_class_method :load_or_create_snapshot

  def transform_pair(originals)
    {
      metadata: transform_metadata(originals.fetch(:metadata)),
      registrant: transform_registrant(originals.fetch(:registrant)),
    }
  end
  private_class_method :transform_pair

  def prepare_pair(current, originals)
    {
      metadata: if generated_file_matches?(:metadata, current.fetch(:metadata), originals.fetch(:metadata))
                  transform_metadata(current.fetch(:metadata))
                else
                  current.fetch(:metadata)
                end,
      registrant: if current.fetch(:registrant) == originals.fetch(:registrant)
                    transform_registrant(current.fetch(:registrant))
                  else
                    current.fetch(:registrant)
                  end,
    }
  end
  private_class_method :prepare_pair

  def transform_metadata(content)
    metadata = JSON.parse(content)
    plugins = metadata.fetch('plugins')
    ios_plugins = plugins.fetch('ios')
    unless ios_plugins.is_a?(Array)
      raise BoundaryError, 'expected plugins.ios to be an array in .flutter-plugins-dependencies'
    end

    matching_indexes = ios_plugins.each_index.select do |index|
      plugin = ios_plugins.fetch(index)
      plugin.is_a?(Hash) && plugin['name'] == 'mcumgr_flutter'
    end
    unless matching_indexes.length == 1
      raise BoundaryError,
            "expected exactly one mcumgr_flutter iOS plugin entry, found #{matching_indexes.length}"
    end

    plugins['ios'] = ios_plugins.each_with_index.reject { |_plugin, index| index == matching_indexes.first }.map(&:first)
    trailing_newline = content.end_with?("\r\n") ? "\r\n" : (content.end_with?("\n") ? "\n" : '')
    JSON.generate(metadata) + trailing_newline
  rescue JSON::ParserError, KeyError => error
    raise BoundaryError, "invalid .flutter-plugins-dependencies shape: #{error.message}"
  end
  private_class_method :transform_metadata

  def transform_registrant(content)
    import_count = content.scan(MCUMGR_IMPORT_BLOCK).length
    unless import_count == 1
      raise BoundaryError, "expected exactly one mcumgr_flutter import block, found #{import_count}"
    end

    registration_count = content.scan(MCUMGR_REGISTRATION).length
    unless registration_count == 1
      raise BoundaryError,
            "expected exactly one mcumgr_flutter registration call, found #{registration_count}"
    end

    transformed = content.sub(MCUMGR_IMPORT_BLOCK, '').sub(MCUMGR_REGISTRATION, '')
    if transformed.include?('mcumgr_flutter') || transformed.include?('McumgrFlutterPlugin')
      raise BoundaryError, 'unexpected mcumgr_flutter reference remains in GeneratedPluginRegistrant.m'
    end

    transformed
  end
  private_class_method :transform_registrant

  def paths_for(app_root)
    root = File.expand_path(app_root)
    backup_directory = File.join(root, BACKUP_DIRECTORY)
    {
      metadata: File.join(root, METADATA_RELATIVE_PATH),
      registrant: File.join(root, REGISTRANT_RELATIVE_PATH),
      backup_directory: backup_directory,
      metadata_backup: File.join(backup_directory, METADATA_BACKUP_NAME),
      registrant_backup: File.join(backup_directory, REGISTRANT_BACKUP_NAME),
    }
  end
  private_class_method :paths_for

  def read_generated_files(paths)
    {
      metadata: read_required(paths.fetch(:metadata)),
      registrant: read_required(paths.fetch(:registrant)),
    }
  end
  private_class_method :read_generated_files

  def read_snapshot(paths)
    expected_entries = [METADATA_BACKUP_NAME, REGISTRANT_BACKUP_NAME].sort
    actual_entries = Dir.children(paths.fetch(:backup_directory)).sort
    unless actual_entries == expected_entries
      raise BoundaryError,
            "invalid Ray-Ban DAT backup contents: expected #{expected_entries.join(', ')}, " \
            "found #{actual_entries.join(', ')}"
    end

    {
      metadata: read_required(paths.fetch(:metadata_backup)),
      registrant: read_required(paths.fetch(:registrant_backup)),
    }
  end
  private_class_method :read_snapshot

  def read_required(path)
    File.binread(path)
  rescue Errno::ENOENT
    raise BoundaryError, "required generated file is missing: #{path}"
  end
  private_class_method :read_required

  def create_snapshot(paths, originals)
    backup_directory = paths.fetch(:backup_directory)
    parent_directory = File.dirname(backup_directory)
    FileUtils.mkdir_p(parent_directory)
    staging_directory = Dir.mktmpdir('.rayban-dat-plugin-boundary-', parent_directory)

    begin
      File.binwrite(File.join(staging_directory, METADATA_BACKUP_NAME), originals.fetch(:metadata))
      File.binwrite(File.join(staging_directory, REGISTRANT_BACKUP_NAME), originals.fetch(:registrant))
      File.rename(staging_directory, backup_directory)
      staging_directory = nil
    ensure
      FileUtils.remove_entry(staging_directory) if staging_directory && Dir.exist?(staging_directory)
    end
  rescue Errno::EEXIST
    raise BoundaryError, "Ray-Ban DAT backup already appeared concurrently: #{backup_directory}"
  end
  private_class_method :create_snapshot

  def validate_known_files!(paths, current, originals, transformed)
    %i[metadata registrant].each do |key|
      next if generated_file_matches?(key, current.fetch(key), originals.fetch(key))
      next if generated_file_matches?(key, current.fetch(key), transformed.fetch(key))

      raise BoundaryError, "refusing to overwrite changed generated file: #{paths.fetch(key)}"
    end
  end
  private_class_method :validate_known_files!

  def generated_file_matches?(key, current, expected)
    return true if current == expected
    return false unless key == :metadata

    metadata_matches_except_creation_date?(current, expected)
  end
  private_class_method :generated_file_matches?

  def metadata_matches_except_creation_date?(current, expected)
    current_document = JSON.parse(current)
    expected_document = JSON.parse(expected)
    current_date = current_document.delete('date_created')
    expected_date = expected_document.delete('date_created')

    current_date.is_a?(String) && expected_date.is_a?(String) && current_document == expected_document
  rescue JSON::ParserError
    false
  end
  private_class_method :metadata_matches_except_creation_date?

  def write_pair(paths, content)
    %i[metadata registrant].each do |key|
      path = paths.fetch(key)
      next if File.binread(path) == content.fetch(key)

      atomic_write(path, content.fetch(key))
    end
  end
  private_class_method :write_pair

  def atomic_write(path, content)
    original_mode = File.stat(path).mode
    Tempfile.create(['.rayban-dat-plugin-boundary-', '.tmp'], File.dirname(path)) do |file|
      file.binmode
      file.write(content)
      file.flush
      file.fsync
      File.chmod(original_mode, file.path)
      File.rename(file.path, path)
    end
  end
  private_class_method :atomic_write

  def remove_snapshot(paths)
    FileUtils.remove_entry(paths.fetch(:backup_directory))
  end
  private_class_method :remove_snapshot
end

if $PROGRAM_NAME == __FILE__
  command = ARGV.shift
  app_root = ARGV.shift || File.expand_path('..', __dir__)

  if ARGV.any? || !%w[prepare restore].include?(command)
    warn 'Usage: ruby ios/rayban_dat_plugin_boundary.rb prepare|restore [app-root]'
    exit 2
  end

  begin
    result = if command == 'prepare'
               RayBanDatPluginBoundary.prepare!(app_root: app_root, env: ENV)
             else
               RayBanDatPluginBoundary.restore!(app_root: app_root)
             end
    puts "Ray-Ban DAT plugin boundary: #{result}"
  rescue RayBanDatPluginBoundary::BoundaryError => error
    warn "Ray-Ban DAT plugin boundary: #{error.message}"
    exit 1
  end
end
