import '../models/task_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for standalone `<task>` tags with steps, summary, and transcript references.
class TaskParser extends BaseTagParser {
  static final _taskPattern = RegExp(r'<task\s+([^>]*)>([\s\S]*?)</task>', caseSensitive: false);

  static final _stepPattern = RegExp(r'<step\s+([^>]*)>([\s\S]*?)</step>', caseSensitive: false);

  static final _stepSelfClosingPattern = RegExp(r'<step\s+([^/]*)/\s*>', caseSensitive: false);

  static final _refPattern = RegExp(r'<ref\s+([^>]*)>([\s\S]*?)</ref>', caseSensitive: false);

  static final _summaryPattern = RegExp(r'<summary>([\s\S]*?)</summary>', caseSensitive: false);

  @override
  RegExp get pattern => _taskPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final taskAttrString = match.group(1) ?? '';
    final taskContent = match.group(2) ?? '';
    final task = _parseTask(taskAttrString, taskContent);
    if (task == null) return null;
    return TaskSegment(task);
  }

  TaskData? _parseTask(String taskAttrString, String taskContent) {
    final attributes = parseAttributes(taskAttrString);
    final title = attributes['title'];

    if (title == null || title.isEmpty) return null;

    String? summary;
    final summaryMatch = _summaryPattern.firstMatch(taskContent);
    if (summaryMatch != null) {
      summary = summaryMatch.group(1)?.trim();
    }

    final taskRefs = <TranscriptReference>[];
    for (final refMatch in _refPattern.allMatches(taskContent)) {
      final refStart = refMatch.start;
      bool isInsideStep = false;
      for (final stepMatch in _stepPattern.allMatches(taskContent)) {
        if (refStart > stepMatch.start && refStart < stepMatch.end) {
          isInsideStep = true;
          break;
        }
      }
      if (!isInsideStep) {
        final refAttrString = refMatch.group(1) ?? '';
        final refContent = refMatch.group(2) ?? '';
        final refAttrs = parseAttributes(refAttrString);
        taskRefs.add(TranscriptReference.fromParsed(attributes: refAttrs, innerContent: refContent));
      }
    }

    final steps = <TaskStepData>[];

    for (final stepMatch in _stepPattern.allMatches(taskContent)) {
      final stepAttrString = stepMatch.group(1) ?? '';
      final stepContent = stepMatch.group(2) ?? '';
      final step = _parseStep(stepAttrString, stepContent);
      if (step != null) steps.add(step);
    }

    for (final stepMatch in _stepSelfClosingPattern.allMatches(taskContent)) {
      final stepAttrString = stepMatch.group(1) ?? '';
      final step = _parseStep(stepAttrString, '');
      if (step != null) steps.add(step);
    }

    return TaskData(
      title: title,
      summary: summary,
      priority: TaskPriority.fromString(attributes['priority']),
      status: TaskStatus.fromString(attributes['status']),
      assignee: attributes['assignee'],
      dueDate: attributes['due'] ?? attributes['dueDate'],
      steps: steps,
      transcriptRefs: taskRefs,
    );
  }

  TaskStepData? _parseStep(String stepAttrString, String stepContent) {
    final attributes = parseAttributes(stepAttrString);
    final title = attributes['title'];

    if (title == null || title.isEmpty) return null;

    final stepRefs = <TranscriptReference>[];
    for (final refMatch in _refPattern.allMatches(stepContent)) {
      final refAttrString = refMatch.group(1) ?? '';
      final refContent = refMatch.group(2) ?? '';
      final refAttrs = parseAttributes(refAttrString);
      stepRefs.add(TranscriptReference.fromParsed(attributes: refAttrs, innerContent: refContent));
    }

    return TaskStepData.fromParsed(attributes: attributes, innerContent: stepContent, transcriptRefs: stepRefs);
  }
}
