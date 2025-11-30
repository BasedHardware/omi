/// Generative UI components for rendering LLM-generated content
library generative_ui;

// Models
export 'models/rich_list_item_data.dart';
export 'models/pie_chart_data.dart';
export 'models/accordion_data.dart';

// Parsers (modular tag parsers for easy extension)
export 'parsers/parsers.dart';
export 'xml_parser.dart';

// Styles
export 'markdown_style.dart';

// Widgets
export 'widgets/rich_list_widget.dart';
export 'widgets/pie_chart_widget.dart';
export 'widgets/bar_chart_widget.dart';
export 'widgets/accordion_widget.dart';
export 'widgets/in_app_browser.dart';

// Main renderer
export 'generative_markdown_widget.dart';
