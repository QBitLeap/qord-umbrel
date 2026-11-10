import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("notices", ROOT / "scripts/collect_notices.py")
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


class NoticeTests(unittest.TestCase):
    def test_reviewed_supplement_requires_exact_archive_identity_and_text_hash(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            crate, bundle = root / "crate", root / "bundle"
            crate.mkdir()
            bundle.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()
            lock = workspace / "Cargo.lock"
            lock_text = ('version = 4\n[[package]]\nname = "example"\nversion = "1"\n'
                         'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
                         'checksum = "' + "a" * 64 + '"\n')
            lock.write_text(lock_text)
            text = b"Complete retained license text"
            (bundle / "LICENSE.txt").write_bytes(text)
            manifest = {"format": "reviewed-cargo-notices-v1", "packages": [{
                "name": "example", "version": "1", "declaredLicense": "MIT",
                "archiveSha256": "a" * 64, "basis": "Reviewed upstream text",
                "files": [{"file": "LICENSE.txt", "sha256": hashlib.sha256(text).hexdigest(),
                           "source": "https://example.com/upstream/LICENSE"}]}]}
            (bundle / "manifest.json").write_text(json.dumps(manifest))
            metadata = {"workspace_root": str(root / "workspace"), "packages": [{
                "id": "built", "name": "example", "version": "1", "license": "MIT",
                "source": "registry+https://github.com/rust-lang/crates.io-index",
                "manifest_path": str(crate / "Cargo.toml")} ]}
            report = notices.collect(metadata, root / "valid", {"built"}, bundle)
            self.assertEqual(report["packagesWithoutNoticeFiles"], [])
            copied = report["packages"][0]["noticeFiles"][0]["file"]
            self.assertEqual((root / "valid" / copied).read_bytes(), text)
            lock.write_text(lock_text.replace("a" * 64, "b" * 64))
            with self.assertRaises(ValueError):
                notices.collect(metadata, root / "changed-archive", {"built"}, bundle)
            lock.write_text(lock_text)
            (bundle / "LICENSE.txt").write_text("Changed text")
            with self.assertRaises(ValueError):
                notices.collect(metadata, root / "changed-text", {"built"}, bundle)

    def test_only_built_packages_are_selected_and_unknown_artifacts_are_refused(self):
        selected = notices.built_packages([
            {"reason": "compiler-artifact", "package_id": "built"},
            {"reason": "build-script-executed", "package_id": "built"},
            {"reason": "compiler-message", "package_id": "unbuilt"}])
        self.assertEqual(selected, {"built"})
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            crate = root / "crate"
            crate.mkdir()
            (crate / "LICENSE").write_text("Upstream text")
            metadata = {"workspace_root": str(crate), "packages": [
                {"id": "built", "name": "used", "version": "1", "manifest_path": str(crate / "Cargo.toml")},
                {"id": "unbuilt", "name": "unused", "version": "2", "manifest_path": str(root / "unused/Cargo.toml")}]}
            report = notices.collect(metadata, root / "output", selected)
            self.assertEqual([p["name"] for p in report["packages"]], ["used"])
            self.assertEqual(report["packagesWithoutNoticeFiles"], [])
            with self.assertRaises(ValueError):
                notices.collect(metadata, root / "unknown", {"unknown"})

    def test_workspace_license_is_retained_without_traversal_and_missing_text_is_reported(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            workspace = root / "source"
            crate = workspace / "crates/example"
            crate.mkdir(parents=True)
            (workspace / "LICENSE").write_text("Complete upstream license\n")
            other = root / "registry/other"
            other.mkdir(parents=True)
            metadata = {"workspace_root": str(workspace), "packages": [
                {"name": "example", "version": "1.0.0", "manifest_path": str(crate / "Cargo.toml"),
                 "license": "MIT", "license_file": "../../LICENSE"},
                {"name": "other", "version": "2.0.0", "manifest_path": str(other / "Cargo.toml"),
                 "license": "Apache-2.0"}]}
            output = root / "notices"
            report = notices.collect(metadata, output)
            self.assertEqual(report["packagesWithoutNoticeFiles"], ["other"])
            entry = report["packages"][0]["noticeFiles"][0]
            self.assertNotIn("..", Path(entry["file"]).parts)
            self.assertEqual((output / entry["file"]).read_text(), "Complete upstream license\n")
            self.assertEqual(entry["sha256"], hashlib.sha256((workspace / "LICENSE").read_bytes()).hexdigest())
            self.assertEqual(json.loads((output / "inventory.json").read_text()), report)

    def test_linked_external_license_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            crate = root / "source"
            crate.mkdir()
            outside = root / "outside.txt"
            outside.write_text("Unrelated file")
            (crate / "LICENSE").symlink_to(outside)
            metadata = {"workspace_root": str(crate), "packages": [
                {"name": "example", "version": "1.0.0", "manifest_path": str(crate / "Cargo.toml")}]}
            with self.assertRaises(ValueError):
                notices.collect(metadata, root / "output")
            self.assertEqual(list((root / "output").rglob("*.txt")), [])


if __name__ == "__main__":
    unittest.main()
