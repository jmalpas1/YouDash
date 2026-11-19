#!/usr/bin/env python3
"""Local two-stage YouMod + YouDash unsigned IPA builder.

Use on macOS with Xcode and requirements-build.txt installed.
All proprietary inputs and unsigned output stay local, out of public GitHub.
"""
import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path
import plistlib
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from build_carplay import assert_decrypted, commands

ROOT = Path(__file__).resolve().parents[1]
MAX_DEB_SIZE = 100 * 1024 * 1024
YOUMOD_DYLIB = "Library/MobileSubstrate/DynamicLibraries/YouMod.dylib"
YOUMOD_BUNDLE = "Library/Application Support/YouMod.bundle/Info.plist"


def run(*cmd):
    print("Running:", " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), check=True, cwd=ROOT)


def unpack_deb(source: Path, output: Path) -> Path:
    """Accept an upstream artifact ZIP with one .deb, or the .deb itself."""
    if source.suffix.lower() == ".deb":
        if source.stat().st_size > MAX_DEB_SIZE:
            raise ValueError("YouMod package is unexpectedly large")
        output.write_bytes(source.read_bytes())
    elif source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            packages = [entry for entry in archive.infolist()
                        if not entry.is_dir() and entry.filename.lower().endswith(".deb")]
            if len(packages) != 1:
                raise ValueError("Expected exactly one .deb in the YouMod artifact ZIP")
            if packages[0].file_size > MAX_DEB_SIZE:
                raise ValueError("YouMod package is unexpectedly large")
            output.write_bytes(archive.read(packages[0]))
    else:
        raise ValueError("YouMod input must be a .deb or GitHub artifact .zip")
    return output


def ar_member(package: Path, member: str) -> bytes:
    # macOS Command Line Tools provide ar; no package installation scripts run.
    return subprocess.run(["ar", "p", str(package), member], check=True,
                          capture_output=True).stdout


def deb_report(package: Path) -> dict:
    control = ar_member(package, "control.tar.gz")
    with tarfile.open(fileobj=io.BytesIO(control), mode="r:gz") as archive:
        control_file = next((m for m in archive.getmembers()
                             if m.name.lstrip("./") == "control"), None)
        if control_file is None:
            raise ValueError("Missing deb control file")
        fields = {}
        for line in archive.extractfile(control_file).read().decode().splitlines():
            if ":" in line and not line[:1].isspace():
                key, val = line.split(":", 1)
                fields[key] = val.strip()
    if fields.get("Package") != "dev.water888.youmod":
        raise ValueError("Unexpected YouMod package identity")

    # Theos rootful packages use data.tar.lzma. Stream without extracting
    # the supplied media frameworks merely to validate package layout.
    compressed = ar_member(package, "data.tar.lzma")
    found = set()
    with lzma.LZMAFile(io.BytesIO(compressed)) as stream:
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            for item in archive:
                if item.isfile():
                    found.add(item.name.lstrip("./"))
    missing = sorted({YOUMOD_DYLIB, YOUMOD_BUNDLE} - found)
    if missing:
        raise ValueError("YouMod deb is missing: " + ", ".join(missing))
    return {"package": fields["Package"], "build": fields.get("Version"),
            "has_dylib": True, "has_bundle": True,
            "contains_ffmpeg_frameworks": any("ffmpegkit.framework/" in p for p in found)}


def ipa_report(path: Path, require_youmod: bool = False) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        infos = [n for n in names if n.startswith("Payload/") and
                 len(n.split("/")) == 3 and n.endswith(".app/Info.plist")]
        if len(infos) != 1:
            raise ValueError("Expected one iOS app in Payload")
        info = plistlib.loads(archive.read(infos[0]))
        app = infos[0].rsplit("/", 1)[0] + "/"
        executable = app + info["CFBundleExecutable"]
        if executable not in names:
            raise ValueError("IPA is missing its main executable")
        data = archive.read(executable)
        commands(data)
        assert_decrypted(data)
        found_mod = app + "Frameworks/YouMod.dylib" in names
        if require_youmod and not found_mod:
            raise ValueError("Cyan output is missing Frameworks/YouMod.dylib")
        return {"version": info.get("CFBundleShortVersionString"),
                "bundle_id": info.get("CFBundleIdentifier"),
                "main_executable_decrypted": True, "youmod_in_frameworks": found_mod,
                "app_root": app}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipa", type=Path, required=True, help="Decrypted YouTube IPA")
    parser.add_argument("--youmod", type=Path, required=True, help="YouMod build ZIP or .deb")
    parser.add_argument("--bundle-id", default="io.github.youtubecar.app")
    parser.add_argument("--reported-version", default="native",
                        help="Default native retains the actual YouTube version")
    parser.add_argument("--preflight-only", action="store_true",
                        help="Inspect inputs without modifying them; works on Linux/macOS")
    args = parser.parse_args()
    for item in (args.ipa, args.youmod):
        if not item.is_file():
            parser.error("File not found: " + str(item))
    with tempfile.TemporaryDirectory(prefix="youdash-youmod-") as temporary:
        staging = Path(temporary)
        deb = unpack_deb(args.youmod, staging / "YouMod.deb")
        source = ipa_report(args.ipa)
        package = deb_report(deb)
        report = {"input_ipa": source, "youmod": package,
                  "input_sha256": hashlib.sha256(args.ipa.read_bytes()).hexdigest(),
                  "status": "preflight_passed"}
        print(json.dumps(report, indent=2), flush=True)
        if args.preflight_only:
            return
        if sys.platform != "darwin":
            parser.error("Full injection requires macOS with Xcode tools")
        stage = staging / "YouTube-With-YouMod.ipa"
        run(sys.executable, "-m", "cyan", "-i", args.ipa.resolve(), "-o", stage,
            "-u", "-w", "-e", "-f", deb)
        stage_report = ipa_report(stage, require_youmod=True)
        print("YouMod stage:", json.dumps(stage_report, indent=2))
        run(sys.executable, ROOT / "scripts/build_carplay.py",
            "--ipa", stage, "--unsigned", "--bundle-id", args.bundle_id,
            "--reported-version", args.reported_version)
        dist = ROOT / "dist" / ("YouTubeCarPlay-" + source["version"] + "-unsigned.ipa")
        final = ipa_report(dist, require_youmod=True)
        print("Unsigned IPA:", dist, "\nFinal checks:", json.dumps(final, indent=2))
        print("Do not upload this IPA or proprietary inputs to a public GitHub repository.")


if __name__ == "__main__":
    main()
