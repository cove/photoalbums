import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import create_metadata_tsv


class TestCreateMetadataTSV(unittest.TestCase):
    def test_find_files_filters_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a.tif").touch()
            (base / "b.jpg").touch()
            (base / "c.txt").touch()

            files = create_metadata_tsv.find_files(base, create_metadata_tsv.FILE_EXTENSIONS)
            names = sorted(p.name for p in files)

            self.assertEqual(names, ["a.tif", "b.jpg"])

    def test_collect_all_metadata_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            file_path = base / "sub" / "a.tif"
            file_path.parent.mkdir()
            file_path.touch()

            with mock.patch("create_metadata_tsv.PHOTO_ALBUMS_DIR", base), mock.patch(
                "create_metadata_tsv.extract_metadata",
                return_value={"XMP-dc:Description": "desc"},
            ):
                results = create_metadata_tsv.collect_all_metadata([file_path], progress=False)

            self.assertEqual(len(results), 1)
            expected = str(Path("Photo Albums") / "sub" / "a.tif")
            self.assertEqual(results[0]["FilePath"], expected)

    def test_write_tsv_outputs_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "metadata.tsv"
            data = [{"FilePath": "Photo Albums/a.tif", "XMP-dc:Description": "desc"}]

            create_metadata_tsv.write_tsv(data, str(output_path))

            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("FilePath", content.splitlines()[0])
            self.assertIn("Photo Albums/a.tif", content)


if __name__ == "__main__":
    unittest.main()
