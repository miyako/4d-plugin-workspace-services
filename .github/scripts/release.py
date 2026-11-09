"""Fail-closed branch bumps and create-only publication; never repair partial state."""

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
from xml.parsers.expat import ExpatError

sys.dont_write_bytecode = True
from source_version import SOURCE_PATHS, bump, read

TRAILER = "Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"
GENERATED_PATHS = tuple(
    f"Workspace Services.4dbase/Plugins/Workspace Services.bundle/Contents/{output}"
    for output in (
        "MacOS/Workspace Services",
        "Info.plist",
        "Resources/English.lproj/InfoPlist.strings",
        "_CodeSignature/**",
    )
)


def run(*args, input=None, env=None):
    return subprocess.run(
        args, input=input, env=env, text=True, stdout=subprocess.PIPE, check=True
    ).stdout.strip()


def api(endpoint, payload=None, asset=None):
    command = ["gh", "api", "--method", "GET" if payload is None and asset is None else "POST", endpoint]
    if payload is not None:
        command += ["--input", "-"]
    if asset is not None:
        command += ["--header", "Content-Type: application/octet-stream", "--input", str(asset)]
    return json.loads(run(*command, input=json.dumps(payload) if payload is not None else None))


def selected_sha(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected immutable selected github.sha")
    if run("git", "rev-parse", "HEAD") != sha:
        raise ValueError("Checkout does not match selected github.sha")


def remote_ref(ref):
    output = run("git", "ls-remote", "--refs", "origin", ref)
    if not output:
        return None
    lines = output.splitlines()
    if len(lines) != 1:
        raise ValueError(f"Malformed remote ref response for {ref}")
    parts = lines[0].split()
    if len(parts) != 2 or parts[1] != ref or not re.fullmatch(r"[0-9a-f]{40}", parts[0]):
        raise ValueError(f"Malformed remote ref response for {ref}")
    return parts[0]


def available(repo, tag):
    # Listing releases requires authentication and includes drafts. A failed
    # authenticated request (including 404) is never treated as absence.
    run("gh", "auth", "status")
    if remote_ref(f"refs/tags/{tag}") is not None:
        raise ValueError(f"{tag} already exists remotely")
    page = 1
    while True:
        releases = api(f"repos/{repo}/releases?per_page=100&page={page}")
        if not isinstance(releases, list) or len(releases) > 100:
            raise ValueError("Malformed releases page")
        for release in releases:
            if (
                not isinstance(release, dict)
                or type(release.get("id")) is not int
                or release["id"] <= 0
                or not isinstance(release.get("tag_name"), str)
                or not release["tag_name"]
                or type(release.get("draft")) is not bool
                or type(release.get("prerelease")) is not bool
            ):
                raise ValueError("Malformed release entry")
            if release["tag_name"] == tag:
                raise ValueError(f"{tag} already has a draft or published release")
        if len(releases) < 100:
            break
        page += 1


def context(sha):
    selected_sha(sha)
    # Native builds legitimately dirty tracked output bundles. Everything
    # outside the exact generated product paths stays immutable.
    for options in ((), ("--cached",)):
        changed = run("git", "diff", *options, "--name-only", sha, "--", ".",
                      *(f":(exclude){path}" for path in GENERATED_PATHS))
        if changed:
            raise ValueError("Source/configuration differs from the selected commit")
    # Explicitly cover source paths even if a future source lives under output.
    for options in ((), ("--cached",)):
        if run("git", "diff", *options, "--name-only", sha, "--", *map(str, SOURCE_PATHS)):
            raise ValueError("Source version metadata differs from the selected commit")
    version = read()
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9_.-]+", repo
    ) or repo.split("/")[-1] in (".", ".."):
        raise ValueError("Invalid repository")
    return repo, version, f"v{version}"


def check(sha):
    repo, version, tag = context(sha)
    available(repo, tag)
    return version, tag


def preflight(sha):
    if run("git", "status", "--porcelain"):
        raise ValueError("Build preflight requires a clean source checkout")
    return check(sha)


def publish(sha, assets):
    repo, version, tag = context(sha)
    expected = [f"Workspace Services-{version}.zip", f"Workspace Services-{version}.dmg"]
    if [str(path) for path in assets] != expected:
        raise ValueError(f"Expected release assets: {expected}")
    for path in assets:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty release asset: {path}")
    # Repeat only after all native/sign/notary/staple gates; a POST race fails.
    available(repo, tag)
    ref = api(f"repos/{repo}/git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})
    if (
        not isinstance(ref, dict)
        or ref.get("ref") != f"refs/tags/{tag}"
        or not isinstance(ref.get("object"), dict)
        or ref["object"].get("sha") != sha
        or remote_ref(f"refs/tags/{tag}") != sha
    ):
        raise ValueError("New remote tag failed exact-SHA verification")
    print(f"Created remote tag {tag} at {sha}; retained if later steps fail", flush=True)
    release = api(f"repos/{repo}/releases", {
        "tag_name": tag, "target_commitish": sha, "name": tag,
        "draft": False, "prerelease": False, "body": "",
        "generate_release_notes": False,
    })
    if (
        not isinstance(release, dict)
        or type(release.get("id")) is not int
        or release["id"] <= 0
        or release.get("tag_name") != tag
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("Malformed create-release response; inspect retained remote state")
    release_id = release["id"]
    print(f"Created {tag}, release ID {release_id}; uploading assets", flush=True)
    for asset in assets:
        result = api(
            f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets?name={quote(asset.name)}",
            asset=asset,
        )
        if (
            not isinstance(result, dict)
            or type(result.get("id")) is not int
            or result["id"] <= 0
            or result.get("name") != asset.name
            or type(result.get("size")) is not int
            or result.get("size") != asset.stat().st_size
            or result.get("state") != "uploaded"
        ):
            raise ValueError(f"Malformed upload response for {asset}; inspect retained release")


def bump_branch(sha, branch, mode):
    selected_sha(sha)
    hooks = Path(__file__).resolve().parent / "bump-hooks"
    guard = hooks / "pre-push"
    if not guard.is_file() or not os.access(guard, os.X_OK):
        raise ValueError("Required advertised-SHA pre-push guard is missing or not executable")
    ref = f"refs/heads/{branch}"
    run("git", "check-ref-format", ref)
    if remote_ref(ref) != sha:
        raise ValueError("Selected branch moved since dispatch; dispatch again")
    if run("git", "status", "--porcelain"):
        raise ValueError("Bump requires a clean checkout")
    new = bump(mode)
    run("git", "add", "--", *map(str, SOURCE_PATHS))
    run("git", "commit", "-m", f"chore: bump version to {new}", "-m", TRAILER)
    if remote_ref(ref) != sha:
        raise ValueError("Selected branch moved during bump; nothing pushed")
    commit = run("git", "rev-parse", "HEAD")
    if run("git", "rev-list", "--parents", "-n", "1", commit) != f"{commit} {sha}" \
            or run("git", "status", "--porcelain"):
        raise ValueError("Bump commit must be a clean single-parent direct child of selected SHA")
    changed = set(run("git", "diff-tree", "--no-commit-id", "--name-only",
                      "-r", commit).splitlines())
    if not changed or not changed.issubset(set(map(str, SOURCE_PATHS))):
        raise ValueError("Bump commit must change source version metadata only")
    if TRAILER not in run("git", "log", "-1", "--format=%B").splitlines():
        raise ValueError("Bump commit is missing the required co-author trailer")
    if not guard.is_file() or not os.access(guard, os.X_OK):
        raise ValueError("Required advertised-SHA pre-push guard is missing or not executable")
    result = run("git", "-c", f"core.hooksPath={hooks}", "-c", "push.followTags=false",
                 "push", "--porcelain", "--no-follow-tags", "origin", f"{commit}:{ref}",
                 env={**os.environ, "BUMP_EXPECTED_SHA": sha,
                      "BUMP_EXPECTED_REF": ref, "BUMP_NEW_SHA": commit})
    if not any(line.startswith(" \t") and line.split("\t")[1].endswith(f":{ref}")
               for line in result.splitlines()):
        raise ValueError("Branch push was not a new update; inspect remote state")
    if remote_ref(ref) != commit:
        raise ValueError("Pushed branch failed exact-SHA verification; inspect remote state")
    print(f"Bumped source metadata to {new}; run Build manually on {branch}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "check", "publish", "bump"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch")
    parser.add_argument("--mode", choices=("patch", "minor", "major"))
    parser.add_argument("assets", nargs="*", type=Path)
    args = parser.parse_intermixed_args(argv)
    if args.command == "bump":
        if not args.branch or not args.mode:
            parser.error("bump requires --branch and --mode")
        bump_branch(args.sha, args.branch, args.mode)
    elif args.command in ("preflight", "check"):
        version, tag = (preflight if args.command == "preflight" else check)(args.sha)
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write(f"version={version}\ntag={tag}\n")
    else:
        publish(args.sha, args.assets)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, plistlib.InvalidFileException,
            ExpatError, subprocess.CalledProcessError) as error:
        print(f"::error::{error}. Stopped without rollback/retry. Any remote tag, "
              "release and uploaded assets are retained; see README recovery guidance.", file=sys.stderr)
        sys.exit(1)
