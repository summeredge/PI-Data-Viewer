# PI Data Viewer - Agent Instructions

## Project Overview

PI Data Viewer is an industrial historical data visualization tool.

Main purpose:

- Read historical data from PI Historian.
- Convert data into pandas DataFrame.
- Display engineering charts through a web interface.

This project focuses on visualization, not data analysis.


## Technology Stack

Primary stack:

- Python
- Dash
- Plotly
- pandas
- numpy
- scipy

Keep the existing architecture unless a change is explicitly requested.


## Scope Boundaries

Allowed:

- PI data reading.
- DataFrame management.
- Interactive charts.
- Basic statistics display.
- Data export.

Do not add:

- Causal analysis.
- Machine learning models.
- PCA modeling.
- Predictive control.
- Automatic diagnosis.

These belong to other projects.


## Development Rules

- Keep changes small and focused.
- Reuse existing modules before creating new ones.
- Do not introduce unnecessary dependencies.
- Do not perform unrelated refactoring.
- Preserve existing interfaces and data formats.


## Data Rules

The common data format is:

- pandas DataFrame.
- Datetime index.
- Columns represent PI Tags.

Chart modules should consume DataFrame objects and should not directly access PI.


## Windows Compatibility

The project runs on Windows.

Avoid:

- Linux-only commands.
- Hard-coded paths.
- Dependencies requiring special system environments.


## Testing Requirements

For code changes:

- Add or update tests when behavior changes.
- Run relevant tests before completion.
- Report modified files and test results.

Focus on:

- Data format stability.
- Module imports.
- Chart generation.
- Application startup.


## Agent Behavior

Before making changes:

1. Read the existing code.
2. Understand the current implementation.
3. Make the smallest change that satisfies the task.

Do not expand the project scope without confirmation.