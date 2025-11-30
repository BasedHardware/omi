# Generative UI Components

A modular system for rendering LLM-generated custom XML tags as rich UI components within markdown content.

## Overview

This module allows AI/LLM responses to include special XML tags that get rendered as interactive UI components (lists with images, charts, etc.) while preserving regular markdown rendering for the rest of the content.

## Supported Tags

### Rich List (`<rich-list>`)

Renders a horizontal scrollable list of cards with thumbnails.

```xml
<rich-list>
  <item
    title="Product Name"
    description="Brief description"
    thumb="https://example.com/image.jpg"
    url="https://example.com/product"
  />
  <item title="Another Item" description="More details" thumb="https://..." url="https://..."/>
</rich-list>
```

**Attributes:**
| Attribute | Required | Description |
|-----------|----------|-------------|
| `title` | Yes | Main title text |
| `description` | No | Secondary description text |
| `thumb` | No | Thumbnail image URL |
| `url` | No | Link URL (opens in-app browser when tapped) |

### Chart (`<pie-chart>`)

Renders data visualization with multiple chart type options.

#### Available Chart Types

| Type | Attribute | Description |
|------|-----------|-------------|
| **Bar Chart** | `type="bar"` (default) | Vertical bar chart for comparing values |
| **Pie Chart** | `type="pie"` | Solid pie chart for proportions |
| **Donut Chart** | `type="donut"` | Pie chart with center hole |

#### Bar Chart (Default)

```xml
<pie-chart title="Category Distribution">
  <segment label="Work" value="45" color="#8B5CF6"/>
  <segment label="Health" value="30" color="#10B981"/>
  <segment label="Learning" value="25" color="#F59E0B"/>
</pie-chart>
```

Best for: Comparing absolute values, rankings, numeric comparisons.

#### Pie Chart

```xml
<pie-chart title="Time Distribution" type="pie">
  <segment label="Work" value="45" color="#8B5CF6"/>
  <segment label="Health" value="30" color="#10B981"/>
  <segment label="Learning" value="25" color="#F59E0B"/>
</pie-chart>
```

Best for: Showing parts of a whole, percentage breakdowns.

#### Donut Chart

```xml
<pie-chart title="Budget Allocation" type="donut">
  <segment label="Engineering" value="45" color="#8B5CF6"/>
  <segment label="Marketing" value="30" color="#10B981"/>
  <segment label="Operations" value="25" color="#F59E0B"/>
</pie-chart>
```

Best for: Same as pie chart, with a cleaner modern look.

**Chart Attributes:**
| Attribute | Required | Description |
|-----------|----------|-------------|
| `title` | No | Chart title displayed above the chart |
| `type` | No | `"bar"` (default), `"pie"`, or `"donut"` |

**Segment Attributes:**
| Attribute | Required | Description |
|-----------|----------|-------------|
| `label` | Yes | Category label |
| `value` | Yes | Numeric value |
| `color` | No | Hex color (e.g., `#8B5CF6`). Uses default palette if omitted |

**Default Color Palette:**
- Purple: `#8B5CF6`
- Green: `#10B981`
- Orange: `#F59E0B`
- Blue: `#3B82F6`
- Red: `#EF4444`
- Light Purple: `#A78BFA`
- Cyan: `#06B6D4`
- Dark Orange: `#F97316`

**Features:**
- Interactive touch with tooltips/highlights
- Smooth animations
- Auto-scaling for bar charts
- Legend for pie/donut charts
- Percentage display on touch

#### Future Chart Types

The following chart types can be added using the `fl_chart` library:

| Chart Type | Tag Example | Best For |
|------------|-------------|----------|
| **Line Chart** | `<line-chart>` | Trends over time, progress tracking, mood/activity history |
| **Radar Chart** | `<radar-chart>` | Multi-attribute comparison, skills assessment, balanced metrics |
| **Horizontal Bar** | `type="hbar"` | Rankings, leaderboards, top-N lists |
| **Progress/Gauge** | `<progress>` | Single metric visualization, goal completion, scores |

To add a new chart type, see [Adding a New Tag Type](#adding-a-new-tag-type).

### Accordion (`<accordion>`)

Renders expandable/collapsible sections for organized content.

```xml
<accordion title="Frequently Asked Questions" allow-multiple="true">
  <section title="What is this?">
    This is an expandable section with **markdown** support.

    - Lists work
    - Links work
    - All markdown features
  </section>
  <section title="How does it work?">
    Tap the header to expand or collapse each section.
  </section>
</accordion>
```

**Accordion Attributes:**
| Attribute | Required | Description |
|-----------|----------|-------------|
| `title` | No | Optional title displayed above the accordion |
| `allow-multiple` | No | `"true"` allows multiple sections open at once (default: one at a time) |

**Section Attributes:**
| Attribute | Required | Description |
|-----------|----------|-------------|
| `title` | Yes | Section header text (clickable to expand/collapse) |

**Features:**
- Smooth expand/collapse animations
- Markdown support in section content
- Single or multiple expansion modes
- Visual indicators for expanded state

## Usage

### Basic Usage

```dart
import 'package:omi/widgets/generative_ui/generative_ui.dart';

// In your widget:
GenerativeMarkdownWidget(
  content: '''
Here is some markdown content.

<rich-list>
  <item title="Example" description="Description" thumb="https://..." url="https://..."/>
</rich-list>

More markdown after the list.
  ''',
)
```

### With Custom URL Handler

```dart
GenerativeMarkdownWidget(
  content: content,
  onUrlTap: (url) {
    // Custom handling
    print('Tapped: $url');
  },
)
```

### Check for Generative Tags

```dart
if (XmlTagParser.containsGenerativeTags(content)) {
  // Content has custom tags, use GenerativeMarkdownWidget
} else {
  // Regular markdown content
}
```

## Architecture

```
lib/widgets/generative_ui/
├── parsers/                        # Modular tag parsers
│   ├── base_tag_parser.dart        # Abstract base class
│   ├── rich_list_parser.dart       # <rich-list> parser
│   ├── chart_parser.dart           # <pie-chart> parser
│   ├── accordion_parser.dart       # <accordion> parser
│   └── parsers.dart                # Barrel export
├── models/                         # Data models
│   ├── rich_list_item_data.dart
│   ├── pie_chart_data.dart
│   └── accordion_data.dart
├── widgets/                        # UI components
│   ├── rich_list_widget.dart       # Horizontal card list
│   ├── bar_chart_widget.dart       # Bar chart (default)
│   ├── pie_chart_widget.dart       # Pie/donut chart
│   ├── accordion_widget.dart       # Expandable sections
│   └── in_app_browser.dart         # Modal browser for URLs
├── xml_parser.dart                 # Main parser orchestrator
├── markdown_style.dart             # Shared markdown styles
├── generative_markdown_widget.dart # Main rendering widget
└── generative_ui.dart              # Barrel export
```

### How It Works

1. **Content Parsing**: `XmlTagParser` scans content for registered XML tags
2. **Segmentation**: Content is split into `ContentSegment` objects:
   - `MarkdownSegment` - Regular markdown text
   - `RichListSegment` - Parsed rich list data
   - `PieChartSegment` - Parsed chart data
   - `AccordionSegment` - Parsed accordion data
3. **Rendering**: `GenerativeMarkdownWidget` renders each segment with the appropriate widget
4. **Markdown Preprocessing**: Fixes common markdown issues (setext headings, spacing)

## Adding a New Tag Type

### Step 1: Create the Parser

Create a new file in `parsers/`:

```dart
// parsers/timeline_parser.dart
import '../xml_parser.dart';
import 'base_tag_parser.dart';

class TimelineParser extends BaseTagParser {
  static final _pattern = RegExp(
    r'<timeline>([\s\S]*?)</timeline>',
    caseSensitive: false,
  );

  @override
  RegExp get pattern => _pattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final innerContent = match.group(1) ?? '';
    // Parse inner content...
    return TimelineSegment(events);
  }
}
```

### Step 2: Create the Segment Class

Add to `xml_parser.dart`:

```dart
class TimelineSegment extends ContentSegment {
  final List<TimelineEvent> events;
  const TimelineSegment(this.events);
}
```

### Step 3: Register the Parser

In `xml_parser.dart`, add to `_parsers`:

```dart
final List<BaseTagParser> _parsers = [
  RichListParser(),
  ChartParser(),
  TimelineParser(),  // Add here
];
```

Also update `containsGenerativeTags()`:

```dart
static bool containsGenerativeTags(String content) {
  return RichListParser().containsTag(content) ||
      ChartParser().containsTag(content) ||
      TimelineParser().containsTag(content);  // Add here
}
```

### Step 4: Create the Widget

Create the UI widget in `widgets/`:

```dart
// widgets/timeline_widget.dart
class TimelineWidget extends StatelessWidget {
  final List<TimelineEvent> events;
  // ...
}
```

### Step 5: Handle in Renderer

Update `GenerativeMarkdownWidget._buildSegment()`:

```dart
Widget _buildSegment(BuildContext context, ContentSegment segment) {
  if (segment is MarkdownSegment) {
    return _buildMarkdownSegment(context, segment.content);
  } else if (segment is RichListSegment) {
    return RichListWidget(items: segment.items, ...);
  } else if (segment is PieChartSegment) {
    return GenerativeBarChartWidget(data: segment.data);
  } else if (segment is TimelineSegment) {
    return TimelineWidget(events: segment.events);  // Add here
  }
  return const SizedBox.shrink();
}
```

### Step 6: Export

Add exports to `parsers/parsers.dart` and `generative_ui.dart`.

## Markdown Preprocessing

The module automatically fixes common markdown formatting issues:

1. **Setext Heading Prevention**: Adds blank lines before `---` to prevent text from becoming headings
2. **Heading Spacing**: Ensures blank lines after `#` headings
3. **Horizontal Rule Spacing**: Proper spacing around `---` dividers

## Styling

All markdown content uses `MarkdownStyleHelper.getStyleSheet()` for consistent styling:

- White text on dark background
- 16px base font size
- 1.5 line height
- Explicit styles prevent theme inheritance issues

## Dependencies

- `flutter_markdown` - Markdown rendering
- `fl_chart` - Chart visualization
- `cached_network_image` - Image caching
- `webview_flutter` - In-app browser
- `share_plus` - URL sharing

## LLM System Prompt Reference

To enable AI/LLM to generate rich UI components, add the following instructions to your system prompt:

### Basic System Prompt Addition

```
You can enhance your responses with rich UI components using special XML tags embedded in your markdown responses.

### Available Components:

1. **Rich List** - Display items as horizontal scrollable cards:
<rich-list>
  <item title="Title" description="Description" thumb="IMAGE_URL" url="LINK_URL"/>
</rich-list>

2. **Chart** - Display data visualization (bar, pie, or donut):
<pie-chart title="Chart Title" type="bar|pie|donut">
  <segment label="Category" value="NUMBER" color="#HEX_COLOR"/>
</pie-chart>

Chart types:
- type="bar" (default): Vertical bar chart for comparing values
- type="pie": Solid pie chart for proportions
- type="donut": Pie chart with center hole

3. **Accordion** - Display expandable/collapsible sections:
<accordion title="Section Title" allow-multiple="true">
  <section title="First Section">Content with **markdown** support.</section>
  <section title="Second Section">More content here.</section>
</accordion>

### Guidelines:
- Use rich lists for recommendations, resources, products, or any list of items with images
- Use charts to visualize distributions, breakdowns, or comparisons
- Use accordions for FAQs, detailed breakdowns, or content that benefits from expand/collapse
- These tags can be placed anywhere in your markdown response
- Always ensure proper spacing around tags (blank lines before and after)
- For thumbnails, use relevant image URLs or placeholder services like picsum.photos
```

### Complete System Prompt Example

```
You are a helpful assistant that provides rich, interactive responses.

When appropriate, enhance your responses with visual components:

1. Use <rich-list> for:
   - Product recommendations
   - Resource links
   - Related articles
   - Action items with links
   - Any list that benefits from visual thumbnails

2. Use <pie-chart> for data visualization:
   - type="bar" (default): Rankings, comparisons, absolute values
   - type="pie": Parts of a whole, percentage breakdowns
   - type="donut": Same as pie, modern style

   Use cases:
   - Topic distributions
   - Time breakdowns
   - Category comparisons
   - Budget allocations

3. Use <accordion> for:
   - FAQs and Q&A sections
   - Detailed breakdowns with many items
   - Step-by-step instructions
   - Content that users may want to explore selectively
   - Organizing long-form content into digestible sections

Example response format:

## Summary
Your markdown content here...

**Recommended Resources:**

<rich-list>
<item title="Resource Name" description="Brief description" thumb="https://picsum.photos/200" url="https://example.com"/>
</rich-list>

**Distribution Analysis:**

<pie-chart title="Category Breakdown">
<segment label="Category A" value="40" color="#8B5CF6"/>
<segment label="Category B" value="35" color="#10B981"/>
<segment label="Category C" value="25" color="#F59E0B"/>
</pie-chart>

More markdown content...
```

### Tips for LLM Integration

1. **Contextual Usage**: Instruct the LLM to use components only when they add value
2. **Fallback Content**: Components should enhance, not replace, text content
3. **Image Sources**: Provide guidance on acceptable image URL sources
4. **Data Accuracy**: For charts, ensure values are meaningful and add up logically
5. **Spacing**: Remind LLM to add blank lines around XML tags for proper markdown parsing

## Example: Full LLM Response

```markdown
## Meeting Summary

The team discussed Q4 planning and resource allocation.

**Quick Links:**

<rich-list>
  <item title="Meeting Recording" description="Watch the full discussion" thumb="https://picsum.photos/200" url="https://example.com/recording"/>
  <item title="Shared Notes" description="Collaborative document" thumb="https://picsum.photos/200" url="https://example.com/notes"/>
</rich-list>

### Key Recommendations

The following action items were identified...

**Recommended Resources:**

<rich-list>
  <item title="Increase Engineering" description="Add 2 senior developers" thumb="https://picsum.photos/200" url="https://example.com/hiring"/>
  <item title="Marketing Push" description="Launch campaign in November" thumb="https://picsum.photos/200" url="https://example.com/campaign"/>
</rich-list>

### Budget Breakdown

<pie-chart title="Q4 Budget Allocation" type="donut">
  <segment label="Engineering" value="45" color="#8B5CF6"/>
  <segment label="Marketing" value="30" color="#10B981"/>
  <segment label="Operations" value="25" color="#F59E0B"/>
</pie-chart>

### Time Distribution

<pie-chart title="Weekly Focus Areas" type="pie">
  <segment label="Development" value="40"/>
  <segment label="Meetings" value="25"/>
  <segment label="Planning" value="20"/>
  <segment label="Admin" value="15"/>
</pie-chart>

### Frequently Asked Questions

<accordion title="Meeting FAQ">
  <section title="When is the next meeting?">
    The team will reconvene **next Tuesday at 2pm** to finalize decisions.

    - Review action items
    - Present updated proposals
    - Vote on final budget
  </section>
  <section title="Who should attend?">
    All department heads and project leads are required to attend.
  </section>
  <section title="What should I prepare?">
    Please prepare:
    1. Status updates on your action items
    2. Any blockers or concerns
    3. Preliminary budget requests
  </section>
</accordion>

The team will reconvene next week to finalize decisions.
```

## License

This module is part of the OMI open source project.
