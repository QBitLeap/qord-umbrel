"""Retain available Cargo dependency license/notice texts in the runtime image."""

import hashlib
import json
from pathlib import Path
import re
import sys


def collect(metadata, output):
    if output.exists():
        raise ValueError("New dependency-notice directory required")
    workspace = Path(metadata["workspace_root"]).resolve()
    output.mkdir(parents=True)
    records, total = [], 0
    for package in metadata["packages"]:
        label = package["name"] + "-" + package["version"]
        if re.fullmatch(r"[A-Za-z0-9_.+-]+", label) is None:
            raise ValueError("Unexpected package name/version")
        root = Path(package["manifest_path"]).resolve().parent
        candidates = {p for p in root.rglob("*") if p.is_file() and
                      p.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT"))
                      and not any(part in {".git", "target", "node_modules"} for part in p.relative_to(root).parts)}
        if package.get("license_file"):
            candidates.add(root / package["license_file"])
        if not candidates and root.is_relative_to(workspace):
            candidates.update(p for p in workspace.glob("LICENSE*") if p.is_file())
        files = []
        for path in sorted(candidates):
            resolved = path.resolve()
            if not resolved.is_relative_to(root) and not (root.is_relative_to(workspace) and resolved.is_relative_to(workspace)):
                raise ValueError("Dependency notice escapes its source root")
            if path.is_symlink() or not path.is_file():
                raise ValueError("Linked or missing dependency notice")
            data = path.read_bytes()
            total += len(data)
            if len(data) > 2 * 1024 * 1024 or total > 64 * 1024 * 1024:
                raise ValueError("Dependency notice size budget exceeded; review without truncating")
            relative = resolved.relative_to(root) if resolved.is_relative_to(root) else Path("workspace") / resolved.relative_to(workspace)
            target = output / label / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            files.append({"file": target.relative_to(output).as_posix(), "sha256": hashlib.sha256(data).hexdigest()})
        records.append({"name": package["name"], "version": package["version"],
                        "declaredLicense": package.get("license"), "noticeFiles": files})
    report = {"packages": records, "copiedBytes": total,
              "packagesWithoutNoticeFiles": [p["name"] for p in records if not p["noticeFiles"]]}
    (output / "inventory.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


if __name__ == "__main__":
    result = collect(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]))
    print(json.dumps({"packages": len(result["packages"]), "copiedBytes": result["copiedBytes"],
                      "packagesWithoutNoticeFiles": result["packagesWithoutNoticeFiles"]}))
