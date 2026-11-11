"""Preservation evidence is anchored to immutable intake, never mutable HEAD."""

import importlib.util
from pathlib import Path
import re
import stat
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
BASE = "44a5101cf089f3eb6f63f3b77a93486a8169f164"
PROJECT = "Workspace Services.xcodeproj/project.pbxproj"
PLIST = "Info.plist"
LOCALIZED = "English.lproj/InfoPlist.strings"
SOURCE_PATHS = (PROJECT, PLIST, LOCALIZED)
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location(
    "contract_source_version", ROOT / ".github/scripts/source_version.py"
)
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)


def original(path):
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{BASE}:{path}"])


def block(workflow, name):
    return workflow.split(f"      - name: {name}\n", 1)[1].split(
        "\n      - name:", 1
    )[0].rstrip()


class RepositoryContractTests(unittest.TestCase):
    def test_original_coordinated_header_and_actual_mac_only_topology(self):
        bump = original(".github/workflows/bump-version.yml").decode()
        header, body = bump.split("name: Bump version", 1)
        self.assertIn("MARKETING_VERSION/CURRENT_PROJECT_VERSION AND Info.plist", header)
        self.assertIn("CFBundleShortVersionString/CFBundleVersion", header)
        self.assertIn('KEY="MARKETING_VERSION"', body)
        self.assertIn('KEY="CURRENT_PROJECT_VERSION"', body)
        before = original(".github/workflows/release.yml").decode()
        self.assertIn("  push:\n    tags:\n      - 'v*.*.*'", before)
        self.assertEqual(re.findall(r"^  ([\w-]+):\n", before.split("\njobs:\n")[1],
                                    re.MULTILINE), ["version", "build-macos"])
        self.assertNotIn("runs-on: windows", before)

    def test_only_authorized_source_version_tokens_changed_byte_for_byte(self):
        version = source.read(ROOT)
        for path in SOURCE_PATHS:
            with self.subTest(path=path):
                before = original(path)
                if path == PROJECT:
                    expected = before.replace(
                        b"MARKETING_VERSION = 1.4.7;",
                        f"MARKETING_VERSION = {version};".encode(),
                    ).replace(
                        b"CURRENT_PROJECT_VERSION = 1.4.2;",
                        f"CURRENT_PROJECT_VERSION = {version};".encode(),
                    )
                elif path == PLIST:
                    expected = before.replace(b"<string>1.4.7</string>",
                                              f"<string>{version}</string>".encode())
                    self.assertNotIn(b"<key>CFBundleVersion</key>", before)
                else:
                    expected = before.replace(
                        b'CFBundleShortVersionString = "1.4.2";',
                        f'CFBundleShortVersionString = "{version}";'.encode(),
                    ).replace(
                        b"Workspace Services version 1.4.2, Copyright 2024 miyako.",
                        f"Workspace Services version {version}, Copyright 2024 miyako.".encode(),
                    )
                    self.assertIn(b"\r", before)
                    self.assertNotIn(b"\n", before)
                self.assertEqual((ROOT / path).read_bytes(), expected)
                mode = subprocess.check_output(
                    ["git", "-C", str(ROOT), "ls-tree", BASE, "--", path], text=True,
                ).split()[0]
                self.assertEqual(stat.S_IMODE((ROOT / path).stat().st_mode),
                                 0o755 if mode == "100755" else 0o644)

    def test_all_unrelated_intake_files_preserved(self):
        paths = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", BASE], text=True,
        ).splitlines()
        allowed = {*SOURCE_PATHS, "README.md", ".github/workflows/bump-version.yml",
                   ".github/workflows/release.yml"}
        # Ownership fixes have their own immutable baseline preservation test.
        from test_ownership import CHANGED_NATIVE
        allowed.update(CHANGED_NATIVE)
        for path in paths:
            if path not in allowed:
                with self.subTest(path=path):
                    self.assertEqual((ROOT / path).read_bytes(), original(path))

    def test_native_configuration_and_default_output_are_intake_evidence(self):
        before = original(PROJECT).decode()
        after = (ROOT / PROJECT).read_text()
        scrub = lambda text: re.sub(
            r"((?:MARKETING_VERSION|CURRENT_PROJECT_VERSION) = )[^;]+;",
            r"\1VERSION;", text,
        )
        self.assertEqual(scrub(after), scrub(before))
        configurations = re.findall(
            r"/\* (Default|Development|Deployment) \*/ = \{\n"
            r"\s*isa = XCBuildConfiguration;\n\s*buildSettings = \{(.*?)"
            r"\n\s*\};\n\s*name = \1;", before, re.DOTALL,
        )
        self.assertEqual(len(configurations), 6)
        defaults = [settings for name, settings in configurations if name == "Default"]
        self.assertEqual(len(defaults), 2)
        self.assertTrue(all("CONFIGURATION_BUILD_DIR" not in settings for settings in defaults))
        self.assertTrue(any(
            'SYMROOT = "$(SRCROOT)/$(PRODUCT_NAME).4dbase/Plugins";' in settings
            for settings in defaults
        ))
        self.assertTrue(all("OBJROOT" not in settings for settings in defaults))
        for resource in (
            "Cocoa.framework in Frameworks", "AppKit.framework", "CoreGraphics.framework",
            "InfoPlist.strings in Resources", "English.lproj/InfoPlist.strings",
            "manifest.json in CopyFiles", "constants.xlf in CopyFiles",
        ):
            self.assertIn(resource, before)
        self.assertEqual(before.count("MACOSX_DEPLOYMENT_TARGET = 10.13;"), 3)
        self.assertEqual(original("Workspace Services.vcxproj"),
                         (ROOT / "Workspace Services.vcxproj").read_bytes())

    def test_native_credentials_signing_outputs_and_release_defaults_preserved(self):
        before = original(".github/workflows/release.yml").decode()
        after = (ROOT / ".github/workflows/release.yml").read_text()
        for name in ("import Developer ID certificate", "store notarytool credentials"):
            self.assertEqual(block(before, name), block(after, name))
        self.assertEqual(
            re.findall(r"\$\{\{ secrets\.([A-Z_]+) \}\}", before),
            re.findall(r"\$\{\{ secrets\.([A-Z_]+) \}\}", after),
        )
        for required in (
            "PRODUCT_NAME: Workspace Services", "XCODE_PROJECT: Workspace Services.xcodeproj",
            "VCX_SOLUTION: Workspace Services.sln", "MACOS_DEPLOYMENT_TARGET: '11.0'",
            'ARCHS="arm64 x86_64"', "ONLY_ACTIVE_ARCH=NO", "-configuration Default",
            'MACOSX_DEPLOYMENT_TARGET="${{ env.MACOS_DEPLOYMENT_TARGET }}"',
            "codesign --verbose --deep --timestamp --force --options=runtime",
            'codesign --verify --deep --strict --verbose=2 "$BUNDLE_PATH"',
            'ditto -c -k --keepParent "$BUNDLE_PATH" "$ZIP_PATH"',
            'hdiutil create -format UDBZ -volname "${{ env.PRODUCT_NAME }}" '
            '-srcfolder "$BUNDLE_PATH" "$DMG_PATH"',
            'xcrun stapler staple "$DMG_PATH"',
            'ZIP_PATH="${{ env.PRODUCT_NAME }}-${VERSION}.zip"',
            'DMG_PATH="${{ env.PRODUCT_NAME }}-${VERSION}.dmg"',
        ):
            self.assertIn(required, before)
            self.assertIn(required, after)
        self.assertIn("tag_name: ${{ needs.version.outputs.tag }}", before)
        self.assertIn("name: ${{ needs.version.outputs.tag }}", before)
        self.assertNotRegex(before, r"(?m)^\s+(body|generate_release_notes):")

    def test_manual_immutable_independent_serial_workflow_and_fail_closed_order(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertRegex(workflow, r"(?m)^name: Build$")
        trigger = workflow.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(trigger.strip(), "workflow_dispatch:")
        self.assertIn("group: release-publication\n  cancel-in-progress: false", workflow)
        self.assertEqual(workflow.count("uses: actions/checkout@v4"), 2)
        self.assertEqual(workflow.count("ref: ${{ github.sha }}"), 2)
        self.assertEqual(re.findall(
            r"^  ([\w-]+):\n", workflow.split("\njobs:\n")[1], re.MULTILINE,
        ), ["version", "build-macos"])
        self.assertIn("needs: [version]", workflow)
        for forbidden in (
            "default_branch", "refs/heads/main", "workflow_run:", "workflow_call:",
            "always()", "continue-on-error:", "softprops/", "shell: cmd", "shell: pwsh",
        ):
            self.assertNotIn(forbidden, workflow)
        self.assertNotRegex(workflow, r"(?m)^\s+if:")
        self.assertIn('release.py preflight --sha "$SELECTED_SHA"',
                      block(workflow, "validate source and publication availability"))
        self.assertIn('release.py publish --sha "$SELECTED_SHA" "$ZIP_PATH" "$DMG_PATH"',
                      block(workflow, "create GitHub Release"))
        names = [
            "validate source and publication availability", "import Developer ID certificate",
            "store notarytool credentials", "build macOS plugin (universal)",
            "verify universal binary", "codesign", "package, notarize & staple",
            "create GitHub Release",
        ]
        positions = [workflow.index(f"- name: {name}\n") for name in names]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(workflow.index("--verify-bundle"), workflow.index("- name: codesign"))
        self.assertIn('CONFIGURATION_BUILD_DIR="$PWD/$PLUGINS_DIR"', workflow)
        self.assertIn("CODE_SIGNING_ALLOWED=NO", workflow)
        clean = block(workflow, "build macOS plugin (universal)")
        self.assertNotIn('/Default"', clean)
        self.assertNotIn('rm -rf "${BUNDLE_PATH}"', clean)
        self.assertNotIn('rm -rf "${PLUGINS_DIR}"', clean)
        self.assertNotIn("i386", block(workflow, "verify universal binary"))
        self.assertNotIn("*.dylib", block(workflow, "verify universal binary"))


if __name__ == "__main__":
    unittest.main()
