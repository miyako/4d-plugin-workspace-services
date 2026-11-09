"""Validate and bump authoritative source versions, never prebuilt destinations.

The coordinated policy is established by the header of bump-version.yml at
e35b968f6d8392f6f3b9f964ccfdb37aa653c611, not its marketing-only shell body.
"""

import argparse
from pathlib import Path
import plistlib
import re
from xml.parsers.expat import ExpatError


PROJECT = Path("Workspace Services.xcodeproj/project.pbxproj")
PLIST = Path("Info.plist")
LOCALIZED = Path("English.lproj/InfoPlist.strings")
SOURCE_PATHS = (PROJECT, PLIST, LOCALIZED)
KEYS = ("MARKETING_VERSION", "CURRENT_PROJECT_VERSION")
SETTING_COUNT = 6
VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
REFERENCES = {f"$({key})": key for key in KEYS}
REFERENCES.update({f"${{{key}}}": key for key in KEYS})
INFO_PREFIX = "Workspace Services version "
INFO_SUFFIX = ", Copyright 2024 miyako."
TOKEN = re.compile(
    r'(?P<space>\s+)|(?P<comment>/\*.*?\*/|//[^\r\n]*)|'
    r'(?P<quoted>"(?:\\.|[^"\\])*")|'
    r'(?P<reference>\$\([^()\s]*\)|\$\{[^{}\s]*\})|'
    r'(?P<word>[^\s"=;{}(),/]+)|(?P<symbol>[^\s])',
    re.DOTALL,
)
PLIST_VERSION = re.compile(
    r"<key>\s*(CFBundleShortVersionString|CFBundleVersion)\s*</key>"
    r"\s*<string>([^<]*)</string>"
)


class UniqueDictionary(dict):
    def __setitem__(self, key, value):
        if key in self:
            raise ValueError(f"Duplicate source plist key: {key}")
        super().__setitem__(key, value)


def unquote(value):
    return value[1:-1] if value.startswith('"') and value.endswith('"') else value


def _decode(data):
    for bom, encoding in (
        (b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"),
        (b"\xfe\xff", "utf-16-be"),
    ):
        if data.startswith(bom):
            return data[len(bom):].decode(encoding), bom, encoding
    return data.decode("utf-8"), b"", "utf-8"


def text(path):
    return _decode(Path(path).read_bytes())[0]


def rendered(path, transform):
    value, bom, encoding = _decode(Path(path).read_bytes())
    return bom + transform(value).encode(encoding)


def _tokens(value):
    tokens = []
    for match in TOKEN.finditer(value):
        if match.lastgroup in ("space", "comment"):
            continue
        if match[0] == '"' or match[0] == "/*":
            raise ValueError("Unterminated source string or comment")
        # A failed block-comment match must not become two ordinary symbols.
        if match[0] == "/" and value.startswith("/*", match.start()):
            raise ValueError("Unterminated source comment")
        tokens.append(match)
    return tokens


def _value(token):
    value = unquote(token[0])
    if "\\" in value:
        raise ValueError("Escaped authoritative metadata is unsupported")
    return value


def _span(token):
    quoted = token.lastgroup == "quoted"
    return token.start() + quoted, token.end() - quoted


def project_settings(project):
    """Return lexical (key, value, value-span) assignments across configurations."""
    tokens = _tokens(project)
    settings = []
    scopes = [set()]
    for index, token in enumerate(tokens):
        if token[0] == "{":
            scopes.append(set())
        elif token[0] == "}":
            if len(scopes) == 1:
                raise ValueError("Unbalanced project dictionary")
            scopes.pop()
        key = unquote(token[0])
        if key not in KEYS:
            continue
        following = tokens[index + 1:index + 4]
        if not following or following[0][0] != "=":
            if index == 0 or tokens[index - 1][0] in (";", "{", "}"):
                raise ValueError(f"Malformed source assignment: {key}")
            continue
        if (len(following) != 3 or following[2][0] != ";"
                or following[1].lastgroup not in ("word", "quoted", "reference")):
            raise ValueError(f"Malformed source value: {key}")
        if key in scopes[-1]:
            raise ValueError(f"Duplicate source setting in one dictionary: {key}")
        scopes[-1].add(key)
        settings.append((key, _value(following[1]), _span(following[1])))
    if len(scopes) != 1:
        raise ValueError("Unbalanced project dictionary")
    for key in KEYS:
        if sum(item[0] == key for item in settings) != SETTING_COUNT:
            raise ValueError(f"Expected {SETTING_COUNT} source assignments for {key}")
    return settings


def _localized(value):
    tokens = _tokens(value)
    fields = UniqueDictionary()
    spans = {}
    if len(tokens) % 4:
        raise ValueError("Malformed source localization")
    for offset in range(0, len(tokens), 4):
        key, equals, item, semi = tokens[offset:offset + 4]
        if (equals[0] != "=" or semi[0] != ";"
                or key.lastgroup not in ("word", "quoted")
                or item.lastgroup not in ("word", "quoted", "reference")):
            raise ValueError("Malformed source localization assignment")
        name = unquote(key[0])
        fields[name] = unquote(item[0])
        spans[name] = _span(item)
    return fields, spans


def _plist(value):
    # Validate decoded XML independently of its original byte-order declaration.
    xml = re.sub(r'(<\?xml\b[^>]*\bencoding\s*=\s*["\'])[^"\']+',
                 r"\g<1>UTF-8", value, count=1)
    try:
        fields = plistlib.loads(xml.encode("utf-8"), dict_type=UniqueDictionary)
    except (plistlib.InvalidFileException, ExpatError, UnicodeError) as error:
        raise ValueError("Invalid source Info.plist XML") from error
    if not isinstance(fields, dict):
        raise ValueError("Source Info.plist must be a dictionary")
    if "CFBundleShortVersionString" not in fields:
        raise ValueError("Required CFBundleShortVersionString is missing")
    masked = re.sub(r"<!--.*?-->", lambda m: " " * len(m[0]), value, flags=re.DOTALL)
    serialized = list(PLIST_VERSION.finditer(masked))
    spans = {}
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        if key not in fields:
            continue
        matches = [match for match in serialized if match[1] == key]
        if (not isinstance(fields[key], str) or len(matches) != 1
                or matches[0][2] != fields[key]):
            raise ValueError(f"{key} must have one editable, literal XML string")
        spans[key] = matches[0].span(2)
    return fields, spans


def _resolve(settings):
    fields = {key: [value for name, value, _ in settings if name == key] for key in KEYS}
    resolved = {}

    def resolve(key, chain=()):
        if key in chain:
            raise ValueError("Cyclic source version reference")
        if key in resolved:
            return resolved[key]
        versions = set()
        for value in fields[key]:
            actual = resolve(REFERENCES[value], chain + (key,)) if value in REFERENCES else value
            if not re.fullmatch(VERSION, actual):
                raise ValueError(f"{key} must resolve to canonical X.Y.Z")
            versions.add(actual)
        if len(versions) != 1:
            raise ValueError(f"{key} configuration values have drifted")
        resolved[key] = versions.pop()
        return resolved[key]

    for key in KEYS:
        resolve(key)
    if len(set(resolved.values())) != 1:
        raise ValueError("Coordinated source settings have drifted")
    return resolved


def _inspect(documents):
    settings = project_settings(documents[PROJECT])
    resolved = _resolve(settings)
    version = resolved["MARKETING_VERSION"]
    fields, plist_spans = _plist(documents[PLIST])
    for key in plist_spans:
        value = fields[key]
        if resolved.get(REFERENCES.get(value), value) != version:
            raise ValueError(f"{key} is invalid, unresolved or has drifted")
    localized, localized_spans = _localized(documents[LOCALIZED])
    expected = {
        "CFBundleShortVersionString": version,
        "CFBundleGetInfoString": INFO_PREFIX + version + INFO_SUFFIX,
    }
    if any(localized.get(key) != value for key, value in expected.items()):
        raise ValueError("Copied source localization is missing, invalid or has drifted")
    edits = {path: [] for path in SOURCE_PATHS}
    edits[PROJECT] = [span for _, value, span in settings if value not in REFERENCES]
    edits[PLIST] = [span for key, span in plist_spans.items() if fields[key] not in REFERENCES]
    edits[LOCALIZED].append(localized_spans["CFBundleShortVersionString"])
    start, end = localized_spans["CFBundleGetInfoString"]
    edits[LOCALIZED].append((start + len(INFO_PREFIX), end - len(INFO_SUFFIX)))
    return version, edits, fields, resolved


def _load(root):
    return {path: _decode((Path(root) / path).read_bytes()) for path in SOURCE_PATHS}


def read(root=Path(".")):
    return _inspect({path: item[0] for path, item in _load(root).items()})[0]


def _replace(value, spans, version):
    for start, end in sorted(spans, reverse=True):
        value = value[:start] + version + value[end:]
    return value


def bump(mode, root=Path(".")):
    """Bump source metadata; accepts PRNG's bump(mode, root) and bump(root, mode)."""
    if isinstance(root, str) and root in ("major", "minor", "patch") \
            and mode not in ("major", "minor", "patch"):
        mode, root = root, mode
    if mode not in ("major", "minor", "patch"):
        raise ValueError("Expected major, minor or patch")
    root = Path(root)
    loaded = _load(root)
    documents = {path: item[0] for path, item in loaded.items()}
    current, edits, _, _ = _inspect(documents)
    index = ("major", "minor", "patch").index(mode)
    parts = list(map(int, current.split(".")))
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    new = ".".join(map(str, parts))
    updated = {path: _replace(value, edits[path], new) for path, value in documents.items()}
    if _inspect(updated)[0] != new:
        raise ValueError("Bumped metadata did not validate")
    # Validate and encode every candidate before opening any source for writing.
    output = {path: loaded[path][1] + value.encode(loaded[path][2])
              for path, value in updated.items()}
    for path, data in output.items():
        if data != loaded[path][1] + documents[path].encode(loaded[path][2]):
            (root / path).write_bytes(data)
    return new


def source_files(root=Path(".")):
    return tuple(Path(root) / path for path in SOURCE_PATHS)


def verify_bundle(bundle, root=Path(".")):
    """Check built display metadata without changing a source or destination."""
    loaded = _load(root)
    version, _, source_plist, _ = _inspect(
        {path: item[0] for path, item in loaded.items()})
    contents = Path(bundle) / "Contents"
    fields = plistlib.loads((contents / "Info.plist").read_bytes(), dict_type=UniqueDictionary)
    if not isinstance(fields, dict) or fields.get("CFBundleShortVersionString") != version:
        raise ValueError("Built bundle display version differs from selected source")
    if ("CFBundleVersion" in source_plist or "CFBundleVersion" in fields) \
            and fields.get("CFBundleVersion") != version:
        raise ValueError("Built bundle build version differs from selected source")
    localized_path = contents / "Resources" / LOCALIZED
    data = localized_path.read_bytes()
    if data.startswith(b"bplist00") or _decode(data)[0].lstrip().startswith("<?xml"):
        localized = plistlib.loads(data, dict_type=UniqueDictionary)
    else:
        localized, _ = _localized(_decode(data)[0])
    if not isinstance(localized, dict) or (
        localized.get("CFBundleShortVersionString") != version
        or localized.get("CFBundleGetInfoString") != INFO_PREFIX + version + INFO_SUFFIX
    ):
        raise ValueError("Built localized display differs from selected source")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--bump", choices=("patch", "minor", "major"))
    operation.add_argument("--verify-bundle", type=Path)
    args = parser.parse_args()
    if args.verify_bundle:
        verify_bundle(args.verify_bundle)
    else:
        print(bump(args.bump) if args.bump else read())
