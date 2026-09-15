"""Tests for SkillResources resource directories, readers, and linked file exposure."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agentos.skills.resources import SkillResources


def test_skill_resources_directories_and_helpers(tmp_path: Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    skill_dir.mkdir()

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.py").write_text("print('hello')", encoding="utf-8")

    references_dir = skill_dir / "references"
    references_dir.mkdir()
    (references_dir / "guide.md").write_text("# Guide", encoding="utf-8")

    assets_dir = skill_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "schema.json").write_text('{"type": "object"}', encoding="utf-8")

    templates_dir = skill_dir / "templates"
    templates_dir.mkdir()
    (templates_dir / "report.md").write_text("# {{title}}", encoding="utf-8")

    resources = SkillResources(skill_dir)

    assert resources.has_scripts() is True
    assert resources.has_references() is True
    assert resources.has_assets() is True
    assert resources.has_templates() is True

    assert [p.name for p in resources.list_scripts()] == ["run.py"]
    assert [p.name for p in resources.list_references()] == ["guide.md"]
    assert [p.name for p in resources.list_assets()] == ["schema.json"]
    assert [p.name for p in resources.list_templates()] == ["report.md"]

    # Test reading via dedicated convenience methods
    assert resources.read_script("run.py") == "print('hello')"
    assert resources.read_script("scripts/run.py") == "print('hello')"
    assert resources.read_reference("guide.md") == "# Guide"
    assert resources.read_reference("references/guide.md") == "# Guide"
    assert resources.read_asset("schema.json") == '{"type": "object"}'
    assert resources.read_asset("assets/schema.json") == '{"type": "object"}'
    assert resources.read_template("report.md") == "# {{title}}"
    assert resources.read_template("templates/report.md") == "# {{title}}"

    # Test generic read_resource
    assert resources.read_resource("templates/report.md") == "# {{title}}"
    assert resources.read_resource("report.md") == "# {{title}}"
    assert resources.read_resource("nonexistent.txt") is None


def test_skill_resources_empty_directories(tmp_path: Path) -> None:
    empty_skill_dir = tmp_path / "empty-skill"
    empty_skill_dir.mkdir()

    resources = SkillResources(empty_skill_dir)

    assert resources.has_scripts() is False
    assert resources.has_references() is False
    assert resources.has_assets() is False
    assert resources.has_templates() is False

    assert resources.list_scripts() == []
    assert resources.list_references() == []
    assert resources.list_assets() == []
    assert resources.list_templates() == []


def test_skill_view_linked_files_includes_templates(tmp_path: Path) -> None:
    skill_dir = tmp_path / "doc-skill"
    skill_dir.mkdir()

    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "gen.py").write_text("# generator", encoding="utf-8")

    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "ref.md").write_text("# ref", encoding="utf-8")

    (skill_dir / "assets").mkdir()
    (skill_dir / "assets" / "style.css").write_text("body {}", encoding="utf-8")

    (skill_dir / "templates").mkdir()
    (skill_dir / "templates" / "memo.docx.tpl").write_text("template", encoding="utf-8")

    skill_obj = SimpleNamespace(base_dir=str(skill_dir))

    from agentos.skills.resources import SkillResources

    resources = SkillResources(Path(skill_obj.base_dir))
    found = [
        *resources.list_references(),
        *resources.list_scripts(),
        *resources.list_assets(),
        *resources.list_templates(),
    ]
    linked = [p.relative_to(Path(skill_obj.base_dir)).as_posix() for p in found]

    assert linked == [
        "references/ref.md",
        "scripts/gen.py",
        "assets/style.css",
        "templates/memo.docx.tpl",
    ]
