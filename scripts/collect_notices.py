"""Retain available Cargo dependency license/notice texts in the runtime image."""

import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib


def built_packages(messages):
    selected = {message["package_id"] for message in messages
                if message.get("reason") in {"compiler-artifact", "build-script-executed"}}
    if not selected:
        raise ValueError("Cargo build emitted no package artifacts")
    return selected


def collect(metadata, output, selected=None, reviewed=None):
    if output.exists():
        raise ValueError("New dependency-notice directory required")
    workspace = Path(metadata["workspace_root"]).resolve()
    output.mkdir(parents=True)
    records, total = [], 0
    supplements = {}
    locked = {}
    if reviewed is not None:
        manifest = json.loads((reviewed / "manifest.json").read_text())
        if manifest.get("format") != "reviewed-cargo-notices-v1":
            raise ValueError("Unrecognized reviewed notice inventory")
        supplements = {(p["name"], p["version"]): p for p in manifest["packages"]}
        locked = {(p["name"], p["version"], p.get("source")): p.get("checksum")
                  for p in tomllib.loads((workspace / "Cargo.lock").read_text())["package"]}
    known = {p["id"] for p in metadata["packages"] if "id" in p}
    if selected is not None and (not selected or selected - known):
        raise ValueError("Built packages differ from the locked Cargo metadata")
    for package in metadata["packages"]:
        if selected is not None and package["id"] not in selected:
            continue
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
        supplement = supplements.get((package["name"], package["version"])) if not files else None
        if supplement is not None:
            checksum = locked.get((package["name"], package["version"], package.get("source")))
            if (not str(package.get("source", "")).startswith("registry+")
                    or checksum != supplement["archiveSha256"]
                    or package.get("license") != supplement["declaredLicense"]):
                raise ValueError("Reviewed notice does not match the locked registry package")
            for entry in supplement["files"]:
                relative = Path(entry["file"])
                path = reviewed / relative
                if (relative.is_absolute() or ".." in relative.parts or path.is_symlink()
                        or not path.resolve().is_relative_to(reviewed.resolve())):
                    raise ValueError("Reviewed notice path escapes its bundle")
                data = path.read_bytes()
                total += len(data)
                if (hashlib.sha256(data).hexdigest() != entry["sha256"]
                        or len(data) > 2 * 1024 * 1024 or total > 64 * 1024 * 1024):
                    raise ValueError("Reviewed notice changed or exceeds the size budget")
                target = output / label / "supplemental" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                files.append({"file": target.relative_to(output).as_posix(),
                              "sha256": entry["sha256"], "source": entry["source"]})
        records.append({"name": package["name"], "version": package["version"],
                        "declaredLicense": package.get("license"), "noticeFiles": files,
                        "supplementBasis": supplement["basis"] if supplement is not None else None})
    report = {"packages": records, "copiedBytes": total,
              "scope": "Cargo build artifacts" if selected is not None else "All metadata packages",
              "packagesWithoutNoticeFiles": [p["name"] for p in records if not p["noticeFiles"]]}
    (output / "inventory.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


if __name__ == "__main__":
    messages = [json.loads(line) for line in Path(sys.argv[3]).read_text().splitlines() if line.strip()]
    result = collect(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]),
                     built_packages(messages), Path(sys.argv[4]))
    print(json.dumps({"packages": len(result["packages"]), "copiedBytes": result["copiedBytes"],
                      "packagesWithoutNoticeFiles": result["packagesWithoutNoticeFiles"]}))
