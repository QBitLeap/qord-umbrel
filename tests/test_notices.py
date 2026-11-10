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
