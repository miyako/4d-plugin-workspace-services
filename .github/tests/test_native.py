"""Execute the literal macOS workflow Bash with a closed, stub-only native PATH."""

import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
BASE = "44a5101cf089f3eb6f63f3b77a93486a8169f164"
WORKFLOW = (ROOT / ".github/workflows/release.yml").read_text()
PRODUCT = "Workspace Services"
BUNDLE = f"{PRODUCT}.4dbase/Plugins/{PRODUCT}.bundle"
SOURCE_PATHS = (
    "Info.plist", "English.lproj/InfoPlist.strings",
    f"{PRODUCT}.xcodeproj/project.pbxproj",
)
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location(
    "native_source_version", ROOT / ".github/scripts/source_version.py"
)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def step(name):
    matches = re.findall(
        rf"^      - name: {re.escape(name)}\n"
        r"(?:(?!      - ).*\n)*?        run: \|\n"
        r"((?:          .*(?:\n|$)|[ \t]*\n)+)",
        WORKFLOW, re.MULTILINE,
    )
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one literal run block: {name}")
    return textwrap.dedent(matches[0])


STUB = r'''
import json
import os
from pathlib import Path
import plistlib
import re
import sys

tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([tool, *args]) + "\n")
root = Path.cwd()
product = "Workspace Services"
bundle = root / os.environ["BUNDLE_PATH"]
contents = bundle / "Contents"
mode = os.environ.get("BUILD_MODE", "complete")

if tool == "xcodebuild":
    assert args == [
        "-project", product + ".xcodeproj", "-target", product,
        "-configuration", "Default", "ARCHS=arm64 x86_64",
        "ONLY_ACTIVE_ARCH=NO", "MACOSX_DEPLOYMENT_TARGET=11.0",
        "CODE_SIGNING_ALLOWED=NO",
        "CONFIGURATION_BUILD_DIR=" + str(bundle.parent), "build",
    ], args
    for path in (
        contents / ("MacOS/" + product), contents / "Info.plist",
        contents / "Resources/English.lproj/InfoPlist.strings",
        contents / "_CodeSignature", bundle.parent / (product + ".build"),
    ):
        assert not path.exists(), "stale generated output survived: " + str(path)
    if mode == "failed-build":
        sys.exit(70)
    if mode != "missing-binary":
        target = contents / ("MacOS/" + product)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"" if mode == "empty-binary" else b"fresh universal binary")
    if mode != "missing-plist":
        data = plistlib.loads((root / "Info.plist").read_bytes())
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            if key in data:
                data[key] = re.sub(
                    r"\$\([^)]+\)|\$\{[^}]+\}", os.environ["SOURCE_VERSION"], data[key]
                )
        if mode == "stale-plist":
            data["CFBundleShortVersionString"] = os.environ["STALE_VERSION"]
        if mode == "stale-build":
            data["CFBundleVersion"] = os.environ["STALE_VERSION"]
        (contents / "Info.plist").write_bytes(plistlib.dumps(data))
    if mode != "missing-localized":
        target = contents / "Resources/English.lproj/InfoPlist.strings"
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (root / "English.lproj/InfoPlist.strings").read_bytes()
        if mode == "stale-localized":
            data = data.replace(
                os.environ["SOURCE_VERSION"].encode(), os.environ["STALE_VERSION"].encode()
            )
        target.write_bytes(data)
elif tool == "lipo":
    assert args == ["-archs", os.environ["BUNDLE_PATH"] + "/Contents/MacOS/" + product]
    assert Path(args[-1]).is_file()
    print(os.environ.get("ARCHS", "arm64 x86_64"))
elif tool == "python3":
    if args[:2] == [".github/scripts/source_version.py", "--verify-bundle"]:
        assert args == [".github/scripts/source_version.py", "--verify-bundle",
                        os.environ["BUNDLE_PATH"]]
    elif args[:1] == ["-c"]:
        assert args == ["-c", 'import json,sys; print(json.load(sys.stdin)["status"])']
    elif args[:1] == [".github/scripts/release.py"]:
        assert args[1:4] in [
            ["preflight", "--sha", os.environ["SELECTED_SHA"]],
            ["publish", "--sha", os.environ["SELECTED_SHA"]],
        ]
        if args[1] == "publish":
            assert args[4:] == [os.environ["ZIP_PATH"], os.environ["DMG_PATH"]]
        sys.exit(int(os.environ.get("RELEASE_EXIT", "0")))
    else:
        raise AssertionError(args)
    os.execv(os.environ["REAL_PYTHON"], [os.environ["REAL_PYTHON"], *args])
elif tool == "base64":
    assert args == ["--decode", "-o", os.environ["RUNNER_TEMP"] + "/certificate.p12"]
    assert sys.stdin.read() == "fixture-certificate"
    Path(args[-1]).write_bytes(b"fixture certificate")
elif tool == "security":
    if os.environ.get("SECURITY_FAIL"):
        sys.exit(74)
    if args[:1] == ["find-identity"]:
        assert args == ["find-identity", "-v", "-p", "codesigning", os.environ["KEYCHAIN_PATH"]]
        if os.environ.get("SIGN_MODE") != "missing-identity":
            print('1) FAKE "Developer ID Application: Fixture (TEST)"')
    else:
        assert args[0] in {
            "create-keychain", "set-keychain-settings", "unlock-keychain",
            "import", "list-keychain", "set-key-partition-list",
        }, args
elif tool == "codesign":
    verify = args[:1] == ["--verify"]
    expected = (
        ["--verify", "--deep", "--strict", "--verbose=2", os.environ["BUNDLE_PATH"]]
        if verify else
        ["--verbose", "--deep", "--timestamp", "--force", "--options=runtime",
         "--sign", "Developer ID Application: Fixture (TEST)", os.environ["BUNDLE_PATH"]]
    )
    assert args == expected, args
    if os.environ.get("SIGN_MODE") == ("verify" if verify else "sign"):
        sys.exit(75)
elif tool in ("ditto", "hdiutil"):
    expected = (
        ["-c", "-k", "--keepParent", os.environ["BUNDLE_PATH"]]
        if tool == "ditto" else
        ["create", "-format", "UDBZ", "-volname", product,
         "-srcfolder", os.environ["BUNDLE_PATH"]]
    )
    assert args[:-1] == expected, args
    if os.environ.get("PACKAGE_MODE") == tool:
        sys.exit(76)
    Path(args[-1]).write_bytes(b"fixture archive")
elif tool == "xcrun":
    scenario = os.environ.get("NOTARY_MODE", "accepted")
    if args[:2] == ["notarytool", "store-credentials"]:
        assert args == [
            "notarytool", "store-credentials", "notarytool-profile",
            "--apple-id", "fixture-apple-id", "--team-id", "fixture-team",
            "--password", "fixture-password", "--keychain", os.environ["KEYCHAIN_PATH"],
        ]
        if scenario == "credentials":
            sys.exit(77)
    elif args[:2] == ["notarytool", "submit"]:
        assert args[3:] == [
            "--keychain-profile", "notarytool-profile", "--keychain",
            os.environ["KEYCHAIN_PATH"], "--wait", "--output-format", "json",
        ]
        assert Path(args[2]).is_file()
        second = args[2].endswith(".dmg")
        fail_here = not scenario.startswith("second-") or second
        local = scenario.removeprefix("second-") if fail_here else "accepted"
        if local in ("transport", "accepted-nonzero"):
            print(json.dumps({"status": "Accepted"}))
            sys.exit(78)
        if local == "malformed":
            print("not JSON")
        elif local == "missing-status":
            print(json.dumps({"id": "fixture"}))
        else:
            print(json.dumps({"id": "fixture", "status":
                              "Invalid" if local == "invalid" else "Accepted"}))
    elif args[:2] == ["stapler", "staple"]:
        assert args == ["stapler", "staple", os.environ["DMG_PATH"]]
        if scenario == "staple":
            sys.exit(79)
    else:
        raise AssertionError(args)
else:
    raise AssertionError("Unexpected native tool: " + tool)
'''


class NativeShellTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix=".native-tests-", dir=ROOT)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for relative in (*SOURCE_PATHS, ".github/scripts/source_version.py"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, path)
        self.version = source.read(self.root)
        a, b, c = map(int, self.version.split("."))
        self.stale = f"{a}.{b}.{c + 1}"
        self.bundle = self.root / BUNDLE
        self.contents = self.bundle / "Contents"
        self.log = self.root / "calls.jsonl"
        self.env_file = self.root / "github-env"
        self.env_file.touch()
        self.bin = self.root / "closed-path"
        self.bin.mkdir()
        for tool in (
            "xcodebuild", "lipo", "python3", "security", "codesign",
            "ditto", "hdiutil", "xcrun", "base64",
        ):
            path = self.bin / tool
            path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(STUB))
            path.chmod(0o755)
        for tool in ("rm", "grep", "head", "sed"):
            executable = shutil.which(tool)
            self.assertIsNotNone(executable)
            (self.bin / tool).symlink_to(executable)
        runner = self.root / "runner"
        runner.mkdir()
        self.env = {
            "PATH": str(self.bin), "REAL_PYTHON": sys.executable,
            "PYTHONDONTWRITEBYTECODE": "1", "CALL_LOG": str(self.log),
            "SOURCE_VERSION": self.version, "STALE_VERSION": self.stale,
            "BUNDLE_PATH": BUNDLE, "KEYCHAIN_PATH": str(runner / "build.keychain-db"),
            "RUNNER_TEMP": str(runner), "GITHUB_ENV": str(self.env_file),
            "SELECTED_SHA": "a" * 40, "CERT_BASE64": "fixture-certificate",
            "CERT_PASSWORD": "fixture-cert-password", "KEYCHAIN_PASSWORD": "fixture-keychain",
            "APPLE_ID": "fixture-apple-id", "TEAM_ID": "fixture-team",
            "APP_PASSWORD": "fixture-password",
            "ZIP_PATH": f"{PRODUCT}-{self.version}.zip",
            "DMG_PATH": f"{PRODUCT}-{self.version}.dmg",
        }
        self.preserved = {}
        generated = {
            f"MacOS/{PRODUCT}", "Info.plist",
            "Resources/English.lproj/InfoPlist.strings", "_CodeSignature/CodeResources",
        }
        prefix = BUNDLE + "/Contents/"
        originals = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", BASE, "--", prefix],
            text=True,
        ).splitlines()
        for path in originals:
            relative = path.removeprefix(prefix)
            if relative not in generated:
                self.preserved[relative] = subprocess.check_output(
                    ["git", "-C", str(ROOT), "show", f"{BASE}:{path}"]
                )
        for relative in (
            "MacOS/Dependency.dylib",
            "Frameworks/Dependency.framework/Versions/A/Dependency",
            "Frameworks/Dependency.framework/Versions/A/Resources/data",
        ):
            self.preserved[relative] = b"preserved dependency"
        for relative, data in self.preserved.items():
            self.write(relative, data)
        (self.contents / "Frameworks/Dependency.framework/Versions/Current").symlink_to("A")
        for relative in generated:
            self.write(relative, b"stale generated output")
        self.sibling = self.bundle.parent / "Default/Unrelated.bundle/resource"
        self.sibling.parent.mkdir(parents=True)
        self.sibling.write_bytes(b"unrelated Default sibling")
        intermediate = self.bundle.parent / f"{PRODUCT}.build/stale"
        intermediate.parent.mkdir()
        intermediate.write_bytes(b"stale intermediate")

    def write(self, relative, data):
        path = self.contents / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run_step(self, name, prefix="", **env):
        script = step(name)
        for key, value in {
            "env.PRODUCT_NAME": PRODUCT, "env.XCODE_PROJECT": f"{PRODUCT}.xcodeproj",
            "env.MACOS_DEPLOYMENT_TARGET": "11.0",
            "needs.version.outputs.version": self.version,
        }.items():
            script = script.replace("${{ " + key + " }}", value)
        self.assertNotIn("${{", script)
        return subprocess.run(
            ["/bin/bash", "-c", prefix + "\n" + script],
            cwd=self.root, env={**self.env, **env}, text=True,
            capture_output=True, timeout=30,
        )

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def calls(self, tool):
        if not self.log.exists():
            return []
        return [call[1:] for line in self.log.read_text().splitlines()
                if (call := json.loads(line))[0] == tool]

    def build(self, **env):
        self.assert_ok(self.run_step("build macOS plugin (universal)", **env))

    def test_build_preserves_all_original_resources_dependencies_and_default_sibling(self):
        self.build()
        self.assertEqual((self.contents / f"MacOS/{PRODUCT}").read_bytes(),
                         b"fresh universal binary")
        for relative, data in self.preserved.items():
            self.assertEqual((self.contents / relative).read_bytes(), data, relative)
        link = self.contents / "Frameworks/Dependency.framework/Versions/Current"
        self.assertEqual(link.readlink(), Path("A"))
        self.assertEqual(self.sibling.read_bytes(), b"unrelated Default sibling")
        self.assertFalse((self.contents / "_CodeSignature").exists())
        self.assertFalse((self.bundle.parent / f"{PRODUCT}.build").exists())
        self.assert_ok(self.run_step("verify universal binary"))
        self.assertEqual(self.env_file.read_text(), f"BUNDLE_PATH={BUNDLE}\n")

    def test_cleanup_and_build_failures_stop_execution(self):
        result = self.run_step(
            "build macOS plugin (universal)", prefix="rm() { return 81; }"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls("xcodebuild"), [])
        result = self.run_step("build macOS plugin (universal)", BUILD_MODE="failed-build")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls("xcodebuild")), 1)

    def test_missing_empty_and_stale_outputs_cannot_pass_verification(self):
        for mode in (
            "missing-binary", "empty-binary", "missing-plist", "missing-localized",
            "stale-plist", "stale-build", "stale-localized",
        ):
            with self.subTest(mode=mode):
                self.build(BUILD_MODE=mode)
                self.assertNotEqual(self.run_step("verify universal binary").returncode, 0)
                self.assertEqual(self.env_file.read_text(), "")

    def test_architecture_tokens_are_exact_but_extras_are_allowed(self):
        self.build()
        for architectures in (
            "arm64", "x86_64", "arm64e x86_64", "arm64 x86_64h",
            "notarm64 x86_64", "arm64 x86_64_extra",
        ):
            with self.subTest(architectures=architectures):
                self.assertNotEqual(
                    self.run_step("verify universal binary", ARCHS=architectures).returncode, 0
                )
        self.assertEqual(self.calls("python3"), [])
        self.assert_ok(self.run_step("verify universal binary", ARCHS="arm64 x86_64 i386"))

    def test_xml_binary_and_utf16_built_metadata_match_selected_source(self):
        self.build()
        text = (self.root / "English.lproj/InfoPlist.strings").read_bytes().decode()
        values = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)";', text))
        plist = plistlib.loads((self.contents / "Info.plist").read_bytes())
        for serialization in (plistlib.FMT_XML, plistlib.FMT_BINARY):
            self.write("Info.plist", plistlib.dumps(plist, fmt=serialization))
            for key in (None, "CFBundleShortVersionString", "CFBundleGetInfoString"):
                with self.subTest(serialization=serialization, key=key):
                    localized = dict(values)
                    if key:
                        localized[key] = localized[key].replace(self.version, self.stale)
                    self.write("Resources/English.lproj/InfoPlist.strings",
                               plistlib.dumps(localized, fmt=serialization))
                    result = self.run_step("verify universal binary")
                    self.assertEqual(result.returncode == 0, key is None,
                                     result.stdout + result.stderr)
        for encoding in ("utf-16", "utf-16-be"):
            for stale in (False, True):
                with self.subTest(encoding=encoding, stale=stale):
                    localized = text.replace(self.version, self.stale) if stale else text
                    prefix = b"\xfe\xff" if encoding == "utf-16-be" else b""
                    self.write("Resources/English.lproj/InfoPlist.strings",
                               prefix + localized.encode(encoding))
                    result = self.run_step("verify universal binary")
                    self.assertEqual(result.returncode == 0, not stale,
                                     result.stdout + result.stderr)

    def test_certificate_and_notary_credentials_are_exercised_only_through_stubs(self):
        self.assert_ok(self.run_step("import Developer ID certificate"))
        self.assertEqual(len(self.calls("security")), 6)
        self.assertIn(f"KEYCHAIN_PATH={self.env['KEYCHAIN_PATH']}\n",
                      self.env_file.read_text())
        self.assert_ok(self.run_step("store notarytool credentials"))
        self.assertNotEqual(
            self.run_step("import Developer ID certificate", SECURITY_FAIL="yes").returncode, 0
        )
        self.assertNotEqual(
            self.run_step("store notarytool credentials", NOTARY_MODE="credentials").returncode, 0
        )

    def test_identity_signing_and_strict_verification_are_mandatory(self):
        self.assert_ok(self.run_step("codesign"))
        self.assertEqual(len(self.calls("codesign")), 2)
        for mode, count in (("missing-identity", 0), ("sign", 1), ("verify", 2)):
            with self.subTest(mode=mode):
                self.log.unlink()
                self.assertNotEqual(self.run_step("codesign", SIGN_MODE=mode).returncode, 0)
                self.assertEqual(len(self.calls("codesign")), count)
                self.assertEqual(self.calls("ditto"), [])

    def test_both_accepted_submissions_precede_staple_and_output_publication(self):
        self.assert_ok(self.run_step("package, notarize & staple"))
        calls = self.calls("xcrun")
        self.assertEqual([call[:2] for call in calls], [
            ["notarytool", "submit"], ["notarytool", "submit"], ["stapler", "staple"],
        ])
        self.assertEqual([calls[0][2], calls[1][2]],
                         [self.env["ZIP_PATH"], self.env["DMG_PATH"]])
        self.assertEqual(self.env_file.read_text().splitlines(), [
            "ZIP_PATH=" + self.env["ZIP_PATH"], "DMG_PATH=" + self.env["DMG_PATH"],
        ])

    def test_notary_exit_status_and_accepted_json_and_stapling_are_all_required(self):
        for mode in (
            "transport", "accepted-nonzero", "invalid", "malformed", "missing-status",
            "second-transport", "second-accepted-nonzero", "second-invalid",
            "second-malformed", "second-missing-status", "staple",
        ):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                self.assertNotEqual(
                    self.run_step("package, notarize & staple", NOTARY_MODE=mode).returncode, 0
                )
                submissions = [call for call in self.calls("xcrun")
                               if call[:2] == ["notarytool", "submit"]]
                self.assertEqual(len(submissions), 2 if mode.startswith("second-")
                                 or mode == "staple" else 1)
                staples = [call for call in self.calls("xcrun")
                           if call[:2] == ["stapler", "staple"]]
                self.assertEqual(len(staples), int(mode == "staple"))
                self.assertEqual(self.env_file.read_text(), "")

    def test_packaging_failure_blocks_notarization(self):
        for tool in ("ditto", "hdiutil"):
            with self.subTest(tool=tool):
                self.log.unlink(missing_ok=True)
                self.assertNotEqual(
                    self.run_step("package, notarize & staple", PACKAGE_MODE=tool).returncode, 0
                )
                self.assertEqual(self.calls("xcrun"), [])
                self.assertEqual(self.env_file.read_text(), "")

    def test_actual_early_and_final_helper_commands_propagate_failure(self):
        for name in ("validate source and publication availability", "create GitHub Release"):
            with self.subTest(name=name):
                self.assert_ok(self.run_step(name))
                self.assertNotEqual(self.run_step(name, RELEASE_EXIT="82").returncode, 0)


if __name__ == "__main__":
    unittest.main()
