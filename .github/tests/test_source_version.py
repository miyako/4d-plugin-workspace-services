import importlib.util
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("source_version", ROOT / ".github/scripts/source_version.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".source-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.copy_source()
        self.current = source.read(self.root)

    def copy_source(self):
        for name in source.SOURCE_PATHS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)

    def snapshot(self):
        return {name: ((self.root / name).read_bytes(),
                       stat.S_IMODE((self.root / name).stat().st_mode))
                for name in source.SOURCE_PATHS if (self.root / name).exists()}

    def assert_rejected(self, error=ValueError):
        before = self.snapshot()
        with patch.object(Path, "write_bytes") as write:
            with self.assertRaises(error):
                source.read(self.root)
            with self.assertRaises(error):
                source.bump("patch", self.root)
            write.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def plist(self, **values):
        path = self.root / source.PLIST
        fields = plistlib.loads(path.read_bytes())
        fields.update(values)
        path.write_bytes(plistlib.dumps(fields))

    def set_setting(self, key, value, count=None):
        path = self.root / source.PROJECT
        project = source.text(path)
        spans = [span for name, _, span in source.project_settings(project) if name == key]
        if count is not None:
            spans = spans[:count]
        path.write_text(source._replace(project, spans, value))

    def fixture(self, version="3.2.1"):
        project = self.root / source.PROJECT
        project.write_text("{ configurations = {\n" + "".join(
            f'C{i} = {{ MARKETING_VERSION = {version}; CURRENT_PROJECT_VERSION = {version}; }};\n'
            for i in range(source.SETTING_COUNT)
        ) + "}; }\n")
        (self.root / source.PLIST).write_bytes(plistlib.dumps({
            "CFBundleName": "Workspace Services",
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
        }))
        (self.root / source.LOCALIZED).write_text(
            f'CFBundleName = "Workspace Services";\nCFBundleShortVersionString = "{version}";\n'
            f'CFBundleGetInfoString = "{source.INFO_PREFIX}{version}{source.INFO_SUFFIX}";\n'
        )

    def assert_literal_bump(self, before, old, new, encoding="utf-8"):
        for name, (original, mode) in before.items():
            path = self.root / name
            self.assertEqual(path.read_bytes(), original.replace(old.encode(encoding),
                                                                new.encode(encoding)))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
        self.assertEqual(source.read(self.root), new)

    def test_live_version_paths_and_no_intake_bump(self):
        self.assertRegex(self.current, "^" + source.VERSION + "$")
        self.assertEqual(source.SETTING_COUNT, 6)
        self.assertEqual(source.SOURCE_PATHS, (
            Path("Workspace Services.xcodeproj/project.pbxproj"),
            Path("Info.plist"), Path("English.lproj/InfoPlist.strings"),
        ))
        self.assertEqual(source.source_files(self.root),
                         tuple(self.root / path for path in source.SOURCE_PATHS))

    def test_all_bump_modes(self):
        for mode, expected in (("patch", "3.2.2"), ("minor", "3.3.0"), ("major", "4.0.0")):
            with self.subTest(mode=mode):
                self.fixture()
                before = self.snapshot()
                self.assertEqual(source.bump(mode, self.root), expected)
                self.assert_literal_bump(before, "3.2.1", expected)

    def test_zero_and_large_canonical_components(self):
        for version in ("0.0.0", "99999999999999999999.0.99999999999999999999"):
            self.fixture(version)
            self.assertEqual(source.read(self.root), version)
            parts = version.split(".")
            expected = ".".join(parts[:2] + [str(int(parts[2]) + 1)])
            self.assertEqual(source.bump("patch", self.root), expected)

    def test_coordinated_policy_is_not_inferred_from_equal_intake_values(self):
        self.fixture()
        self.set_setting("CURRENT_PROJECT_VERSION", "14.3")
        self.assert_rejected()
        self.fixture()
        self.plist(CFBundleVersion="77")
        self.assert_rejected()

    def test_missing_short_and_both_missing_reject_read_and_bump_without_writes(self):
        for keep_build in (True, False):
            self.fixture()
            path = self.root / source.PLIST
            fields = plistlib.loads(path.read_bytes())
            del fields["CFBundleShortVersionString"]
            if not keep_build:
                del fields["CFBundleVersion"]
            path.write_bytes(plistlib.dumps(fields))
            self.assert_rejected()

    def test_optional_build_absence_retained(self):
        self.assertNotIn("CFBundleVersion", plistlib.loads((self.root / source.PLIST).read_bytes()))
        before = self.snapshot()
        parts = list(map(int, self.current.split(".")))
        parts[2] += 1
        expected = ".".join(map(str, parts))
        self.assertEqual(source.bump("patch", self.root), expected)
        self.assertNotIn("CFBundleVersion", plistlib.loads((self.root / source.PLIST).read_bytes()))
        self.assert_literal_bump(before, self.current, expected)

    def test_invalid_project_versions(self):
        for key in source.KEYS:
            for value in ("", "1", "14.3", "01.2.3", "1.02.3", "1.2.03", "-1.2.3",
                          "v1.2.3", "1.2.3.4", "1.2.3-beta", "1.2.3+build",
                          "$(UNKNOWN)", "${UNKNOWN}", "$(PRODUCT_NAME)"):
                with self.subTest(key=key, value=value):
                    self.fixture()
                    self.set_setting(key, value)
                    self.assert_rejected()

    def test_configuration_drift_rejected(self):
        for key in source.KEYS:
            for count in (1, 5, 6):
                self.fixture()
                self.set_setting(key, "3.2.2", count=count)
                self.assert_rejected()

    def test_missing_extra_and_malformed_settings(self):
        for key in source.KEYS:
            for extra in (f"{key} = ;", f"{key} = 3.2.1",
                          f"{key} nonsense;", f"{key} = 3.2.1 extra;"):
                self.fixture()
                path = self.root / source.PROJECT
                path.write_bytes(path.read_bytes() + ("\n" + extra).encode())
                self.assert_rejected()
            self.fixture()
            path = self.root / source.PROJECT
            original = path.read_text()
            path.write_text(original.replace(f"{key} = 3.2.1;", "", 1))
            self.assert_rejected()

    def test_inline_quoted_and_unquoted_project_duplicates_any_assignment(self):
        for key in source.KEYS:
            for quoted_key in (key, f'"{key}"'):
                for value in ("3.2.1", '"3.2.1"', "9.8.7", "$(UNKNOWN)", '"${UNKNOWN}"'):
                    for location in ("version", "other", "scope"):
                        with self.subTest(key=quoted_key, value=value, location=location):
                            self.fixture()
                            path = self.root / source.PROJECT
                            original = path.read_text()
                            duplicate = f"{quoted_key} = {value};"
                            if location == "version":
                                existing = f"{key} = 3.2.1;"
                                mutated = original.replace(existing, existing + " " + duplicate, 1)
                            elif location == "other":
                                mutated = original + f'\nOTHER = "unchanged"; {duplicate}\n'
                            else:
                                mutated = original + f"\nNEW = {{ {duplicate} }};\n"
                            path.write_text(mutated)
                            self.assert_rejected()

    def test_duplicate_in_one_configuration_cannot_replace_missing_configuration(self):
        self.fixture()
        path = self.root / source.PROJECT
        value = path.read_text().replace("MARKETING_VERSION = 3.2.1;", "", 1)
        value = value.replace("MARKETING_VERSION = 3.2.1;",
                              'MARKETING_VERSION = 3.2.1; "MARKETING_VERSION" = 3.2.1;', 1)
        path.write_text(value)
        self.assert_rejected()

    def test_project_quoted_keys_values_inline_and_comments_supported(self):
        self.fixture()
        path = self.root / source.PROJECT
        original = path.read_text()
        for key in source.KEYS:
            original = original.replace(f"{key} = 3.2.1;",
                                        f'"{key}" /* gap */ = /* value */ "3.2.1" \t;')
        path.write_text(original)
        before = self.snapshot()
        self.assertEqual(source.bump("patch", self.root), "3.2.2")
        self.assert_literal_bump(before, "3.2.1", "3.2.2")

    def test_project_comment_and_string_noise_preserved_byte_for_byte(self):
        self.fixture()
        path = self.root / source.PROJECT
        noise = (
            '\n/*\rMARKETING_VERSION = 3.2.1;\n"CURRENT_PROJECT_VERSION" = 3.2.1;\r\n*/'
            '\n// MARKETING_VERSION = 3.2.1; CURRENT_PROJECT_VERSION = 3.2.1;\r'
            'OTHER = "MARKETING_VERSION = 3.2.1; \\"CURRENT_PROJECT_VERSION\\" = 3.2.1;";\n'
            'MARKETING_VERSION_SUFFIX = 3.2.1; PREFIX_CURRENT_PROJECT_VERSION = 3.2.1;\n'
        )
        path.write_bytes(path.read_bytes() + noise.encode())
        before = path.read_bytes()
        self.plist(UnrelatedVersion="3.2.1")
        source.bump("patch", self.root)
        self.assertTrue(path.read_bytes().endswith(noise.encode()))
        self.assertEqual(path.read_bytes()[:-len(noise)],
                         before[:-len(noise)].replace(b"3.2.1", b"3.2.2"))
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())[
            "UnrelatedVersion"], "3.2.1")

    def test_known_references_resolve_and_remain_exactly_spelled(self):
        for reference in source.REFERENCES:
            for marketing_reference in ("$(MARKETING_VERSION)", "${MARKETING_VERSION}"):
                self.fixture()
                self.set_setting("CURRENT_PROJECT_VERSION", f'"{marketing_reference}"')
                self.plist(CFBundleShortVersionString=reference, CFBundleVersion=reference)
                before = self.snapshot()
                self.assertEqual(source.bump("patch", self.root), "3.2.2")
                self.assert_literal_bump(before, "3.2.1", "3.2.2")

    def test_reverse_reference_chain_and_unquoted_references(self):
        for reference in ("$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}"):
            self.fixture()
            self.set_setting("MARKETING_VERSION", reference)
            self.plist(CFBundleShortVersionString="${MARKETING_VERSION}",
                       CFBundleVersion="$(CURRENT_PROJECT_VERSION)")
            before = self.snapshot()
            source.bump("minor", self.root)
            self.assert_literal_bump(before, "3.2.1", "3.3.0")

    def test_cyclic_and_unresolved_references_fail_before_writes(self):
        for key in source.KEYS:
            for reference in (f"$({key})", f"${{{key}}}"):
                self.fixture()
                self.set_setting(key, f'"{reference}"')
                self.assert_rejected()
        self.fixture()
        self.set_setting("MARKETING_VERSION", '"$(CURRENT_PROJECT_VERSION)"')
        self.set_setting("CURRENT_PROJECT_VERSION", '"${MARKETING_VERSION}"')
        self.assert_rejected()

    def test_reference_does_not_hide_configuration_drift(self):
        self.fixture()
        self.set_setting("CURRENT_PROJECT_VERSION", '"$(MARKETING_VERSION)"')
        self.set_setting("MARKETING_VERSION", "3.2.2", count=1)
        self.plist(CFBundleShortVersionString="${CURRENT_PROJECT_VERSION}")
        self.assert_rejected()

    def test_invalid_plist_versions_and_drift(self):
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            for value in ("", "1", "14.3", "01.2.3", "v1.2.3", "3.2.2", "1.2.3-beta",
                          "1.2.3.4", "$(UNKNOWN)", "${UNKNOWN}", "$(PRODUCT_NAME)",
                          123, True, [], {}):
                self.fixture()
                self.plist(**{key: value})
                self.assert_rejected()

    def test_duplicate_plist_keys_and_invalid_serialization(self):
        for key in ("CFBundleShortVersionString", "CFBundleVersion", "CFBundleName"):
            self.fixture()
            path = self.root / source.PLIST
            value = path.read_text().replace("</dict>", f"<key>{key}</key><string>3.2.1</string></dict>")
            path.write_text(value)
            self.assert_rejected()
        for value in (b"", b"not a plist", b"<plist><dict>", plistlib.dumps([]),
                      plistlib.dumps({"CFBundleShortVersionString": "3.2.1"},
                                     fmt=plistlib.FMT_BINARY)):
            self.fixture()
            (self.root / source.PLIST).write_bytes(value)
            self.assert_rejected()

    def test_xml_entities_and_non_string_versions_fail_closed(self):
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            self.fixture()
            path = self.root / source.PLIST
            value = path.read_text()
            value = value.replace(f"<key>{key}</key>\n\t<string>3.2.1</string>",
                                  f"<key>{key}</key>\n\t<string>&#51;.2.1</string>")
            path.write_text(value)
            self.assert_rejected()

    def test_xml_comment_noise_and_unrelated_literal_preserved(self):
        self.fixture()
        path = self.root / source.PLIST
        value = path.read_text().replace("</dict>",
            '<!-- <key>CFBundleVersion</key><string>3.2.1</string> -->\n'
            '<key>Other</key><string>3.2.1</string>\n</dict>')
        path.write_text(value)
        source.bump("patch", self.root)
        self.assertIn('<!-- <key>CFBundleVersion</key><string>3.2.1</string> -->', path.read_text())
        self.assertEqual(plistlib.loads(path.read_bytes())["Other"], "3.2.1")

    def test_localization_missing_drift_invalid_and_duplicate(self):
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            for value in ("", "invalid", "01.2.3", "$(UNKNOWN)", "$(MARKETING_VERSION)", "3.2.2"):
                self.fixture()
                path = self.root / source.LOCALIZED
                text = source.text(path)
                _, spans = source._localized(text)
                path.write_text(source._replace(text, [spans[key]], value))
                self.assert_rejected()
            self.fixture()
            path = self.root / source.LOCALIZED
            path.write_text(path.read_text().replace(key, "OtherKey"))
            self.assert_rejected()

    def test_localized_inline_duplicates_quoted_and_unquoted_after_any_assignment(self):
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            for name in (key, f'"{key}"'):
                for value in ('"3.2.1"', '"bad"', "3.2.1"):
                    self.fixture()
                    path = self.root / source.LOCALIZED
                    path.write_bytes(path.read_bytes() + f'OTHER = "same"; {name} = {value};'.encode())
                    self.assert_rejected()

    def test_localized_quotes_inline_unquoted_short_and_noise(self):
        self.fixture()
        path = self.root / source.LOCALIZED
        value = path.read_text()
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            value = value.replace(key + " =", f'"{key}" =')
        value = value.replace('"3.2.1";', "3.2.1;").replace("\n", " ")
        noise = ('\r/* CFBundleShortVersionString = "3.2.1"; */'
                 '\n// "CFBundleGetInfoString" = "3.2.1";\r'
                 'OTHER = "CFBundleShortVersionString = \\"3.2.1\\";";\r')
        path.write_bytes((value + noise).encode())
        source.bump("patch", self.root)
        self.assertEqual(path.read_bytes(), (value.replace("3.2.1", "3.2.2") + noise).encode())

    def test_localization_product_and_copyright_are_not_blindly_rewritten(self):
        for old, new in (("Workspace Services", "Other Product"),
                         ("Copyright 2024", "Copyright 2025"), ("miyako.", "someone.")):
            self.fixture()
            path = self.root / source.LOCALIZED
            path.write_bytes(path.read_bytes().replace(old.encode(), new.encode()))
            self.assert_rejected()

    def test_unterminated_strings_comments_and_malformed_localizations(self):
        for path in (source.PROJECT, source.LOCALIZED):
            for suffix in ('\n/* unterminated', '\nOTHER = "unterminated', "\nOTHER = ;"):
                self.fixture()
                target = self.root / path
                target.write_bytes(target.read_bytes() + suffix.encode())
                if path == source.PROJECT and suffix == "\nOTHER = ;":
                    continue
                self.assert_rejected()

    def test_missing_source_files_fail_before_all_writes(self):
        for name in source.SOURCE_PATHS:
            self.copy_source()
            (self.root / name).unlink()
            self.assert_rejected(FileNotFoundError)

    def test_encoding_endianness_bom_mixed_endings_modes_and_unrelated_bytes(self):
        for encoding, bom in (("utf-8", b""), ("utf-8", b"\xef\xbb\xbf"),
                              ("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff")):
            for ending in ("\n", "\r", "\r\n", "mixed"):
                with self.subTest(encoding=encoding, ending=ending):
                    self.fixture()
                    for index, name in enumerate(source.SOURCE_PATHS):
                        path = self.root / name
                        lines = source.text(path).splitlines()
                        value = "".join(line + (("\r", "\r\n", "\n")[i % 3]
                                                if ending == "mixed" else ending)
                                        for i, line in enumerate(lines))
                        path.write_bytes(bom + value.encode(encoding))
                        path.chmod((0o755, 0o640, 0o644)[index])
                    before = self.snapshot()
                    source.bump("minor", self.root)
                    self.assert_literal_bump(before, "3.2.1", "3.3.0", encoding)

    def test_mixed_encodings_across_source_files(self):
        self.fixture()
        encodings = ("utf-8-sig", "utf-16-le", "utf-16-be")
        boms = (b"", b"\xff\xfe", b"\xfe\xff")
        for name, encoding, bom in zip(source.SOURCE_PATHS, encodings, boms):
            path = self.root / name
            path.write_bytes(bom + source.text(path).encode(encoding))
        before = self.snapshot()
        self.assertEqual(source.bump("major", self.root), "4.0.0")
        for name, encoding in zip(source.SOURCE_PATHS, encodings):
            encoding = "utf-8" if encoding == "utf-8-sig" else encoding
            self.assertEqual((self.root / name).read_bytes(),
                             before[name][0].replace("3.2.1".encode(encoding), "4.0.0".encode(encoding)))

    def test_invalid_encoding_fails_before_all_writes(self):
        for name in source.SOURCE_PATHS:
            self.fixture()
            path = self.root / name
            path.write_bytes(path.read_bytes() + b"\xff")
            self.assert_rejected(UnicodeError)

    def test_prebuilt_destinations_and_other_files_are_untouched(self):
        excluded = (
            "Workspace Services.4dbase/Plugins/Workspace Services.bundle/Contents/Info.plist",
            "Workspace Services.4dbase/Plugins/Workspace Services.bundle/Contents/Resources/English.lproj/InfoPlist.strings",
            "manifest.json", "constants.xlf", "English.lproj/locversion.plist",
            "Workspace Services.vcxproj", "4DPlugin.cpp", "4D Plugin API/4DPluginAPI.h",
        )
        for index, name in enumerate(excluded):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"untouched metadata 1.4.2 / 1.4.7\n")
            path.chmod(0o640 if index % 2 else 0o755)
        before = {name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
                  for name in excluded}
        source.bump("major", self.root)
        self.assertEqual(before, {name: ((self.root / name).read_bytes(),
                                         (self.root / name).stat().st_mode) for name in excluded})

    def test_exact_intake_repair_preserves_unrelated_bytes_and_modes(self):
        baseline = "44a5101cf089f3eb6f63f3b77a93486a8169f164"
        for name in source.SOURCE_PATHS:
            original = subprocess.run(["git", "show", f"{baseline}:{name}"], cwd=ROOT,
                                      capture_output=True, check=True).stdout
            expected = original
            version = self.current.encode()
            if name == source.PROJECT:
                self.assertEqual(original.count(b"CURRENT_PROJECT_VERSION = 1.4.2;"), 6)
                expected = original.replace(b"CURRENT_PROJECT_VERSION = 1.4.2;",
                                            b"CURRENT_PROJECT_VERSION = " + version + b";")
                expected = expected.replace(b"MARKETING_VERSION = 1.4.7;",
                                            b"MARKETING_VERSION = " + version + b";")
            elif name == source.LOCALIZED:
                self.assertEqual(original.count(b"1.4.2"), 2)
                expected = original.replace(b"1.4.2", version)
            else:
                expected = original.replace(b"<string>1.4.7</string>",
                                            b"<string>" + version + b"</string>")
            self.assertEqual((ROOT / name).read_bytes(), expected)
            tree = subprocess.run(["git", "ls-tree", baseline, "--", str(name)], cwd=ROOT,
                                  capture_output=True, check=True, text=True).stdout
            self.assertEqual(stat.S_IMODE((ROOT / name).stat().st_mode),
                             int(tree.split()[0], 8) & 0o777)

    def test_cli_and_invalid_modes_do_not_write(self):
        before = self.snapshot()
        for mode in ("", "other", None):
            with self.assertRaises(ValueError):
                source.bump(mode, self.root)
        output = subprocess.run([sys.executable, str(ROOT / ".github/scripts/source_version.py")],
                                cwd=self.root, check=True, capture_output=True, text=True)
        self.assertEqual(output.stdout.strip(), self.current)
        self.assertEqual(before, self.snapshot())

    def test_compatible_root_first_and_prng_mode_first_api(self):
        self.fixture()
        self.assertEqual(source.bump(self.root, "patch"), "3.2.2")
        self.assertEqual(source.bump("minor", self.root), "3.3.0")
        self.assertEqual(source.bump(mode="major", root=self.root), "4.0.0")

    def bundle(self):
        contents = self.root / "built.bundle/Contents"
        localized = contents / "Resources" / source.LOCALIZED
        localized.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.root / source.LOCALIZED, localized)
        shutil.copy2(self.root / source.PLIST, contents / "Info.plist")
        return contents, localized

    def test_verify_bundle_optional_build_key_and_invalid_root(self):
        contents, _ = self.bundle()
        source.verify_bundle(contents.parent, self.root)
        path = contents / "Info.plist"
        for value in ([], {"CFBundleShortVersionString": "bad"},
                      {"CFBundleShortVersionString": self.current, "CFBundleVersion": "77"}):
            path.write_bytes(plistlib.dumps(value))
            with self.assertRaises(ValueError):
                source.verify_bundle(contents.parent, self.root)
        self.plist(CFBundleVersion=self.current)
        path.write_bytes(plistlib.dumps({"CFBundleShortVersionString": self.current}))
        with self.assertRaisesRegex(ValueError, "build version"):
            source.verify_bundle(contents.parent, self.root)

    def test_built_localized_utf16_xml_binary_and_drift(self):
        contents, localized = self.bundle()
        value = source.text(localized)
        for encoding, bom in (("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff"),
                              ("utf-8-sig", b"")):
            localized.write_bytes(bom + value.encode(encoding))
            source.verify_bundle(contents.parent, self.root)
        fields = {"CFBundleShortVersionString": self.current,
                  "CFBundleGetInfoString": source.INFO_PREFIX + self.current + source.INFO_SUFFIX}
        for fmt in (plistlib.FMT_XML, plistlib.FMT_BINARY):
            localized.write_bytes(plistlib.dumps(fields, fmt=fmt))
            source.verify_bundle(contents.parent, self.root)
        xml = plistlib.dumps(fields).decode().replace('encoding="UTF-8"', 'encoding="UTF-16"')
        for encoding, bom in (("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff")):
            localized.write_bytes(bom + xml.encode(encoding))
            source.verify_bundle(contents.parent, self.root)
        localized.write_bytes(value.replace(self.current, "9.9.9").encode("utf-16"))
        with self.assertRaises(ValueError):
            source.verify_bundle(contents.parent, self.root)

    def test_built_plist_references_resolve_to_selected_source_not_literal_text(self):
        self.fixture()
        self.set_setting("CURRENT_PROJECT_VERSION", '"${MARKETING_VERSION}"')
        self.plist(CFBundleShortVersionString="$(CURRENT_PROJECT_VERSION)",
                   CFBundleVersion="${MARKETING_VERSION}")
        contents, _ = self.bundle()
        fields = {"CFBundleShortVersionString": "3.2.1", "CFBundleVersion": "3.2.1"}
        path = contents / "Info.plist"
        for fmt in (plistlib.FMT_XML, plistlib.FMT_BINARY):
            path.write_bytes(plistlib.dumps(fields, fmt=fmt))
            source.verify_bundle(contents.parent, self.root)
        xml = plistlib.dumps(fields).decode().replace('encoding="UTF-8"', 'encoding="UTF-16"')
        for encoding, bom in (("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff")):
            path.write_bytes(bom + xml.encode(encoding))
            source.verify_bundle(contents.parent, self.root)
        path.write_bytes((self.root / source.PLIST).read_bytes())
        with self.assertRaisesRegex(ValueError, "display version"):
            source.verify_bundle(contents.parent, self.root)


if __name__ == "__main__":
    unittest.main()
