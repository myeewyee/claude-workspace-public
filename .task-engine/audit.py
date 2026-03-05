"""Audit checks: output orphans. Optional TASKS.md export via --regenerate."""

from pathlib import Path

import frontmatter as fm_lib

from fileops import list_task_files, read_task_file
from tasks_md import regenerate


def _extract_parent_name(parent_field) -> str:
    """Extract a task name from a parent wiki-link field."""
    if not parent_field:
        return ""
    val = str(parent_field).strip().strip('"').strip("'")
    if val.startswith("[[") and val.endswith("]]"):
        val = val[2:-2]
    return val


def run_audit(workspace: Path, regenerate_flag: bool = False) -> dict:
    """Run audit checks. Returns structured report."""
    issues = []

    # 1. Output orphans: outputs without a valid parent: pointing to an existing task
    outputs_dir = workspace / "outputs"
    if outputs_dir.exists():
        # Collect all known task names (active + archived)
        all_task_names = set()
        for path in list_task_files(workspace, include_archive=True):
            all_task_names.add(path.stem.lower())

        for f in outputs_dir.iterdir():
            if f.is_file() and f.suffix == ".md" and f.parent == outputs_dir:
                if f.stem.startswith("_"):
                    continue
                try:
                    post = fm_lib.load(str(f))
                    parent_name = _extract_parent_name(post.metadata.get("parent"))
                    if not parent_name:
                        issues.append({
                            "category": "output_orphan",
                            "level": "warning",
                            "detail": f"Output has no parent: field: {f.name}",
                        })
                    elif parent_name.lower() not in all_task_names:
                        issues.append({
                            "category": "output_orphan",
                            "level": "warning",
                            "detail": f"Output parent '{parent_name}' not found in tasks: {f.name}",
                        })
                except Exception:
                    pass

    # Export TASKS.md snapshot if requested
    regenerated = False
    if regenerate_flag:
        regenerate(workspace)
        regenerated = True

    # Build summary
    if issues:
        summary = f"1 check run, {len(issues)} issues need attention"
    else:
        summary = "1 check passed, no issues found"

    return {
        "ok": len(issues) == 0,
        "action": "audit",
        "message": summary,
        "issues": issues,
        "summary": summary,
        "regenerated": regenerated,
        "warnings": [],
    }
