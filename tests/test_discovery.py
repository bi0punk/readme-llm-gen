from pathlib import Path

from readme_rebuilder.config import DiscoverySettings
from readme_rebuilder.services.discovery_service import DiscoveryService


def test_discovers_projects(tmp_path: Path):
    (tmp_path / "proj1").mkdir()
    (tmp_path / "proj1" / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    (tmp_path / "proj2").mkdir()
    (tmp_path / "proj2" / ".git").mkdir()

    service = DiscoveryService(
        DiscoverySettings(
            max_depth=2,
            include_hidden=False,
            exclude_dirs=[".git"],
            project_markers=[".git", "pyproject.toml"],
        )
    )
    projects = service.discover_projects(tmp_path)
    names = [p.name for p in projects]
    assert "proj1" in names
    assert "proj2" in names
