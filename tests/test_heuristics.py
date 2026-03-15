from pathlib import Path

from readme_rebuilder.services.heuristic_service import HeuristicsService


def test_detects_flask_and_entrypoint():
    service = HeuristicsService()
    data = [
        {
            "path": "app.py",
            "content": "from flask import Flask\napp = Flask(__name__)\nAPI_KEY='x'\npython app.py",
        }
    ]
    tree_summary = {"entries": ["app.py", "requirements.txt"]}
    facts = service.derive_project_facts(data, tree_summary, Path("."))
    assert "Flask" in facts["framework_hints"]
    assert "app.py" in facts["entrypoints"]
    assert "API_KEY" in facts["env_vars"]
