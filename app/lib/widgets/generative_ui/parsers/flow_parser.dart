import '../models/flow_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <flow> tags with steps for visualizing user flows/use cases.
///
/// Example:
/// ```xml
/// <flow title="UC-03 – Ordering groceries">
///   <step type="main">User asks to order groceries.</step>
///   <step type="main">System connects to services.</step>
///   <step type="exception">If unsupported, inform user.</step>
/// </flow>
/// ```
class FlowParser extends BaseTagParser {
  static final _flowPattern = RegExp(
    r'<flow\s+([^>]*)>([\s\S]*?)</flow>',
    caseSensitive: false,
  );

  static final _stepPattern = RegExp(
    r'<step(?:\s+([^>]*))?>([^<]*)</step>',
    caseSensitive: false,
  );

  @override
  RegExp get pattern => _flowPattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final flowAttrString = match.group(1) ?? '';
    final flowContent = match.group(2) ?? '';
    final flow = _parseFlow(flowAttrString, flowContent);
    if (flow == null) return null;
    return FlowSegment(flow);
  }

  FlowData? _parseFlow(String flowAttrString, String flowContent) {
    final attributes = parseAttributes(flowAttrString);
    final title = attributes['title'];

    if (title == null || title.isEmpty) return null;

    final steps = <FlowStepData>[];

    for (final stepMatch in _stepPattern.allMatches(flowContent)) {
      final stepAttrString = stepMatch.group(1) ?? '';
      final stepContent = stepMatch.group(2) ?? '';
      final stepAttrs = parseAttributes(stepAttrString);

      if (stepContent.trim().isNotEmpty) {
        steps.add(FlowStepData.fromParsed(
          attributes: stepAttrs,
          innerContent: stepContent,
        ));
      }
    }

    return FlowData(
      title: title,
      steps: steps,
    );
  }
}
