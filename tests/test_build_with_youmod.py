"""Unit checks for the unsigned YouMod + YouDash packaging wrapper."""
from pathlib import Path
import plistlib
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_with_youmod import ipa_report, unpack_deb


class YouModWrapperTests(unittest.TestCase):
    def test_unpack_artifact_zip_containing_one_deb(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            with zipfile.ZipFile(path / "upstream.zip", "w") as archive:
                archive.writestr("dev.water888.youmod_298_iphoneos-arm.deb", b"dummy-deb")
            actual = unpack_deb(path / "upstream.zip", path / "YouMod.deb")
            self.assertEqual(actual.read_bytes(), b"dummy-deb")

    def test_reject_multiple_debs(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            with zipfile.ZipFile(path / "bad.zip", "w") as archive:
                archive.writestr("first.deb", b"A")
                archive.writestr("second.deb", b"B")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                unpack_deb(path / "bad.zip", path / "YouMod.deb")

    def test_detect_decrypted_input_and_missing_youmod(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "youtube.ipa"
            info = {"CFBundleIdentifier": "com.google.ios.youtube",
                    "CFBundleShortVersionString": "21.46.3",
                    "CFBundleExecutable": "YouTube"}
            executable = struct.pack("<IIIIIIII", 0xfeedfacf, 0x100000c, 0,
                                     2, 0, 0, 0, 0)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("Payload/YouTube.app/Info.plist", plistlib.dumps(info))
                archive.writestr("Payload/YouTube.app/YouTube", executable)
            report = ipa_report(path)
            self.assertEqual(report["version"], "21.46.3")
            self.assertFalse(report["youmod_in_frameworks"])
            with self.assertRaisesRegex(ValueError, "missing Frameworks/YouMod"):
                ipa_report(path, require_youmod=True)


if __name__ == "__main__":
    unittest.main()
