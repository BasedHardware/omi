/// Generative UI components for rendering LLM-generated content
library generative_ui;

// Models
export 'models/rich_list_item_data.dart';
export 'models/pie_chart_data.dart';
export 'models/accordion_data.dart';
export 'models/timeline_data.dart';
export 'models/quote_board_data.dart';
export 'models/followups_data.dart';
export 'models/story_briefing_data.dart';
export 'models/study_data.dart';
export 'models/task_data.dart';
export 'models/flow_data.dart';

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
export 'widgets/timeline_widget.dart';
export 'widgets/quote_board_widget.dart';
export 'widgets/followups_widget.dart';
export 'widgets/story_briefing_card.dart';
export 'widgets/story_briefing_screen.dart';
export 'widgets/study_card.dart';
export 'widgets/study_screen.dart';
export 'widgets/task_card.dart';
export 'widgets/task_screen.dart';
export 'widgets/task_create_sheet.dart';
export 'widgets/flow_card.dart';
export 'widgets/in_app_browser.dart';

// Services
export 'services/task_integration_service.dart';

// Main renderer
export 'generative_markdown_widget.dart';
