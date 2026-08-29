![version](https://img.shields.io/badge/version-19%2B-5682DF)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-workspace-services)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-workspace-services/total)

# Workspace Services

Workspace Services is a collection of macOS-only commands that wrap `NSWorkspace`, `NSFileManager`, and `NSApplication` (AppKit/Foundation) to expose Finder-level file operations, application discovery/launch, file and Dock icon management, and folder enumeration to 4D. Commands that return an icon (`FINDER Get icon for file type`, `FILE Get icon`, `DOCK Get icon`) return a `Picture` encoded as TIFF.

**Platforms:** macOS only (Intel and Apple Silicon). There is no Windows implementation and no Linux runtime for 4D plugins.

---

## Summary table

| Command | Returns | Purpose |
|---|---|---|
| [FINDER Perform operation](#finder-perform-operation) | Longint | Move, copy, link, compress, decompress, encrypt, decrypt, destroy, recycle, or duplicate files via Finder |
| [FINDER Get icon for file type](#finder-get-icon-for-file-type) | Picture | Get the generic icon associated with a file type (extension, UTI, OS type, or MIME type) |
| [APPLICATION Get path](#application-get-path) | Text | Resolve an application's bundle identifier or name to a path |
| [APPLICATION Launch](#application-launch) | Longint | Launch an application by bundle identifier or name |
| [APPLICATION Launch paths](#application-launch-paths) | Longint | Launch an application and hand it a list of files/paths to open |
| [FILE Get localized name](#file-get-localized-name) | Text | Get the localized display name of a file or folder |
| [FILE Open with application](#file-open-with-application) | Longint | Open a file with a specific (or the default) application |
| [FILE Get application name](#file-get-application-name) | Text | Get the name of the application that would open a file |
| [FILE SET ICON](#file-set-icon) | — | Set a custom icon on a file |
| [FILE Get icon](#file-get-icon) | Picture | Get a file's current icon |
| [DOCK SET BADGE LABEL](#dock-set-badge-label) | — | Set the plugin host's Dock badge text |
| [DOCK Get icon](#dock-get-icon) | Picture | Get the plugin host's current Dock icon |
| [DOCK Get badge label](#dock-get-badge-label) | Text | Get the plugin host's current Dock badge text |
| [DOCK SET ICON](#dock-set-icon) | — | Set (or reset) the plugin host's Dock icon |
| [FOLDER GET CONTENTS](#folder-get-contents) | — | List the immediate contents of a folder |
| [FOLDER GET SUBPATHS](#folder-get-subpaths) | — | List the full recursive contents of a folder |

`FULL SCREEN BEGIN`/`FULL SCREEN END` (QuickTime full-screen playback) are also present in the plugin but are **deprecated and inert on every build 4D can run today** — see the note at the end of the [Requirements & platform notes](#requirements--platform-notes) section.

---

## Requirements & platform notes

- **macOS only.** No Windows or Linux support exists or is planned; `#if VERSIONMAC` gates the entire implementation.
- **Icons are returned as TIFF-encoded `Picture` values.** `FINDER Get icon for file type`, `FILE Get icon`, and `DOCK Get icon` all build the picture the same way internally (`NSImage` → `CGImage` → TIFF). 4D itself abstracts over the format, so you can use the result directly in a Picture field or `SET PICTURE TO PASTEBOARD`, but if you ever export the raw bytes elsewhere, they're TIFF.
- **Icon-returning commands fail silently, not with a 4D error.** If the lookup fails (unknown file type, no such file, no application icon set), the command returns an **empty Picture** rather than raising an error. Always check the result rather than assuming success.
- **`FINDER Perform operation` uses Apple's legacy `performFileOperation:source:destination:files:tag:` API**, which Apple deprecated in OS X 10.10 in favor of `NSFileManager` methods. It still works on current macOS, but Apple could remove it in a future release — if file operations mysteriously stop working after an OS upgrade, this is the first thing to check.
- **`DOCK SET BADGE LABEL`, `DOCK Get icon`, `DOCK Get badge label`, and `DOCK SET ICON` touch AppKit UI state** (`NSApplication`, `NSDockTile`, `applicationIconImage`). Apple documents these as main-thread APIs. The plugin's manifest marks them thread-safe, so if you call them from a 4D worker process/preemptive process, keep an eye out for Dock glitches or intermittent misbehavior — if you see any, call them from the main process instead.
- **`FOLDER GET SUBPATHS` walks the entire directory tree recursively**, synchronously, with no depth or item-count limit. On a very large or slow (e.g. network-mounted) folder this can take a long time to return. Prefer `FOLDER GET CONTENTS` (one level only) unless you specifically need the full recursive listing, and consider calling `FOLDER GET SUBPATHS` from a worker process for large trees.
- **Path style constants** (used by `FOLDER GET CONTENTS`, `FOLDER GET SUBPATHS`, and `APPLICATION Get path`):

  ```4d
  Path Style HFS 0    // "Macintosh HD:Users:me:file.txt"
  Path Style POSIX 1  // "/Users/me/file.txt"
  Path Style URL 2    // "file:///Users/me/file.txt"
  ```

- **File type constants** (used by `FINDER Get icon for file type`):

  ```4d
  File OSType 0
  File UTI 1
  File Extension 2
  File MIME Type 3
  ```

- **Finder operation constants** (used by `FINDER Perform operation`):

  ```4d
  Operation Move 0
  Operation Copy 1
  Operation Link 2
  Operation Compress 3
  Operation Decompress 4
  Operation Encrypt 5
  Operation Decrypt 6
  Operation Destroy 7
  Operation Recycle 8
  Operation Duplicate 9
  ```

- **Launch option constants** (used by `APPLICATION Launch` and `APPLICATION Launch paths`, combine with `|`):

  ```4d
  Launch And Print 2
  Launch Without Adding Recents 256
  Launch Without Activation 512
  Launch Asyncronous 65536
  Launch New Instance 524288
  Launch And Hide 1048576
  Launch And Hide Others 2097152
  ```

- **`FULL SCREEN BEGIN`/`FULL SCREEN END`** wrap the pre-2015 QuickTime full-screen API and are compiled only in 32-bit builds (`#ifndef __LP64__`). Every 4D build that runs on current macOS is 64-bit, so these two commands compile to no-ops today — they are not documented further here, and there's no reason to call them.

---

## FINDER Perform operation

### Syntax

```4d
result:=FINDER Perform operation(srcPath;dstPath;objects;operation)
```

| Parameter | Type | Description |
|---|---|---|
| `srcPath` | Text | Source folder path, as a POSIX or HFS path |
| `dstPath` | Text | Destination folder path (ignored for `Operation Destroy` and `Operation Recycle`) |
| `objects` | Array Text | Names (not full paths) of the files/folders inside `srcPath` to operate on |
| `operation` | Longint | One of the `Operation...` constants above |
| Result | Longint | `1` on success, `0` on failure |

### Description

Wraps `NSWorkspace performFileOperation:source:destination:files:tag:`. `objects` holds file/folder **names relative to `srcPath`**, not full paths — this mirrors the underlying Apple API. If `operation` doesn't match any of the defined constants, the plugin falls back to `Operation Duplicate` rather than failing — pass a valid constant to avoid surprises.

This API is deprecated by Apple (since OS X 10.10) but still functional on current macOS.

### Example

```4d
ARRAY TEXT($objects;0)
APPEND TO ARRAY($objects;"report.pdf")
APPEND TO ARRAY($objects;"notes.txt")

$success:=FINDER Perform operation("/Users/me/Documents/";"/Users/me/Desktop/";$objects;Operation Copy)

If($success=1)
	ALERT("Copied.")
Else
	ALERT("Copy failed.")
End if
```

```4d
// Move a single file to the Trash equivalent
ARRAY TEXT($objects;0)
APPEND TO ARRAY($objects;"old-draft.docx")
$success:=FINDER Perform operation("/Users/me/Documents/";"";$objects;Operation Recycle)
```

---

## FINDER Get icon for file type

### Syntax

```4d
icon:=FINDER Get icon for file type(typeId;fileType)
```

| Parameter | Type | Description |
|---|---|---|
| `typeId` | Text | The type identifier itself: a filename extension, a UTI, an OS type string, or a MIME type, depending on `fileType` |
| `fileType` | Longint | One of the `File...` constants above |
| Result | Picture | The generic icon for this file type. Empty if the type couldn't be resolved |

### Description

- `File Extension` — `typeId` is a filename extension without the dot, e.g. `"pdf"`.
- `File UTI` — `typeId` is a Uniform Type Identifier, e.g. `"public.jpeg"`.
- `File MIME Type` — `typeId` is a MIME type, e.g. `"text/plain"`; the plugin internally resolves it to a UTI first, then to a filename-extension tag, before looking up the icon.
- `File OSType` — `typeId` is a four-character OS type string, e.g. `"trsh"`.

If the lookup fails at any stage (unrecognized extension, MIME type with no matching UTI, etc.) the command returns an **empty Picture**, not an error.

### Example

From the plugin's own README:

```4d
$icon:=FINDER Get icon for file type("public.jpeg";File Extension)
SET PICTURE TO PASTEBOARD($icon)

$icon:=FINDER Get icon for file type("4db";File Extension)
SET PICTURE TO PASTEBOARD($icon)

$icon:=FINDER Get icon for file type("text/plain";File MIME Type)
SET PICTURE TO PASTEBOARD($icon)

$icon:=FINDER Get icon for file type("trsh";File OSType)
SET PICTURE TO PASTEBOARD($icon)
```

```4d
// Guard against an unresolved type
$icon:=FINDER Get icon for file type("application/x-made-up";File MIME Type)
If(Picture width($icon)=0)
	ALERT("No icon found for this type.")
End if
```

---

## APPLICATION Get path

### Syntax

```4d
result:=APPLICATION Get path(appId;pathStyle)
```

| Parameter | Type | Description |
|---|---|---|
| `appId` | Text | Bundle identifier (e.g. `"com.apple.TextEdit"`) or application name (e.g. `"TextEdit"`/`"TextEdit.app"`) |
| `pathStyle` | Longint | One of the `Path Style...` constants |
| Result | Text | The application's absolute path in the requested style, or an empty string if not found |

### Description

Resolution order: `absolutePathForAppBundleWithIdentifier:` is tried first (works when `appId` is a bundle identifier); if that returns nothing, `fullPathForApplication:` is tried (works when `appId` is an application name). If neither resolves, the result is an empty string.

### Example

```4d
$path:=APPLICATION Get path("com.apple.TextEdit";Path Style POSIX)
// $path = "/System/Applications/TextEdit.app"

$path:=APPLICATION Get path("TextEdit";Path Style HFS)
```

---

## APPLICATION Launch

### Syntax

```4d
success:=APPLICATION Launch(appId;options)
```

| Parameter | Type | Description |
|---|---|---|
| `appId` | Text | Bundle identifier or application name (same resolution rules as `APPLICATION Get path`) |
| `options` | Longint | Combination (`\|`) of the `Launch...` constants, or `0` |
| Result | Longint | `1` on success, `0` if the app couldn't be resolved or launch failed |

### Description

If `appId` can't be resolved to an installed application, the command returns `0` without attempting a launch.

### Example

```4d
$success:=APPLICATION Launch("com.apple.TextEdit";Launch Without Activation)

$success:=APPLICATION Launch("Preview";Launch And Hide|Launch Without Adding Recents)
```

---

## APPLICATION Launch paths

### Syntax

```4d
success:=APPLICATION Launch paths(appId;options;paths)
```

| Parameter | Type | Description |
|---|---|---|
| `appId` | Text | Bundle identifier or application name |
| `options` | Longint | Combination (`\|`) of the `Launch...` constants, or `0` |
| `paths` | Array Text | Full paths of files/documents to hand to the application (internally converted from HFS to file URLs) |
| Result | Longint | `1` on success, `0` if the app couldn't be resolved or launch failed |

### Description

Wraps `NSWorkspace openURLs:withAppBundleIdentifier:options:...`. Each entry in `paths` is converted to a `file://` URL before being passed to the application — pass ordinary paths, not URLs, in `paths`.

### Example

From the plugin's own README:

```4d
$filePath1:=System folder(Desktop)+Generate UUID+".txt"
$filePath2:=System folder(Desktop)+Generate UUID+".txt"

C_BLOB($data)
BLOB TO DOCUMENT($filePath1;$data)
BLOB TO DOCUMENT($filePath2;$data)

ARRAY TEXT($path;0)
APPEND TO ARRAY($path;$filePath1)
APPEND TO ARRAY($path;$filePath2)

APPLICATION Launch paths("com.apple.TextEdit";Launch Without Activation|Launch And Print;$path)
```

---

## FILE Get localized name

### Syntax

```4d
name:=FILE Get localized name(path)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Full path to a file or folder |
| Result | Text | The localized display name shown in Finder (e.g. respects the user's language and hides extensions when Finder does) |

### Description

Wraps `NSFileManager displayNameAtPath:`. Returns an empty string if `path` doesn't exist.

### Example

```4d
$name:=FILE Get localized name("/Applications/TextEdit.app")
// $name = "TextEdit" (not "TextEdit.app"), following the user's Finder display settings
```

---

## FILE Open with application

### Syntax

```4d
success:=FILE Open with application(path;appId;deactivate)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Full path to the file to open |
| `appId` | Text | Bundle identifier or application name of the app to open it with; pass an empty string to use the default application |
| `deactivate` | Longint | Non-zero deactivates the current (host) application after launching the target app |
| Result | Longint | `1` on success, `0` on failure |

### Description

If `appId` can't be resolved to an installed application, the underlying call is still made with a `nil` application, which tells macOS to open `path` with its default application — this is the documented behavior of the underlying Apple API, not a bug, so an unresolved/empty `appId` degrades gracefully rather than failing.

### Example

```4d
$success:=FILE Open with application("/Users/me/notes.txt";"com.apple.TextEdit";0)

// Let the system pick the default app
$success:=FILE Open with application("/Users/me/photo.heic";"";0)
```

---

## FILE Get application name

### Syntax

```4d
appName:=FILE Get application name(path)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Full path to a file |
| Result | Text | Name of the application that would open this file. Empty if the lookup fails |

### Description

Wraps `NSWorkspace getInfoForFile:application:type:`. If the call fails (no application known, file not found), the result is an empty string rather than an error.

### Example

```4d
$appName:=FILE Get application name("/Users/me/report.pdf")
// e.g. $appName = "Preview"
```

---

## FILE SET ICON

### Syntax

```4d
FILE SET ICON(path;icon)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Full path to the file |
| `icon` | Picture | The custom icon to assign |

### Description

No return value — this command has no result to check. If `icon` is empty/invalid, the command silently does nothing (the file's icon is left unchanged).

### Example

```4d
$icon:=FINDER Get icon for file type("public.jpeg";File Extension)
FILE SET ICON("/Users/me/Desktop/my-document.txt";$icon)
```

---

## FILE Get icon

### Syntax

```4d
icon:=FILE Get icon(path)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Full path to the file |
| Result | Picture | The file's current icon (custom if one was set with `FILE SET ICON`, otherwise the generic icon for its type). Empty if `path` doesn't resolve to an icon |

### Example

From the plugin's own README:

```4d
$icon:=FILE Get icon(Structure file)
SET PICTURE TO PASTEBOARD($icon)
```

---

## DOCK SET BADGE LABEL

### Syntax

```4d
DOCK SET BADGE LABEL(label)
```

| Parameter | Type | Description |
|---|---|---|
| `label` | Text | Text to show as the host application's Dock badge; pass an empty string to clear it |

### Description

No return value. Affects the plugin host's own Dock icon, not any other application's.

### Example

```4d
DOCK SET BADGE LABEL(String(Records in selection([MyTable])))

DOCK SET BADGE LABEL("")  // clear the badge
```

---

## DOCK Get icon

### Syntax

```4d
icon:=DOCK Get icon
```

| Parameter | Type | Description |
|---|---|---|
| Result | Picture | The host application's current Dock icon. Empty if AppKit has no application icon set (uncommon) |

### Example

```4d
$icon:=DOCK Get icon
SET PICTURE TO PASTEBOARD($icon)
```

---

## DOCK Get badge label

### Syntax

```4d
label:=DOCK Get badge label
```

| Parameter | Type | Description |
|---|---|---|
| Result | Text | The host application's current Dock badge text, or an empty string if none is set |

### Example

```4d
$label:=DOCK Get badge label
```

---

## DOCK SET ICON

### Syntax

```4d
DOCK SET ICON(icon)
```

| Parameter | Type | Description |
|---|---|---|
| `icon` | Picture | The icon to use as the host application's Dock icon |

### Description

No return value. Passing an **empty Picture** resets the Dock icon to the application's default (this is checked explicitly by the plugin, not just a side effect) — this is the documented way to undo a previous `DOCK SET ICON` call.

### Example

```4d
$icon:=FINDER Get icon for file type("public.jpeg";File Extension)
DOCK SET ICON($icon)

// later, restore the default
DOCK SET ICON(New picture)  // empty picture resets the Dock icon
```

---

## FOLDER GET CONTENTS

### Syntax

```4d
FOLDER GET CONTENTS(path;paths;pathType)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Full path to the folder |
| `paths` | Array Text | Filled with the full path of each direct child of `path` (files and subfolders, one level only) |
| `pathType` | Longint | One of the `Path Style...` constants |

### Description

Only the folder's immediate children are listed — it does not recurse into subfolders (for that, see `FOLDER GET SUBPATHS`). `path` doesn't need a trailing separator; the plugin adds one if missing. `paths` is reset to a 1-element array before being filled; if the folder can't be read, `paths` comes back empty.

**Consider 4D's own built-in `DOCUMENT LIST` command** if you don't specifically need this plugin's path-style conversion.

### Example

From the plugin's own README:

```4d
FOLDER GET CONTENTS(Get 4D folder(Database folder);$pathHFS;Path Style HFS)
FOLDER GET CONTENTS(Get 4D folder(Database folder);$pathPOS;Path Style POSIX)
FOLDER GET CONTENTS(Get 4D folder(Database folder);$pathURL;Path Style URL)
```

```4d
ARRAY TEXT($items;0)
FOLDER GET CONTENTS("/Users/me/Documents/";$items;Path Style POSIX)
For($i;1;Size of array($items))
	ALERT($items{$i})
End for
```

---

## FOLDER GET SUBPATHS

### Syntax

```4d
FOLDER GET SUBPATHS(path;paths;pathType)
```

| Parameter | Type | Description |
|---|---|---|
| `path` | Text | Full path to the folder |
| `paths` | Array Text | Filled with the full path of every file and folder anywhere below `path`, recursively |
| `pathType` | Longint | One of the `Path Style...` constants |

### Description

Same conversion/behavior as `FOLDER GET CONTENTS`, but recurses through the entire subtree with no depth limit. This is a synchronous, potentially long-running call on large trees or slow (network) volumes — see [Requirements & platform notes](#requirements--platform-notes).

### Example

```4d
ARRAY TEXT($items;0)
FOLDER GET SUBPATHS("/Users/me/Projects/";$items;Path Style POSIX)
ALERT(String(Size of array($items))+" items found")
```

---

## Error handling & troubleshooting

- **Icon commands never raise a 4D error on failure — they return an empty Picture.** Always test the result (e.g. `Picture width($icon)=0`) rather than assuming the lookup succeeded.
- **`FILE Open with application` with an unresolved `appId` still succeeds** by falling back to the file's default application — an empty result more likely means the file itself couldn't be opened, not that the named application was missing.
- **`APPLICATION Get path`/`APPLICATION Launch`/`APPLICATION Launch paths` all accept either a bundle identifier or an application name** for `appId`, tried in that order. If you get an unexpected empty result or launch failure, double-check the exact bundle identifier (e.g. via `mdls -name kMDItemCFBundleIdentifier` in Terminal) rather than assuming the name-based lookup will always match.
- **`FINDER Perform operation`'s `objects` array holds names relative to `srcPath`, not full paths.** Passing full paths here will not match anything and the operation will silently do nothing to those entries.
- **An unrecognized `operation` constant in `FINDER Perform operation` falls back to `Operation Duplicate`**, not an error — always pass one of the documented constants.
- **`FOLDER GET SUBPATHS` can be slow on large or network-mounted folders.** If a call seems to hang, this is very likely why — consider `FOLDER GET CONTENTS` plus your own recursion with a progress indicator, or run the call from a 4D worker process.
- **Dock commands (`DOCK SET BADGE LABEL`, `DOCK Get icon`, `DOCK Get badge label`, `DOCK SET ICON`) affect AppKit UI state, which Apple documents as main-thread-only.** If called from a worker/preemptive process, watch for Dock display glitches; if you see any, move the call to the main process.
- **`FINDER Perform operation` relies on an Apple API deprecated since OS X 10.10.** It works on current macOS, but if file operations suddenly stop working after a macOS upgrade, this deprecated dependency is the first thing to check.

---

## Quick reference

```4d
// Icons
$icon:=FINDER Get icon for file type("pdf";File Extension)
$icon:=FILE Get icon("/Users/me/report.pdf")
FILE SET ICON("/Users/me/report.pdf";$icon)

// Applications
$path:=APPLICATION Get path("com.apple.TextEdit";Path Style POSIX)
APPLICATION Launch("com.apple.TextEdit";Launch Without Activation)
ARRAY TEXT($paths;0)
APPEND TO ARRAY($paths;"/Users/me/notes.txt")
APPLICATION Launch paths("com.apple.TextEdit";Launch Without Activation;$paths)
FILE Open with application("/Users/me/notes.txt";"";0)

// Dock
DOCK SET BADGE LABEL("5")
DOCK SET ICON($icon)
DOCK SET ICON(New picture)  // reset to default

// Folders
ARRAY TEXT($items;0)
FOLDER GET CONTENTS("/Users/me/Documents/";$items;Path Style POSIX)
FOLDER GET SUBPATHS("/Users/me/Documents/";$items;Path Style POSIX)

// Finder file operations
ARRAY TEXT($objects;0)
APPEND TO ARRAY($objects;"file.txt")
FINDER Perform operation("/Users/me/Documents/";"/Users/me/Desktop/";$objects;Operation Copy)
```
