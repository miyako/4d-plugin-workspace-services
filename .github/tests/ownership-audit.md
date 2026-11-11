# Native ownership audit

## Provenance and inventory

Audit baseline: `d5585cbc7d26f7e0bd8b86e97c1c2096be948bc9`.
Canonical guidance read through GitHub's immutable contents API:
`miyako/skills/4d-skills/skills/4dplugin/SKILL.md` at
`e6b492fcb81e5e1a7f7db723594b420e63bf6eb9`.
Prior harness reference, also read through the immutable API without a
checkout: `miyako/4d-plugin-windows-services` at
`7eb674e4d2cf807f957496a88468462af8e0de69`. Its results are not this audit's results.

The complete bundled SDK implementation says `rev : v14`, its header and
types say `v13`; these comments are not a verified upstream release.
Protected Git blobs:

| File in `4D Plugin API/` | Blob |
|---|---|
| `4DPluginAPI.c` | `29788ed041effaf67269ccd93f971e8aee2ce5f8` |
| `4DPluginAPI.h` | `9054b45ffc7ff6f5b8d57529a3788a55d977b314` |
| `PublicTypes.h` | `2bb392e73e9c556c274fe0a75b3a6b83e310b77c` |
| `PrivateTypes.h` | `77053dc0c0a3718d2d3b6f158371a6af78c6ae66` |
| `EntryPoints.h` | `730f2f77ff2713fb2fe4b7d6562baeedf5f664cb` |
| `Flags.h` | `10a83185333dac06a62dda61b9f9428243d1e2ee` |
| `4DPluginAPI.def` | `996ecc4ab11ad165de9192eba2e7478db141c757` |

All tracked native production implementations are the SDK, `4DPlugin.cpp`,
and these **16** wrappers under `4D Plugin API/Classes/`:
`ARRAY_BOOLEAN`, `ARRAY_DATE`, `ARRAY_INTEGER`, `ARRAY_LONGINT`, `ARRAY_REAL`,
`ARRAY_TEXT`, `ARRAY_TIME`, `C_BLOB`, `C_DATE`, `C_INTEGER`, `C_LONGINT`,
`C_PICTURE`, `C_POINTER`, `C_REAL`, `C_TEXT`, `C_TIME`.
All declarations, including `C_TYPES.h`, the prefix header and dispatcher
header, were included in the inventory. `CBytes` and `CPicture` are internal
helpers in the blob/picture sources, not additional SDKs.
Both Xcode's actual sources phase and the legacy VCX compile memberships
contain these same 18 production translation units; the harness compiles all,
including dormant helper methods. The `.def` exports the SDK entrypoint.
There is no independent Windows command implementation; the checked-in
Windows project/binary does not establish a working Windows build.

The source and bundled manifests agree: 18 commands, with text arrays in
commands 1 (Finder inputs), 5 (launch-path inputs), 17 and 18 (folder outputs).
The scalar text inputs/outputs in commands 2-11 and 13, picture inputs/outputs
in 2/9/10/12/14, and numeric/full-screen commands were not excluded.
`CommandDispatcher` calls stack-local wrappers without copying them.
Picture production commands call the SDK directly, not `CPicture`.
`CPicture`/`C_PICTURE`/`C_POINTER` defects and the implicit-copy defects below
are therefore **compiled latent defects**, not a demonstrated exported-command
crash. Repository search is used to establish reachability, not safety.
Tracked bundle binaries, archives, 4D database content, manifests, project
files and existing release automation are preserved, not executed or rebuilt.

## Exact SDK contracts and fixes

`PA_CreateVariable(eVK_Unistring)` allocates an empty string (SDK 3632-3634);
the picture variant creates an empty owned picture (3549-3551).
`PA_SetStringVariable` (3826-3831) and `PA_SetPictureVariable` (3852-3857)
shallow-assign, without clearing or retaining. `PA_GetPictureVariable`
(3729-3736) explicitly borrows. `PA_DuplicatePicture(p,1)` (447-454)
requests a retain; `PA_DisposePicture` releases.

`CPicture::fromFileAtPath` used to overwrite an empty owner with a path
descriptor, dispose that descriptor, then clear the same allocation via its
argument alias. The output picture argument was never cleared. It now uses
the content setter on the initialized argument, retains the borrowed output
through `setPicture` **before** clearing both arguments, and has exactly one
string owner. `setBytes` releases the creation owner after `setPicture`
retains it. It captures creation error immediately and does not adopt an
unspecified failed return; the existing owned picture remains intact.

`createCopy`, `createGrayScale`, `getSize` and `createThumbnail` no longer
allocate an empty picture immediately before shallow-overwriting it:
the overwritten slot starts Undefined and the existing SDK setter establishes
its final kind. Borrowed input pictures remain explicitly detached before
argument cleanup. Returned picture owners remain detached and transferred to
the caller, who must dispose them. Actual command results are cleared only
after an immediate successful error check. Failed/unspecified results,
including a poisoned raw `fType=0`, are never normalized, adopted or cleared.
This does not add worker throws or a new error channel.

`PA_ConvertCharsetToCharset` (4775-4794) explicitly returns **bytes** and
forwards byte capacity. `CPicture::createCopy` passed that size to
`CUTF16String`, whose length is UTF-16 **code units**. The fix divides by
`sizeof(PA_Unichar)`. ASCII `.png`/`.jpg`/`.tif` previously read beyond the
byte vector. BMP/supplementary fixtures may fit in the oversized input-derived
capacity and are not claimed to fail ASan for that reason.

`C_POINTER::getVariable` tried to construct a reference from an owning
`PA_GetPointerValue` result (header 409 requires clearing that result).
It also interpreted the value union as reference metadata. The variable
branch now uses this exact SDK's `PA_SetVariableOrFieldReference`
(3919-3945), which derives scope/tag/name/index from the pointer. No invented
reference layout or API/engine ABI header changes.

Seven array wrappers, `C_BLOB`, `CPicture` and `C_PICTURE` own raw pointers
or an exclusive picture reference but allowed implicit shallow C++ copies.
The same final harness demonstrates nine baseline ASan use-after-frees and
one `CPicture` duplicate-release reference proof. Their copy constructors
and assignments are now deleted, following the already-noncopyable
`C_TEXT`. All actual consumers still compile. Value-owned `CBytes`, date,
integer, longint, real and time values and borrowed `C_POINTER` remain
copyable; no production copy callsite is claimed.

## Preserved paths and concrete limits

`PA_SetStringInArray` (4444-4460) disposes the old element and shallow-transfers
on the exact predicate: Unicode array, non-null data, index >= 0 and <= count,
non-null incoming descriptor. Index **zero** is accepted. `ARRAY_TEXT`
correctly leaves each accepted independent allocation with the array; there
is no post-transfer dispose to remove. `fromParamAtIndex` copies borrowed
element content into independent C++ strings before any array mutation.
The scalar wrapper uses `PA_SetUnistring` content replacement, not scalar
descriptor transfer; scalar return and parameter ownership are unchanged.
Numeric/date/time wrappers own values or independent C++ containers.
Blob conversion temporaries use C++ values; owned output handles transfer
to the host. There are no plugin-owned asynchronous callbacks or object/
collection property getter/adoption paths in this target.

The SDK's array resize may dispose removed elements **before** a failed
resize (3960 onward). Wrapper output loops also assume successful storage
creation/resize; a rejected insertion retains its caller's allocation.
No safe allocation-failure preservation guarantee follows from these APIs.
This audit deliberately does not rewrite the protected SDK, invent a
metadata/error rollback contract, or certify wrapper OOM safety. The harness
tests the setter's rejection contract with explicit caller cleanup, **not**
the wrapper's behavior under failed array storage allocation or resize.

`PA_GetPictureData` returns an engine-provided string with no explicit
ownership annotation in these bundled headers/implementation. Successful
representation enumeration/handle extraction is deferred pending an engine
contract; no blanket dispose was added. The harness uses pictures with no
representations and poisons the failed descriptor. It proves that failed
descriptors are not consumed, not representation-string ownership safety.
Constructor allocation failure, invalid converter return sizes, genuine
SDK OOM behavior and platform allocation failures are not certified.

Picture helpers historically ignore command errors and expose no new
notification mechanism. That behavior is preserved: failed commands leave
their existing output/argument behavior, and later cleanup/queries may
overwrite the error. This is a documented reporting gap, not a claim that
failure is success. Creation failure in `setBytes` remains visible through
`PA_GetLastError` because it returns before any cleanup/adoption call.

## Reproducible isolated evidence

Run on macOS, with Python's standard library and the existing Clang toolchain:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s .github/tests -p test_ownership.py -v
```

The **same final harness** extracts only actual production sources via
`git archive d5585cbc7d26f7e0bd8b86e97c1c2096be948bc9` and compiles baseline
and fixed sources independently. All seven SDK blob hashes are enforced.
No SDK fragments, SDK replacements, source rewrites, project builds or
dependency installs are used. ASan and UBSan are enabled; only alignment
instrumentation is disabled for legacy packed SDK structures. LeakSanitizer
is disabled; explicit allocation sets/reference counts enforce zero strings,
pictures and handles, with synthetic URL/platform object counts checked
after autorelease-pool teardown.

| Revision | Cases | Passing controls | Expected named failures |
|---|---:|---:|---:|
| Fixed actual source | 109 | 109 | 0 |
| Immutable baseline | 109 | 34 | 75 |

Baseline failures: 14 ASan heap-buffer-overflows in `createCopy`; nine ASan
implicit-copy use-after-frees; one `CPicture` duplicate release; ten path
duplicate/unowned string disposals; eight owning-value fetch/reference
misuses; 25 picture reference imbalances; six string allocation imbalances;
one missing creation-owner release; one attempted retain of a poisoned
failed picture creation. Every expected failure requires its named
diagnostic, not just any nonzero exit.

ASCII, BMP, supplementary surrogate pairs and empty fixtures run with both
allocated and null engine empty strings. Cases cover replacement, churn,
borrowed copy before mutation, resize/clear, Undefined array adoption, scalar
return/parameter independence, exact termination/content/length, index-zero
transfer, rejected type/data/index/null descriptor, repeated calls, picture
handoffs, owning synchronous command results, failed command poison, failed
command-argument handle creation and failed picture creation.

The **actual dispatcher** exercises all 18 commands with synthetic positive/
negative replies, three path variants, all ten Finder operation selections
and all four icon-type selections. All NSWorkspace, NSFileManager,
NSApplication/dock, NSBundle, AppleEvent, NSURL/path, UTI and image boundaries
are replaced **before compilation**. Unknown engine selectors and unexpected
image/native operations abort; unknown Objective-C stub messages cannot
dispatch into real platform objects. An `nm -u` import gate rejects real
workspace/file/application/URL/UTI/graphics operations and direct process,
network, filesystem, UI/input/service boundaries. Fixtures are in-memory;
no real enumeration, applications, paths, URLs, file operations, trash,
mount, notification, settings, process or user data is used.
The LP64 full-screen functions are actual no-op branches; no 32-bit
QuickTime coverage is claimed. Native image encoding success is not tested.

Both existing manual workflows and all scripts/native build phases were
read before validation. Xcode's Deployment phase signs/notarizes/packages;
native project builds are therefore not used. Neither existing workflow
triggers on push/PR. The added `Native ownership` workflow is read-only,
macOS-only, restricted by relevant paths and the exact audit branch/master,
and fetches immutable preservation history. It never dispatches, builds a
product, signs, packages, uploads, publishes, creates tags or releases.
Existing migration tests retain their original intake baseline; exact native
exceptions are additionally constrained by this audit's immutable baseline.

This is synthetic host and sanitizer evidence, not a native 4D ABI test,
a Windows build, a Windows/4D crash reproduction, an exhaustive platform
failure proof, or a certification of all dormant SDK APIs.
