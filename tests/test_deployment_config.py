from pathlib import Path
import tomllib

from supplychain_copilot.file_io import MAX_FILE_BYTES


ROOT = Path(__file__).resolve().parents[1]


def test_cloud_upload_limit_matches_application_validation():
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["maxUploadSize"] == MAX_FILE_BYTES // (1024 * 1024) == 20


def test_cloud_runtime_requirements_exclude_development_tools():
    runtime = {line.strip().split("<")[0].split(">")[0].split("=")[0].lower()
               for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#")}
    assert runtime == {"pandas", "streamlit", "openpyxl", "xlrd"}


def test_sample_data_and_entrypoint_are_repository_relative():
    assert (ROOT / "app.py").is_file()
    assert (ROOT / "sample_inventory.csv").is_file()
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'Path(__file__).resolve().parent / "sample_inventory.csv"' in app
