```python
import pandas as pd
from pandas import DataFrame
from pandas.core.dtypes.common import is_list_like

def create_chart_tool(data, chart_type="bar", labels=None, values=None, config=None):
    """
    Creates a chart tool visualization.
    
    Args:
        data: The data to be visualized.
        chart_type: The type of chart, options include "line" or "bar".
        labels: The labels for the chart.
        values: The values for the chart.
        config: Configuration options for the chart.
    
    Returns:
        A dictionary containing the figure and configuration.
    """
    # Ensure labels are a list
    labels = list(labels) if labels and isinstance(labels, (list, tuple)) else []
    
    # Ensure values are a list
    values = list(values) if values and isinstance(values, (list, tuple)) else []
    
    # Normalize chart_type to lowercase and strip whitespace
    chart_type = chart_type.strip().lower() if chart_type else "bar"
    
    # Convert values to float and handle NaN/Inf
    values = [float(v) if isinstance(v, (int, float)) else 0 for v in values]
    values = [v if abs(v) != float('inf') else 1e300 for v in values]
    
    # Handle configurable assignment
    configurable = config.get('configurable', []) if config else []
    
    # Create DataFrame
    df = DataFrame({labels[0]: values}) if labels else DataFrame(data)
    
    # Create figure
    fig = df.plot(kind=chart_type, title=labels[1] if len(labels) > 1 else None)
    
    return {
        "figure": fig,
        "config": configurable
    }
```

This code addresses all the points mentioned in the task by adding input validation, normalizing the chart type, handling numeric values, and ensuring the configurable parameter is properly set.