from importlib import import_module
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    "app.py",
    "config/config.yaml",
    "start.bat",
    ".gitignore",
    "PIReader/Program.cs",
    "PIReader/build.bat",
    "PIReader.Tests/PIReader.Tests.csproj",
    "PIReader.Tests/Program.cs",
    "backend/__init__.py",
    "backend/file_reader.py",
    "backend/pi_reader.py",
    "backend/dataframe_store.py",
    "backend/statistics.py",
    "backend/spc.py",
    "backend/capability.py",
    "backend/frequency.py",
    "charts/__init__.py",
    "charts/trend.py",
    "charts/scatter.py",
    "charts/histogram.py",
    "charts/boxplot.py",
    "charts/probability.py",
    "charts/control_chart.py",
    "charts/capability.py",
    "charts/frequency.py",
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
        "backend.file_reader",
        "backend.dataframe_store",
        "charts.trend",
        "charts.scatter",
        "backend.spc",
        "backend.capability",
        "backend.frequency",
        "charts.boxplot",
        "charts.probability",
        "charts.control_chart",
        "charts.capability",
        "charts.frequency",
        "pages.viewer",
    ):
        assert import_module(module_name)


def test_dash_app_imports():
    from app import app

    assert app.title == "PI Data Viewer"
    assert app.layout is not None


def test_probability_chart_does_not_read_external_data_sources():
    source = (PROJECT_ROOT / "charts/probability.py").read_text(encoding="utf-8")

    for forbidden in ("read_pi_data", "backend.pi_reader", "read_local_file"):
        assert forbidden not in source


def test_capability_modules_do_not_read_external_data_sources_or_copy_imr_sigma():
    for relative_path in ("backend/capability.py", "charts/capability.py"):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for forbidden in (
            "read_pi_data",
            "backend.pi_reader",
            "read_local_file",
            "store_dataframe",
        ):
            assert forbidden not in source
    capability_source = (PROJECT_ROOT / "backend/capability.py").read_text(
        encoding="utf-8"
    )
    assert "1.128" not in capability_source
    assert "calculate_imr" in capability_source


def test_frequency_modules_do_not_read_external_data_or_repair_sampling():
    for relative_path in ("backend/frequency.py", "charts/frequency.py"):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for forbidden in (
            "read_pi_data",
            "backend.pi_reader",
            "read_local_file",
            "store_dataframe",
        ):
            assert forbidden not in source
    frequency_source = (PROJECT_ROOT / "backend/frequency.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (".resample(", ".interpolate(", ".ffill(", ".bfill("):
        assert forbidden not in frequency_source


def test_project_ignore_and_start_paths():
    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in ignored
    assert "*.py[cod]" in ignored
    assert ".pytest_cache/" in ignored
    assert "PIReader/PIReader.exe" in ignored
    assert "PIReader/config.txt" not in ignored
    assert "PIReader/tags.txt" not in ignored

    start = (PROJECT_ROOT / "start.bat").read_text(encoding="utf-8")
    assert 'PI_CONFIG=%~dp0PIReader\\config.txt' in start
    assert 'PI_READER_EXE=%~dp0PIReader\\PIReader.exe' in start
    assert "D:\\" not in start
    assert "C:\\Users\\" not in start
