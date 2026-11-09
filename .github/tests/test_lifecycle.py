"""Offline lifecycle regressions using actual repositories and receive-pack."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
import release
import source_version as source

INTAKE = "44a5101"
PRODUCT = "Workspace Services"
BUNDLE = Path(f"{PRODUCT}.4dbase/Plugins/{PRODUCT}.bundle")
GENERATED = tuple(BUNDLE / name for name in (
    f"Contents/MacOS/{PRODUCT}", "Contents/Info.plist",
    "Contents/Resources/English.lproj/InfoPlist.strings",
    "Contents/_CodeSignature/CodeResources",
))
PRESERVED = tuple(BUNDLE / name for name in (
    "Contents/Resources/manifest.json",
    "Contents/Resources/constants.xlf",
    f"Contents/Windows64/{PRODUCT}.4DX",
    "Contents/QuickLook/Thumbnail.png",
))
SIBLINGS = tuple(map(Path, (
    "Default/Other.bundle/Contents/MacOS/Other",
    "Default/Workspace Services.bundle/Contents/Resources/manifest.json",
    "Default/Workspace Services.bundle/Contents/Windows64/Workspace Services.4DX",
    "Default/Workspace Services.bundle/Contents/MacOS/helper",
    "build/source-config.txt",
)))


def git(root, *args, input=None):
    location = ["--git-dir", str(root)] if root.name.endswith(".git") else ["-C", str(root)]
    return subprocess.run(
        ["git", *location, *args], input=input, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


@contextlib.contextmanager
def cwd(root):
    old = Path.cwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(old)


class GitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix=".lifecycle-", dir=ROOT)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.local, self.remote, self.peer = (
            self.root / name for name in ("local", "remote.git", "peer")
        )
        git(self.root, "init", "--bare", str(self.remote))
        git(self.root, "init", "-b", "selected", str(self.local))
        for key, value in (
            ("user.name", "Lifecycle Test"), ("user.email", "test@example.invalid"),
            ("push.followTags", "true"), ("commit.gpgsign", "false"),
        ):
            git(self.local, "config", key, value)
        git(self.local, "commit", "--allow-empty", "-m", "ancestor")
        self.ancestor = git(self.local, "rev-parse", "HEAD")
        for name in source.SOURCE_PATHS:
            target = self.local / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        shutil.copytree(ROOT / ".github/scripts", self.local / ".github/scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for name in (".github/workflows/release.yml", ".github/workflows/bump-version.yml",
                     "Workspace Services.vcxproj", "4DPlugin.cpp", "README.md"):
            target = self.local / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.originals = {}
        for name in (*GENERATED, *PRESERVED):
            data = subprocess.run(
                ["git", "-C", str(ROOT), "show", f"{INTAKE}:{name}"],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ).stdout
            target = self.local / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if name in GENERATED:
                self.originals[name] = data
        for name in SIBLINGS:
            target = self.local / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"tracked sibling fixture; not generated product output")
        (self.local / GENERATED[0]).chmod(0o755)
        git(self.local, "add", ".")
        git(self.local, "commit", "-m", "fixture")
        self.sha = git(self.local, "rev-parse", "HEAD")
        self.version = source.read(self.local)
        self.tag = f"v{self.version}"
        git(self.local, "remote", "add", "origin", str(self.remote))
        git(self.local, "push", "origin", "HEAD:refs/heads/selected")
        git(self.root, "clone", "--branch", "selected", str(self.remote), str(self.peer))
        for key, value in (("user.name", "Peer"), ("user.email", "peer@example.invalid"),
                           ("commit.gpgsign", "false")):
            git(self.peer, "config", key, value)
        self.enter = cwd(self.local)
        self.enter.__enter__()
        self.addCleanup(self.enter.__exit__, None, None, None)

    def assert_no_tags(self):
        self.assertEqual(git(self.local, "tag", "--list"), "")
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def advance_peer(self):
        (self.peer / "peer.txt").write_text("concurrent update")
        git(self.peer, "add", ".")
        git(self.peer, "commit", "-m", "peer")
        git(self.peer, "push", "origin", "HEAD:refs/heads/selected")
        return git(self.peer, "rev-parse", "HEAD")

    def assets(self):
        paths = [Path(f"{PRODUCT}-{self.version}.{ext}") for ext in ("zip", "dmg")]
        for path in paths:
            path.write_bytes(b"fixture asset")
        return paths

    def test_bump_exact_single_parent_source_only_clean_no_tags(self):
        git(self.remote, "update-ref", "refs/heads/other", self.sha)
        with patch("sys.stdout", new_callable=io.StringIO):
            release.bump_branch(self.sha, "selected", "patch")
        new = git(self.local, "rev-parse", "HEAD")
        self.assertNotEqual(new, self.sha)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/selected"), new)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/other"), self.sha)
        self.assertEqual(git(self.local, "rev-list", "--parents", "-n", "1", new),
                         f"{new} {self.sha}")
        changed = git(self.local, "diff-tree", "--no-commit-id", "--name-only", "-r", new)
        self.assertEqual(set(changed.splitlines()), set(map(str, source.SOURCE_PATHS)))
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        message = git(self.local, "log", "-1", "--format=%B")
        self.assertIn("Co-authored-by:", message)
        self.assertIn("<223556219+Copilot@users.noreply.github.com>", message)
        self.assertEqual({name: (self.local / name).read_bytes() for name in GENERATED},
                         self.originals)
        self.assert_no_tags()

    def test_bump_does_not_follow_annotated_tags_even_when_configured(self):
        git(self.local, "tag", "-a", "unrelated", "-m", "must not follow")
        release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(git(self.local, "tag", "--list"), "unrelated")
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_bump_cli_does_not_leave_bytecode_or_worktree_dirt(self):
        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        result = subprocess.run(
            [sys.executable, ".github/scripts/release.py", "bump", "--sha", self.sha,
             "--branch", "selected", "--mode", "patch"],
            env=env, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assert_no_tags()

    def test_invalid_immutable_sha_and_branch_fail_without_publication(self):
        for sha in ("selected", self.sha.upper(), "a" * 39, "a" * 41, "a" * 40):
            with self.subTest(sha=sha), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                release.selected_sha(sha)
        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
            release.bump_branch(self.sha, "invalid..branch", "patch")
        self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)
        self.assert_no_tags()

    def test_initial_and_preparation_remote_races(self):
        real_bump = release.bump

        def concurrent(mode):
            value = real_bump(mode)
            self.advance_peer()
            return value

        with patch.object(release, "bump", side_effect=concurrent):
            with self.assertRaisesRegex(ValueError, "moved"):
                release.bump_branch(self.sha, "selected", "minor")
        remote = git(self.peer, "rev-parse", "HEAD")
        self.assertEqual(release.remote_ref("refs/heads/selected"), remote)
        git(self.local, "reset", "--hard", self.sha)
        with self.assertRaisesRegex(ValueError, "moved"):
            release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)
        self.assert_no_tags()

    def advertised_race(self, kind):
        original = release.run
        expected, pushes, reads = None, 0, 0

        def intercept(*args, **kwargs):
            nonlocal expected, pushes, reads
            if args[:2] == ("git", "ls-remote"):
                reads += 1
            if "push" in args:
                self.assertEqual(reads, 2, "race must follow the final remote read")
                pushes += 1
                if kind == "advance":
                    expected = self.advance_peer()
                elif kind == "rewind":
                    expected = self.ancestor
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                elif kind == "delete":
                    git(self.remote, "update-ref", "-d", "refs/heads/selected")
                elif kind == "same-result":
                    expected = git(self.local, "rev-parse", "HEAD")
                    git(self.remote, "fetch", "--no-tags", str(self.local), "HEAD")
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                else:
                    self.fail(kind)
            return original(*args, **kwargs)

        with patch.object(release, "run", side_effect=intercept):
            with self.assertRaises(subprocess.CalledProcessError):
                release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(pushes, 1)
        self.assertEqual(release.remote_ref("refs/heads/selected"), expected)
        self.assert_no_tags()

    def test_advertised_advance(self):
        self.advertised_race("advance")

    def test_advertised_rewind(self):
        self.advertised_race("rewind")

    def test_advertised_deletion(self):
        self.advertised_race("delete")

    def test_advertised_same_result_with_zero_hook_rows(self):
        self.advertised_race("same-result")

    def missing_guard(self, late, absent):
        runtime = self.root / "runtime"
        shutil.copytree(self.local / ".github/scripts", runtime)
        guard = runtime / "bump-hooks/pre-push"
        original = release.remote_ref
        reads = 0

        def lose():
            if absent:
                guard.unlink()
            else:
                guard.chmod(0o644)

        def remote(ref):
            nonlocal reads
            result = original(ref)
            reads += 1
            if late and reads == 2:
                lose()
            return result

        if not late:
            lose()
        with patch.object(release, "__file__", str(runtime / "release.py")), \
                patch.object(release, "remote_ref", side_effect=remote), \
                self.assertRaisesRegex(ValueError, "guard is missing or not executable"):
            release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(reads, 2 if late else 0)
        if not late:
            self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)
        self.assertEqual(original("refs/heads/selected"), self.sha)
        self.assert_no_tags()

    def test_initial_missing_guard(self):
        self.missing_guard(False, True)

    def test_initial_nonexecutable_guard(self):
        self.missing_guard(False, False)

    def test_late_missing_guard(self):
        self.missing_guard(True, True)

    def test_late_nonexecutable_guard(self):
        self.missing_guard(True, False)

    def invalid_commit(self, kind):
        original = release.run

        def intercept(*args, **kwargs):
            if args[:2] == ("git", "commit") and kind == "non-source":
                (self.local / "unrelated").write_text("not metadata")
                git(self.local, "add", "unrelated")
            result = original(*args, **kwargs)
            if args[:2] == ("git", "commit") and kind in ("merge", "empty"):
                tree = git(self.local, "rev-parse",
                           f"{self.sha}^{{tree}}" if kind == "empty" else "HEAD^{tree}")
                parents = ["-p", self.sha]
                if kind == "merge":
                    parents += ["-p", self.ancestor]
                new = git(self.local, "commit-tree", tree, *parents, input="invalid fixture\n")
                git(self.local, "reset", "--hard", new)
            return result

        with patch.object(release, "run", side_effect=intercept) as run:
            with self.assertRaises(ValueError):
                release.bump_branch(self.sha, "selected", "patch")
            self.assertFalse(any("push" in call.args for call in run.call_args_list))
        self.assertEqual(release.remote_ref("refs/heads/selected"), self.sha)
        self.assert_no_tags()

    def test_multiparent_bump_rejected(self):
        self.invalid_commit("merge")

    def test_non_source_bump_rejected(self):
        self.invalid_commit("non-source")

    def test_empty_bump_rejected(self):
        self.invalid_commit("empty")

    def test_missing_coauthor_trailer_fails_before_push(self):
        original = release.run

        def intercept(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[:2] == ("git", "commit"):
                git(self.local, "commit", "--amend", "-m", "trailer removed")
            return result

        with patch.object(release, "run", side_effect=intercept) as run:
            with self.assertRaisesRegex(ValueError, "co-author trailer"):
                release.bump_branch(self.sha, "selected", "patch")
            self.assertFalse(any("push" in item.args for item in run.call_args_list))
        self.assertEqual(release.remote_ref("refs/heads/selected"), self.sha)
        self.assert_no_tags()

    def test_bump_requires_globally_clean_checkout(self):
        (self.local / "untracked").write_text("must not be staged or removed")
        before = git(self.local, "status", "--porcelain")
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(git(self.local, "status", "--porcelain"), before)
        self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)
        self.assertEqual(release.remote_ref("refs/heads/selected"), self.sha)
        self.assert_no_tags()

    def test_postpush_exact_sha_verification_fails_closed(self):
        original = release.remote_ref
        reads = 0

        def remote(ref):
            nonlocal reads
            value = original(ref)
            reads += 1
            return self.sha if reads == 3 else value

        with patch.object(release, "remote_ref", side_effect=remote), \
                self.assertRaisesRegex(ValueError, "exact-SHA"):
            release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(reads, 3)
        self.assertEqual(original("refs/heads/selected"), git(self.local, "rev-parse", "HEAD"))
        self.assert_no_tags()

    def test_guard_rows_missing_environment_and_multiparent(self):
        guard = ROOT / ".github/scripts/bump-hooks/pre-push"
        git(self.local, "commit", "--allow-empty", "-m", "direct child")
        new = git(self.local, "rev-parse", "HEAD")
        env = {**os.environ, "BUMP_EXPECTED_SHA": self.sha,
               "BUMP_EXPECTED_REF": "refs/heads/selected", "BUMP_NEW_SHA": new}
        valid = f"{new} {new} refs/heads/selected {self.sha}\n"

        def execute(row, environment):
            return subprocess.run([str(guard)], input=row, env=environment,
                                  text=True, capture_output=True)

        self.assertEqual(execute(valid, env).returncode, 0)
        for row in ("", valid * 2, valid.replace("refs/heads/selected", "refs/heads/other"),
                    f"{new} {new} refs/heads/selected {'0' * 40}\n",
                    f"{new} {self.sha} refs/heads/selected {self.sha}\n"):
            with self.subTest(row=row):
                self.assertNotEqual(execute(row, env).returncode, 0)
        self.assertNotEqual(execute(valid, {}).returncode, 0)
        tree = git(self.local, "rev-parse", "HEAD^{tree}")
        merged = git(self.local, "commit-tree", tree, "-p", self.sha, "-p", self.ancestor,
                     input="merge\n")
        git(self.local, "update-ref", "HEAD", merged)
        env["BUMP_NEW_SHA"] = merged
        self.assertNotEqual(execute(
            f"{merged} {merged} refs/heads/selected {self.sha}\n", env).returncode, 0)
        self.assert_no_tags()

    def fake_gh(self):
        tools = self.root / "tools"
        tools.mkdir(exist_ok=True)
        executable = tools / "gh"
        executable.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, subprocess, sys\n"
            "from pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "log = Path(os.environ['FAKE_GH_LOG'])\n"
            "with log.open('a') as f: f.write(json.dumps(args)+'\\n')\n"
            "if args == ['auth', 'status']: sys.exit(0)\n"
            "method = args[args.index('--method')+1]\n"
            "endpoint = args[args.index('--method')+2]\n"
            "if method == 'GET': result = []\n"
            "elif endpoint.endswith('/git/refs'):\n"
            " payload = json.load(sys.stdin)\n"
            " subprocess.run(['git', '--git-dir', os.environ['FAKE_REMOTE'], 'update-ref',\n"
            "                 payload['ref'], payload['sha'], '0'*40], check=True)\n"
            " result = {'ref':payload['ref'], 'object':{'sha':payload['sha'],'type':'commit'}}\n"
            "elif endpoint.endswith('/releases'):\n"
            " result = {'id':123, **json.load(sys.stdin)}\n"
            "else:\n"
            " asset = Path(args[args.index('--input')+1])\n"
            " result = {'id':456,'name':asset.name,'size':asset.stat().st_size,'state':'uploaded'}\n"
            "print(json.dumps(result))\n"
        )
        executable.chmod(0o755)
        self.gh_log = self.root / "gh-log"
        return {**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
                "GITHUB_REPOSITORY": "owner/repo", "FAKE_REMOTE": str(self.remote),
                "FAKE_GH_LOG": str(self.gh_log),
                "GITHUB_OUTPUT": str(self.root / "github-output")}

    def cli(self, command, env, assets=()):
        return subprocess.run(
            [sys.executable, ".github/scripts/release.py", command, "--sha", self.sha,
             *map(str, assets)], env=env, text=True, capture_output=True,
        )

    def test_final_cli_check_and_publish_retain_original_tracked_native_dirt(self):
        env = self.fake_gh()
        initial = self.cli("preflight", env)
        self.assertEqual(initial.returncode, 0, initial.stderr)
        for name, original in self.originals.items():
            self.assertEqual((self.local / name).read_bytes(), original)
            with (self.local / name).open("ab") as output:
                output.write(b"\nnew generated native build/signature")
        git(self.local, "add", str(GENERATED[-1]))
        dirt = {name: (self.local / name).read_bytes() for name in GENERATED}
        assets = self.assets()
        before = git(self.local, "status", "--porcelain")
        self.assertTrue(all(str(name) in before for name in GENERATED))
        check = self.cli("check", env)
        self.assertEqual(check.returncode, 0, check.stderr)
        published = self.cli("publish", env, assets)
        self.assertEqual(published.returncode, 0, published.stderr)
        self.assertEqual(git(self.local, "status", "--porcelain"), before)
        self.assertEqual({name: (self.local / name).read_bytes() for name in GENERATED}, dirt)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertEqual(git(self.local, "tag", "--list"), "")
        calls = [json.loads(line) for line in self.gh_log.read_text().splitlines()]
        self.assertEqual(sum("--method" in call and call[call.index("--method") + 1] == "POST"
                             for call in calls), 4)

    def test_preflight_global_clean_rejects_native_dirt_before_api(self):
        env = self.fake_gh()
        (self.local / GENERATED[0]).write_bytes(b"dirty generated native output")
        result = self.cli("preflight", env)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.gh_log.exists())
        self.assertEqual((self.local / GENERATED[0]).read_bytes(), b"dirty generated native output")
        self.assert_no_tags()

    def test_final_cli_staged_unstaged_source_config_and_head_fail_before_apis(self):
        env = self.fake_gh()
        assets = self.assets()
        paths = [*source.SOURCE_PATHS, ".github/scripts/release.py",
                 ".github/workflows/release.yml", ".github/workflows/bump-version.yml",
                 "Workspace Services.vcxproj", "4DPlugin.cpp", "README.md",
                 *PRESERVED, *SIBLINGS]
        for name in paths:
            target = self.local / name
            original = target.read_bytes()
            for staged in (False, True):
                with self.subTest(path=name, staged=staged):
                    suffix = Path(name).suffix
                    comment = {
                        ".py": b"\n# changed tracked source/config\n",
                        ".yml": b"\n# changed tracked source/config\n",
                        ".plist": b"\n<!-- changed tracked source/config -->\n",
                        ".vcxproj": b"\n<!-- changed tracked source/config -->\n",
                    }.get(suffix, b"\n// changed tracked source/config\n")
                    target.write_bytes(original + comment)
                    if staged:
                        git(self.local, "add", str(name))
                    before = git(self.local, "status", "--porcelain")
                    for command in ("check", "publish"):
                        result = self.cli(command, env, assets if command == "publish" else ())
                        self.assertNotEqual(result.returncode, 0, (name, command, result.stdout))
                        self.assertFalse(self.gh_log.exists(), (name, command))
                    self.assertEqual(git(self.local, "status", "--porcelain"), before)
                    git(self.local, "restore", "--staged", "--worktree", "--", str(name))
        git(self.local, "commit", "--allow-empty", "-m", "HEAD moved")
        for command in ("check", "publish"):
            result = self.cli(command, env, assets if command == "publish" else ())
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.gh_log.exists())
        self.assert_no_tags()

    def test_final_cli_rejects_index_dirt_hidden_by_clean_worktree(self):
        env = self.fake_gh()
        assets = self.assets()
        paths = [*source.SOURCE_PATHS, ".github/workflows/release.yml",
                 "README.md", *PRESERVED, *SIBLINGS]
        for name in paths:
            with self.subTest(path=name):
                target = self.local / name
                original = target.read_bytes()
                target.write_bytes(original + b"\nindex-only tracked change\n")
                git(self.local, "add", str(name))
                target.write_bytes(original)
                self.assertEqual(git(self.local, "diff", "--name-only", self.sha), "")
                self.assertEqual(git(self.local, "diff", "--cached", "--name-only", self.sha),
                                 str(name))
                before = git(self.local, "status", "--porcelain")
                for command in ("check", "publish"):
                    result = self.cli(command, env, assets if command == "publish" else ())
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("differs from the selected commit", result.stderr)
                    self.assertFalse(self.gh_log.exists())
                self.assertEqual(target.read_bytes(), original)
                self.assertEqual(git(self.local, "status", "--porcelain"), before)
                git(self.local, "restore", "--staged", "--worktree", "--", str(name))
        self.assert_no_tags()

    def test_invalid_repository_context_fails_before_apis(self):
        env = self.fake_gh()
        for repo in ("owner", "owner/../repo", "owner/repo?x", "", "../repo", "owner/.."):
            with self.subTest(repo=repo):
                result = self.cli("check", {**env, "GITHUB_REPOSITORY": repo})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.gh_log.exists())
        self.assert_no_tags()


class WiringTests(unittest.TestCase):
    def test_immutable_manual_macos_lifecycle_and_exact_assets(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        trigger = workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0].strip()
        self.assertEqual(trigger, "workflow_dispatch:")
        self.assertEqual(workflow.count("uses: actions/checkout@v4"), 2)
        self.assertEqual(workflow.count("ref: ${{ github.sha }}"), 2)
        self.assertIn("group: release-publication\n  cancel-in-progress: false", workflow)
        for value in ("needs: [version]", "runs-on: macos-latest",
                      'ARCHS="arm64 x86_64"', "CODE_SIGNING_ALLOWED=NO",
                      'CONFIGURATION_BUILD_DIR="$PWD/$PLUGINS_DIR"',
                      "codesign --verify --deep --strict", 'notarize "$ZIP_PATH"',
                      'notarize "$DMG_PATH"', 'stapler staple "$DMG_PATH"',
                      'publish --sha "$SELECTED_SHA" "$ZIP_PATH" "$DMG_PATH"'):
            self.assertIn(value, workflow)
        for value in ("continue-on-error", "always()", "${{ inputs.", "softprops/",
                      "github.ref_name", "build-windows", "windows-latest"):
            self.assertNotIn(value, workflow)
        baseline = git(ROOT, "show", f"{INTAKE}:.github/workflows/release.yml")
        for value in ("PRODUCT_NAME: Workspace Services", "XCODE_PROJECT: Workspace Services.xcodeproj",
                      "VCX_SOLUTION: Workspace Services.sln", "MACOS_DEPLOYMENT_TARGET: '11.0'"):
            self.assertIn(value, baseline)
            self.assertIn(value, workflow)

    def test_bump_guard_and_create_only_publication(self):
        workflow = (ROOT / ".github/workflows/bump-version.yml").read_text()
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("SELECTED_BRANCH: ${{ github.ref_name }}", workflow)
        for mode in ("patch", "minor", "major"):
            self.assertIn(f"- {mode}", workflow)
        helper = (ROOT / ".github/scripts/release.py").read_text()
        for value in ('"DELETE"', '"PATCH"', "--clobber", '"--force"',
                      '"gh", "release", "create"', '"git", "tag"'):
            self.assertNotIn(value, helper)
        self.assertIn('"push.followTags=false"', helper)
        self.assertIn('"--no-follow-tags"', helper)
        guard = ROOT / ".github/scripts/bump-hooks/pre-push"
        self.assertTrue(guard.is_file() and os.access(guard, os.X_OK))


if __name__ == "__main__":
    unittest.main()
