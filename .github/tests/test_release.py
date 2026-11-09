"""Fail-closed, create-only publication tests; all gh traffic stays offline."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch
from urllib.parse import parse_qs, urlsplit

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
SPEC = importlib.util.spec_from_file_location("publication_release", ROOT / ".github/scripts/release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
SHA, TAG, REPO = "a" * 40, "v1.2.3", "owner/repo"


def entry(tag="v0.0.1", draft=False):
    return {"id": 9, "tag_name": tag, "draft": draft, "prerelease": False}


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(release, "run", return_value="")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_full_pagination_including_drafts_and_page_two(self):
        for draft in (True, False):
            with self.subTest(draft=draft), \
                    patch.object(release, "remote_ref", return_value=None), \
                    patch.object(release, "api", side_effect=[
                        [entry()] * 100, [entry(TAG, draft)],
                    ]) as api:
                with self.assertRaisesRegex(ValueError, "draft or published"):
                    release.available(REPO, TAG)
                self.assertEqual(api.call_args_list, [
                    call(f"repos/{REPO}/releases?per_page=100&page=1"),
                    call(f"repos/{REPO}/releases?per_page=100&page=2"),
                ])
        with patch.object(release, "remote_ref", return_value=None), \
                patch.object(release, "api", side_effect=[
                    [entry()] * 100, [entry()] * 100, [],
                ]) as api:
            release.available(REPO, TAG)
            self.assertEqual(api.call_count, 3)

    def test_errors_and_malformed_pages_fail_closed_at_every_page(self):
        errors = [
            *(subprocess.CalledProcessError(1, ["gh", str(code)])
              for code in (401, 403, 404, 422, 500)),
            OSError("network"), json.JSONDecodeError("bad", "?", 0),
        ]
        malformed = [
            {}, None, "[]", [None], [{}], [dict(entry(), id=True)],
            [dict(entry(), id=0)], [dict(entry(), id=-1)],
            [dict(entry(), tag_name=None)], [dict(entry(), tag_name="")],
            [dict(entry(), draft=0)], [dict(entry(), prerelease="false")],
            [entry()] * 101,
        ]
        for page in (1, 2, 3):
            for response in errors + malformed:
                with self.subTest(page=page, response=response), \
                        patch.object(release, "remote_ref", return_value=None), \
                        patch.object(release, "api", side_effect=(
                            [[entry()] * 100] * (page - 1) + [response]
                        )) as api:
                    with self.assertRaises((ValueError, OSError, subprocess.CalledProcessError)):
                        release.available(REPO, TAG)
                    self.assertEqual(api.call_count, page)

    def test_exact_remote_tag_and_malformed_remote(self):
        ref = f"refs/tags/{TAG}"
        with patch.object(release, "run", return_value=f"{SHA}\t{ref}") as run:
            self.assertEqual(release.remote_ref(ref), SHA)
            run.assert_called_once_with("git", "ls-remote", "--refs", "origin", ref)
        for value in ("invalid", f"{SHA}\t{ref}-other", f"bad\t{ref}",
                      f"{SHA}\t{ref}\n{SHA}\t{ref}"):
            with self.subTest(value=value), patch.object(release, "run", return_value=value):
                with self.assertRaises(ValueError):
                    release.remote_ref(ref)
        for response in (SHA, OSError("network")):
            with patch.object(release, "remote_ref", side_effect=(
                    response if isinstance(response, Exception) else lambda ref: response)), \
                    patch.object(release, "api") as api:
                with self.assertRaises((ValueError, OSError)):
                    release.available(REPO, TAG)
                api.assert_not_called()

    def test_transport_explicit_methods_binary_upload_and_no_retry(self):
        with patch.object(release, "run", return_value="[]") as run:
            release.api("repos/o/r/releases?per_page=100&page=2")
            run.assert_called_once_with(
                "gh", "api", "--method", "GET",
                "repos/o/r/releases?per_page=100&page=2", input=None,
            )
            payload = {"ref": f"refs/tags/{TAG}", "sha": SHA}
            release.api("repos/o/r/git/refs", payload)
            self.assertEqual(run.call_args.args[:4], ("gh", "api", "--method", "POST"))
            self.assertEqual(json.loads(run.call_args.kwargs["input"]), payload)
            release.api("https://uploads.github.com/repos/o/r/releases/123/assets",
                        asset=Path("asset.zip"))
            self.assertEqual(run.call_args.args[-4:], (
                "--header", "Content-Type: application/octet-stream", "--input", "asset.zip",
            ))
        for failure in (subprocess.CalledProcessError(1, "gh"), OSError("network")):
            with patch.object(release, "run", side_effect=failure) as run:
                with self.assertRaises(type(failure)):
                    release.api("repos/o/r/releases")
                self.assertEqual(run.call_count, 1)
        with patch.object(release, "run", return_value="not json"):
            with self.assertRaises(ValueError):
                release.api("repos/o/r/releases")


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix=".publication-", dir=ROOT)
        self.addCleanup(self.directory.cleanup)
        previous = Path.cwd()
        os.chdir(self.directory.name)
        self.addCleanup(os.chdir, previous)
        self.assets = [Path(f"Workspace Services-1.2.3.{ext}") for ext in ("zip", "dmg")]
        for asset in self.assets:
            asset.write_bytes(b"fixture asset")
        self.calls, self.tag, self.published, self.uploaded = [], None, None, []
        self.failure, self.race, self.bad_kind, self.bad_result = None, None, None, None
        self.pages = [[]]
        self.start(patch.object(release, "context", return_value=(REPO, "1.2.3", TAG)))
        self.start(patch.object(release, "remote_ref", side_effect=lambda ref: self.tag))
        self.start(patch.object(release, "run", side_effect=self.fake_gh))
        self.start(patch("sys.stdout", new_callable=io.StringIO))

    def start(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def fake_gh(self, *args, **kwargs):
        if args[0] == "git":
            return ""
        if args == ("gh", "auth", "status"):
            return ""
        self.assertEqual(args[:4], ("gh", "api", "--method", args[3]))
        method, endpoint = args[3:5]
        asset = Path(args[args.index("--input") + 1]) if "--header" in args else None
        payload = json.loads(kwargs["input"]) if kwargs.get("input") else None
        self.calls.append((method, endpoint, payload, asset))
        if "/releases?" in endpoint:
            self.assertEqual(method, "GET")
            page = int(parse_qs(urlsplit(endpoint).query)["page"][0])
            result = self.pages[page - 1]
            if isinstance(result, Exception):
                raise result
            return json.dumps(result)
        self.assertEqual(method, "POST")
        if endpoint.endswith("/git/refs"):
            kind = "tag"
            if self.race:
                self.tag = self.race
            if self.tag is not None or self.failure == kind:
                raise subprocess.CalledProcessError(1, ["gh", "api", "422"])
            self.tag = payload["sha"]
            result = {"ref": payload["ref"], "object": {"sha": self.tag, "type": "commit"}}
        elif endpoint.endswith("/releases"):
            kind = "release"
            if self.failure == kind:
                raise subprocess.CalledProcessError(1, ["gh", "api"])
            self.published = {"id": 123, **payload}
            result = self.published
        elif asset is not None:
            kind = asset.suffix
            if self.failure == kind:
                raise subprocess.CalledProcessError(1, ["gh", "api"])
            self.uploaded.append(asset.name)
            result = {"id": 456, "name": asset.name, "size": asset.stat().st_size,
                      "state": "uploaded"}
        else:
            raise AssertionError(endpoint)
        return json.dumps(self.bad_result if self.bad_kind == kind else result)

    def publish(self):
        release.publish(SHA, self.assets)

    def reset(self):
        self.calls.clear()
        self.tag, self.published, self.uploaded = None, None, []
        self.failure = self.race = self.bad_kind = self.bad_result = None

    def test_exact_create_only_payload_order_release_id_and_encoded_asset_names(self):
        self.publish()
        self.assertEqual(self.tag, SHA)
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(self.calls[1], (
            "POST", f"repos/{REPO}/git/refs",
            {"ref": f"refs/tags/{TAG}", "sha": SHA}, None,
        ))
        self.assertEqual(self.calls[2], ("POST", f"repos/{REPO}/releases", {
            "tag_name": TAG, "target_commitish": SHA, "name": TAG,
            "draft": False, "prerelease": False, "body": "",
            "generate_release_notes": False,
        }, None))
        for method, endpoint, payload, asset in self.calls[3:]:
            self.assertEqual(method, "POST")
            self.assertTrue(endpoint.startswith(
                f"https://uploads.github.com/repos/{REPO}/releases/123/assets?name="))
            self.assertNotIn(" ", endpoint)
            self.assertNotIn("#", endpoint)
            self.assertEqual(parse_qs(urlsplit(endpoint).query), {"name": [asset.name]})
            self.assertIsNone(payload)
        self.assertEqual(self.uploaded, [asset.name for asset in self.assets])

    def test_same_and_different_sha_post_races_fail_without_reuse(self):
        for sha in (SHA, "b" * 40):
            with self.subTest(sha=sha):
                self.reset()
                self.race = sha
                with self.assertRaises(subprocess.CalledProcessError):
                    self.publish()
                self.assertEqual(self.tag, sha)
                self.assertEqual(len(self.calls), 2)
                self.assertIsNone(self.published)
                self.assertEqual(self.uploaded, [])

    def test_each_post_failure_retains_all_prior_state_without_retry_or_rollback(self):
        for kind, count, tag, published, uploaded in (
            ("tag", 2, None, False, []),
            ("release", 3, SHA, False, []),
            (".zip", 4, SHA, True, []),
            (".dmg", 5, SHA, True, [self.assets[0].name]),
        ):
            with self.subTest(kind=kind):
                self.reset()
                self.failure = kind
                with self.assertRaises(subprocess.CalledProcessError):
                    self.publish()
                self.assertEqual(len(self.calls), count)
                self.assertEqual(self.tag, tag)
                self.assertEqual(self.published is not None, published)
                self.assertEqual(self.uploaded, uploaded)
                self.assertTrue(all(item[0] in ("GET", "POST") for item in self.calls))

    def test_final_recheck_new_draft_page_two_error_and_malformed(self):
        for result in ([entry(TAG, True)], {"message": "bad"},
                       subprocess.CalledProcessError(1, ["gh", "404"]),
                       json.JSONDecodeError("bad", "?", 0)):
            with self.subTest(result=result):
                self.reset()
                self.pages = [[]]
                release.preflight(SHA)
                self.calls.clear()
                self.pages = [[entry()] * 100, result]
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    self.publish()
                self.assertEqual(len(self.calls), 2)
                self.assertIsNone(self.tag)
                self.assertIsNone(self.published)

    def test_fake_gh_walks_all_full_pages_before_create(self):
        self.pages = [[entry()] * 100, [entry()] * 100, []]
        self.publish()
        self.assertEqual(len(self.calls), 7)
        self.assertEqual([item[1] for item in self.calls[:3]], [
            f"repos/{REPO}/releases?per_page=100&page={page}" for page in (1, 2, 3)
        ])
        self.assertEqual(self.tag, SHA)
        self.assertEqual(self.uploaded, [asset.name for asset in self.assets])

    def test_fake_gh_every_page_draft_published_errors_and_malformed_stop_creation(self):
        errors = [
            *(subprocess.CalledProcessError(1, ["gh", str(code)])
              for code in (401, 403, 404, 422, 500)),
            OSError("network"), json.JSONDecodeError("bad", "?", 0),
        ]
        malformed = [{}, None, "[]", [None], [{}], [dict(entry(), id=True)],
                     [dict(entry(), draft=0)], [dict(entry(), prerelease="false")],
                     [entry()] * 101]
        for page in (1, 2, 3):
            for result in errors + malformed + [[entry(TAG, True)], [entry(TAG, False)]]:
                with self.subTest(page=page, result=result):
                    self.reset()
                    self.pages = [[entry()] * 100] * (page - 1) + [result]
                    with self.assertRaises((ValueError, OSError, subprocess.CalledProcessError)):
                        self.publish()
                    self.assertEqual(len(self.calls), page)
                    self.assertTrue(all(item[0] == "GET" for item in self.calls))
                    self.assertIsNone(self.tag)
                    self.assertIsNone(self.published)
                    self.assertEqual(self.uploaded, [])

    def test_authentication_failure_never_checks_or_mutates_remote(self):
        original = self.fake_gh

        def unauthenticated(*args, **kwargs):
            if args == ("gh", "auth", "status"):
                raise subprocess.CalledProcessError(1, args)
            return original(*args, **kwargs)

        with patch.object(release, "run", side_effect=unauthenticated), \
                patch.object(release, "remote_ref") as remote:
            with self.assertRaises(subprocess.CalledProcessError):
                self.publish()
            remote.assert_not_called()
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.tag)

    def test_final_recheck_new_remote_tag_prevents_all_gh_calls(self):
        release.preflight(SHA)
        self.calls.clear()
        self.tag = SHA
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_post_tag_exact_sha_verification_never_creates_release_on_failure(self):
        for result in (None, "b" * 40, OSError("network"), ValueError("malformed")):
            with self.subTest(result=result):
                self.reset()
                with patch.object(release, "remote_ref", side_effect=[None, result]):
                    with self.assertRaises((ValueError, OSError)):
                        self.publish()
                self.assertEqual(self.tag, SHA)
                self.assertEqual(len(self.calls), 2)
                self.assertIsNone(self.published)

    def test_malformed_post_responses_stop_without_undoing_created_state(self):
        tag_response = {"ref": f"refs/tags/{TAG}", "object": {"sha": SHA, "type": "commit"}}
        release_response = {"id": 123, "tag_name": TAG, "target_commitish": SHA,
                            "name": TAG, "draft": False, "prerelease": False, "body": ""}
        asset_response = {"id": 456, "name": self.assets[0].name,
                          "size": self.assets[0].stat().st_size, "state": "uploaded"}
        for kind, responses, count in (
            ("tag", [None, {}, dict(tag_response, ref="refs/tags/wrong"),
                     dict(tag_response, object={"sha": "b" * 40, "type": "commit"})], 2),
            ("release", [None, {}, dict(release_response, id=True),
                         dict(release_response, id=0), dict(release_response, draft=True),
                         dict(release_response, prerelease=True),
                         dict(release_response, tag_name="v9.9.9")], 3),
            (".zip", [None, {}, dict(asset_response, id=True), dict(asset_response, size=True),
                      dict(asset_response, size=1), dict(asset_response, name="wrong"),
                      dict(asset_response, state="new")], 4),
            (".dmg", [None, {}, dict(asset_response, name="wrong")], 5),
        ):
            for result in responses:
                with self.subTest(kind=kind, result=result):
                    self.reset()
                    self.bad_kind, self.bad_result = kind, result
                    with self.assertRaises(ValueError):
                        self.publish()
                    self.assertEqual(len(self.calls), count)
                    self.assertEqual(self.tag, SHA)
                    self.assertEqual(self.published is not None, kind != "tag")
                    self.assertEqual(len(self.uploaded), max(0, count - 3))

    def test_exact_two_nonempty_regular_assets_before_remote_operations(self):
        wrong = Path("wrong.zip")
        wrong.write_bytes(b"wrong asset")
        invalid = (
            [], [self.assets[0]], self.assets + [wrong], [self.assets[0], self.assets[0]],
            [wrong, self.assets[1]], [Path("missing.zip"), self.assets[1]],
            [Path("."), self.assets[1]],
        )
        for assets in invalid:
            with self.subTest(assets=assets), patch.object(release, "remote_ref") as remote:
                with self.assertRaises(ValueError):
                    release.publish(SHA, assets)
                remote.assert_not_called()
                self.assertEqual(self.calls, [])
        self.assets[0].write_bytes(b"")
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_boolean_upload_size_is_not_an_integer(self):
        self.assets[0].write_bytes(b"x")
        self.bad_kind = ".zip"
        self.bad_result = {"id": 456, "name": self.assets[0].name,
                           "size": True, "state": "uploaded"}
        with self.assertRaisesRegex(ValueError, "Malformed upload response"):
            self.publish()
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.tag, SHA)
        self.assertIsNotNone(self.published)
        self.assertEqual(self.uploaded, [self.assets[0].name])


class CLITests(unittest.TestCase):
    def test_distinct_preflight_and_check_interfaces_and_outputs(self):
        for command in ("preflight", "check"):
            with self.subTest(command=command), \
                    patch.object(release, command, return_value=("1.2.3", TAG)) as action, \
                    patch.dict(os.environ, GITHUB_OUTPUT="fixture-output"), \
                    patch("builtins.open", unittest.mock.mock_open()) as output:
                release.main([command, "--sha", SHA])
                action.assert_called_once_with(SHA)
                output.assert_called_once_with("fixture-output", "a")
                output().write.assert_called_once_with(f"version=1.2.3\ntag={TAG}\n")

    def test_publish_bump_and_missing_required_arguments(self):
        with patch.object(release, "publish") as publish:
            release.main(["publish", "--sha", SHA, "first.zip", "second.dmg"])
            publish.assert_called_once_with(SHA, [Path("first.zip"), Path("second.dmg")])
        with patch.object(release, "bump_branch") as bump:
            release.main(["bump", "--sha", SHA, "--branch", "selected", "--mode", "patch"])
            bump.assert_called_once_with(SHA, "selected", "patch")
        for args in (["bump", "--sha", SHA], ["bump", "--sha", SHA, "--branch", "selected"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    release.main(args)

    def test_cli_errors_explicitly_retain_state_and_exit_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / ".github/scripts/release.py"),
             "publish", "--sha", "invalid"], text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Stopped without rollback/retry", result.stderr)
        self.assertIn("remote tag, release and uploaded assets are retained", result.stderr)


if __name__ == "__main__":
    unittest.main()
