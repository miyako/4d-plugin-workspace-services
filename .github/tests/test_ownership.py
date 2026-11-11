"""Compile all actual native sources against closed in-memory platform boundaries."""

import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "d5585cbc7d26f7e0bd8b86e97c1c2096be948bc9"
SDK = {
    "4DPluginAPI.c": "29788ed041effaf67269ccd93f971e8aee2ce5f8",
    "4DPluginAPI.h": "9054b45ffc7ff6f5b8d57529a3788a55d977b314",
    "PublicTypes.h": "2bb392e73e9c556c274fe0a75b3a6b83e310b77c",
    "PrivateTypes.h": "77053dc0c0a3718d2d3b6f158371a6af78c6ae66",
    "EntryPoints.h": "730f2f77ff2713fb2fe4b7d6562baeedf5f664cb",
    "Flags.h": "10a83185333dac06a62dda61b9f9428243d1e2ee",
    "4DPluginAPI.def": "996ecc4ab11ad165de9192eba2e7478db141c757",
}
WRAPPERS = {
    "ARRAY_BOOLEAN", "ARRAY_DATE", "ARRAY_INTEGER", "ARRAY_LONGINT", "ARRAY_REAL",
    "ARRAY_TEXT", "ARRAY_TIME", "C_BLOB", "C_DATE", "C_INTEGER", "C_LONGINT",
    "C_PICTURE", "C_POINTER", "C_REAL", "C_TEXT", "C_TIME",
}
NONCOPY = (
    "ARRAY_BOOLEAN", "ARRAY_DATE", "ARRAY_INTEGER", "ARRAY_LONGINT", "ARRAY_REAL",
    "ARRAY_TEXT", "ARRAY_TIME", "C_BLOB", "CPicture", "C_PICTURE",
)
CHANGED_NATIVE = {
    "4D Plugin API/Classes/" + name + ".h" for name in NONCOPY if name != "CPicture"
} | {"4D Plugin API/Classes/C_PICTURE.cpp", "4D Plugin API/Classes/C_POINTER.cpp"}
FIXTURES = ("ASCII", "\u65e5", "\U0001f600", "")


def cases():
    for text in FIXTURES:
        for empty in ("allocated", "null"):
            for name in ("path", "arrays", "scalar", "pointer"):
                yield (name, text, empty, "none")
            for mode in ("success", "denied"):
                yield ("dispatch", text, empty, mode)
    for text in (".png", ".jpg", ".tif", *FIXTURES):
        for empty in ("allocated", "null"):
            yield ("copy", text, empty, "none")
    for name in ("bytes", "gray", "size", "thumbnail", "creation-failure"):
        yield (name, "", "allocated", "none")
    for name in ("path", "gray", "copy", "size", "thumbnail"):
        for mode in ("command", "handle", "owned-result"):
            for empty in ("allocated", "null"):
                yield (name, ".png" if name == "copy" else "", empty, mode)
    for name in (*NONCOPY, "C_TEXT", "values"):
        yield ("traits", name, "allocated", "none")


def baseline_failure(case):
    return (case[0] in ("path", "copy", "bytes", "gray", "size", "thumbnail",
                        "creation-failure", "pointer")
            or (case[0] == "traits" and case[1] in NONCOPY))


def diagnostic(case):
    name, text, empty, mode = case
    if name == "traits":
        return "unowned picture disposal" if text == "CPicture" else \
            "AddressSanitizer: heap-use-after-free"
    if name == "copy" and text in (".png", ".jpg", ".tif", "ASCII"):
        return "AddressSanitizer: heap-buffer-overflow"
    if name == "pointer":
        return "reference helper fetched an owning value"
    if name == "creation-failure":
        return "retain dead picture"
    if name == "bytes":
        return "creation owner not released"
    if name == "path" and (text or empty == "allocated"):
        return "duplicate/unowned string disposal"
    return "unbalanced (string allocations|picture references)"


@unittest.skipUnless(sys.platform == "darwin", "macOS isolated compiler host")
class OwnershipTests(unittest.TestCase):
    def build(self, source, directory):
        api = source / "4D Plugin API"
        for name, wanted in SDK.items():
            contents = (api / name).read_bytes()
            blob = hashlib.sha1(f"blob {len(contents)}\0".encode() + contents).hexdigest()
            self.assertEqual(blob, wanted, f"Protected SDK changed: {name}")
        wrappers = sorted((api / "Classes").glob("*.cpp"))
        self.assertEqual({p.stem for p in wrappers}, WRAPPERS)
        tests = ROOT / ".github/tests"
        binary = directory / "ownership"
        command = [
            "clang++", "-std=c++14", "-x", "objective-c++",
            "-include", str(tests / "ownership_platform.h"),
            "-I", str(api), "-I", str(api / "Classes"), "-I", str(source),
            "-fsanitize=address,undefined", "-fno-sanitize=alignment",
            "-fno-omit-frame-pointer", "-g", "-Wno-deprecated-declarations",
            "-Wno-return-type-c-linkage", "-Wno-ignored-attributes",
            "-Wno-writable-strings",
            str(api / "4DPluginAPI.c"), *map(str, wrappers), str(source / "4DPlugin.cpp"),
            str(tests / "ownership_host.mm"), "-framework", "Cocoa",
            "-framework", "Carbon", "-o", str(binary),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        imports = subprocess.check_output(["nm", "-u", str(binary)], text=True)
        symbols = {line.split()[-1] for line in imports.splitlines() if line.split()}
        forbidden = {
            "_system", "_popen", "_execve", "_posix_spawn", "_kill", "_socket",
            "_connect", "_fopen", "_open", "_opendir", "_NSLog",
            "_CFURLCreateWithFileSystemPath", "_CFURLCopyFileSystemPath",
            "_UTTypeCreatePreferredIdentifierForTag", "_UTTypeCopyPreferredTagWithClass",
            "_UTGetOSTypeFromString", "_NSFileTypeForHFSTypeCode",
            "_CGImageDestinationCreateWithData", "_CGImageDestinationAddImage",
            "_CGImageDestinationFinalize",
        } | {"_OBJC_CLASS_$_" + name for name in (
            "NSURL", "NSWorkspace", "NSFileManager", "NSApplication", "NSBundle",
            "NSAppleEventDescriptor", "NSImage", "NSProcessInfo", "NSNotificationCenter",
        )}
        rejected = forbidden & symbols
        rejected |= {s for s in symbols if re.match(
            r"_(?:LSOpen|LSCopy|NSWorkspace|CGEvent|AXUI|IOService|"
            r"FSPath|FSMove|FSDelete|FSCopy|mount|unmount|recycle|trash)", s)}
        self.assertFalse(rejected, f"Real platform boundary linked: {rejected}")
        return binary

    def test_fixed_and_immutable_baseline(self):
        records = []
        try:
            with tempfile.TemporaryDirectory(prefix="workspace-ownership-") as temp:
                directory = Path(temp)
                baseline = directory / "baseline"
                baseline.mkdir()
                archive = subprocess.check_output([
                    "git", "archive", BASELINE, "4D Plugin API", "4DPlugin.cpp", "4DPlugin.h",
                ], cwd=ROOT)
                with tarfile.open(fileobj=io.BytesIO(archive)) as files:
                    for member in files.getmembers():
                        path = Path(member.name)
                        self.assertFalse(path.is_absolute() or ".." in path.parts)
                        self.assertTrue(member.isfile() or member.isdir())
                    files.extractall(baseline, filter="data")
                for label, source in (("fixed", ROOT), ("baseline", baseline)):
                    build = directory / f"{label}-build"
                    build.mkdir()
                    binary = self.build(source, build)
                    passed = failed = 0
                    for case in cases():
                        result = subprocess.run(
                            [str(binary), *case], capture_output=True, text=True,
                            env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                                 "UBSAN_OPTIONS": "halt_on_error=1"},
                        )
                        records.append({
                            "source": label, "case": case, "returncode": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr,
                        })
                        expected = label == "baseline" and baseline_failure(case)
                        with self.subTest(source=label, case=case):
                            if expected:
                                failed += 1
                                self.assertNotEqual(result.returncode, 0, "baseline defect not reproduced")
                                self.assertRegex(result.stderr, diagnostic(case))
                            else:
                                passed += 1
                                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                                self.assertIn("strings=0 pictures=0 handles=0", result.stdout)
                    print(f"{label}: cases={passed+failed} passes={passed} "
                          f"expected_defects={failed}; unchanged full SDK + 16 wrappers + "
                          "actual macOS dispatcher; import gate passed", file=sys.stderr)
                    self.assertEqual((passed, failed), (109, 0) if label == "fixed" else (34, 75))
        finally:
            if log := os.environ.get("OWNERSHIP_LOG"):
                Path(log).write_text(json.dumps(records, ensure_ascii=True, indent=2) + "\n")

    def test_preservation(self):
        paths = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", BASELINE], cwd=ROOT, text=True,
        ).splitlines()
        allowed = CHANGED_NATIVE | {"README.md", ".github/tests/test_repository_contract.py"}
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", BASELINE, "--", *paths], cwd=ROOT, text=True,
        ).splitlines()
        self.assertFalse(set(changed) - allowed, f"Protected paths changed: {changed}")
        workflow = (ROOT / ".github/workflows/ownership.yml").read_text()
        self.assertIn("branches: [miyako-workspace-services-ownership, master]", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("runs-on: macos-latest", workflow)
        self.assertNotRegex(
            workflow, r"(?i)workflow_dispatch|upload|artifact|release\.py|"
            r"xcodebuild|msbuild|codesign|notarytool|pip install|contents: write",
        )

    def test_complete_native_inventory_and_manifests(self):
        expected = {"4D Plugin API/Classes/" + name + ".cpp" for name in WRAPPERS}
        expected |= {"4D Plugin API/4DPluginAPI.c", "4DPlugin.cpp"}
        tracked = subprocess.check_output(
            ["git", "ls-files", "*.cpp", "*.c", "*.mm", "*.m"], cwd=ROOT, text=True,
        ).splitlines()
        self.assertEqual(set(tracked) - {".github/tests/ownership_host.mm"}, expected)
        project = ET.fromstring((ROOT / "Workspace Services.vcxproj").read_bytes())
        ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        compiled = {
            item.attrib["Include"].replace("\\", "/")
            for item in project.findall(".//m:ClCompile[@Include]", ns)
        }
        self.assertEqual(compiled, expected)
        mac = (ROOT / "Workspace Services.xcodeproj/project.pbxproj").read_text()
        phase = mac.split("/* Begin PBXSourcesBuildPhase section */", 1)[1].split(
            "/* End PBXSourcesBuildPhase section */", 1)[0]
        self.assertEqual(set(re.findall(r"/\* ([^*]+\.(?:cpp|c)) in Sources \*/", phase)),
                         {Path(p).name for p in expected})
        manifests = [ROOT / "manifest.json", ROOT / (
            "Workspace Services.4dbase/Plugins/Workspace Services.bundle/Contents/Resources/manifest.json")]
        commands = json.loads(manifests[0].read_text())["commands"]
        self.assertEqual(len(commands), 18)
        self.assertEqual([i+1 for i,c in enumerate(commands) if "&Y" in c["syntax"]],
                         [1, 5, 17, 18])
        self.assertEqual(json.loads(manifests[0].read_text()), json.loads(manifests[1].read_text()))


if __name__ == "__main__":
    unittest.main()
