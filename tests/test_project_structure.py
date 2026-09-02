from importlib import import_module
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    "app.py",
    "config/config.yaml",
    "backend/__init__.py",
    "backend/pi_reader.py",
    "backend/dataframe_store.py",
    "backend/statistics.py",
    "backend/spc.py",
    "charts/__init__.py",
    "charts/trend.py",
    "charts/scatter.py",
    "charts/histogram.py",
    "charts/boxplot.py",
    "charts/control_chart.py",
    "charts/heatmap.py",
    "layout/__init__.py",
    "layout/sidebar.py",
    "layout/tabs.py",
    "layout/dashboard.py",
    "pages/__init__.py",
    "pages/viewer.py",
    "export/__init__.py",
    "export/csv_export.py",
    "export/html_report.py",
    "requirements.txt",
    "README.md",
)


def test_project_structure():
    for relative_path in REQUIRED_PATHS:
        assert (PROJECT_ROOT / relative_path).is_file()


def test_module_imports():
    for module_name in (
        "backend.pi_reader",
        "backend.dataframe_store",
        "charts.trend",
        "charts.scatter",
        "pages.viewer",
    ):
        assert import_module(module_name)


def test_dash_app_imports():
    from app import app

    assert app.title == "PI Data Viewer"
    assert app.layout is not None
