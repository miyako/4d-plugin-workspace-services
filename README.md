4d-plugin-workspace-services
============================

Collection of OS X native file manager commands.

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|||

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />

### Releases

[1.2](https://github.com/miyako/4d-plugin-workspace-services/releases/tag/1.2)

## Syntax

```
result:=FINDER Perform operation (srcPath;dstPath;objects;operation)
```

Parameter|Type|Description
------------|------------|----
srcPath|TEXT|
dstPath|TEXT|
objects|ARRAY TEXT|ames of the files and directories to be manipulated
operation|LONGINT|see constants
success|LONGINT|return value of [performFileOperation:source:destination:files:tag:](https://developer.apple.com/documentation/appkit/nsworkspace/1524886-performfileoperation?language=objc)

* Finder Operations

```c
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

icon:=FINDER Get icon for file type (typeId;fileType)

Parameter|Type|Description
------------|------------|----
typeId|TEXT|
fileType|LONGINT|see constants

* File Types

```c
File OSType 0
File UTI 1
File Extension 2
File MIME Type 3
```

### Remarks

Carbon-QuickTime commands do nothing on 64 bits:

```
FULL SCREEN BEGIN
```

```
FULL SCREEN END
```

Commands
---

```cpp
// --- Finder
FINDER_Perform_operation
FINDER_Get_icon_for_file_type

// --- Application
APPLICATION_Get_path
APPLICATION_Launch
APPLICATION_Launch_paths

// --- File
FILE_Get_localized_name
FILE_Open_with_application
FILE_Get_application_name
FILE_SET_ICON
FILE_Get_icon

// --- Dock
DOCK_SET_BADGE_LABEL
DOCK_Get_icon
DOCK_Get_badge_label
DOCK_SET_ICON

// --- Full Screen (QuickTime)
FULL_SCREEN_BEGIN
FULL_SCREEN_END;

// --- Folder
FOLDER_GET_CONTENTS
FOLDER_GET_SUBPATHS
```

Examples
---

```
$icon:=FINDER Get icon for file type ("public.jpeg";File Extension)
SET PICTURE TO PASTEBOARD($icon)

$icon:=FINDER Get icon for file type ("4db";File Extension)
SET PICTURE TO PASTEBOARD($icon)

$icon:=FINDER Get icon for file type ("text/plain";File MIME Type)
SET PICTURE TO PASTEBOARD($icon)

$icon:=FINDER Get icon for file type ("trsh";File OSType)
SET PICTURE TO PASTEBOARD($icon)


$icon:=FILE Get icon (Structure file)
SET PICTURE TO PASTEBOARD($icon)

C_BLOB($data)
$filePath:=System folder(Desktop)+Generate UUID
BLOB TO DOCUMENT($filePath;$data)
FILE SET ICON ($filePath;$icon)
```

```
FOLDER GET CONTENTS (Get 4D folder(Database folder);$pathHFS;Path Style HFS)
FOLDER GET CONTENTS (Get 4D folder(Database folder);$pathPOS;Path Style POSIX)
FOLDER GET CONTENTS (Get 4D folder(Database folder);$pathURL;Path Style URL)
```

```
$filePath1:=System folder(Desktop)+Generate UUID+".txt"
$filePath2:=System folder(Desktop)+Generate UUID+".txt"

C_BLOB($data)
BLOB TO DOCUMENT($filePath1;$data)
BLOB TO DOCUMENT($filePath2;$data)

$appName:=FILE Get application name ($filePath)
$appName:="com.apple.TextEdit"
$appName:="TextEdit.app"
$appName:="TextEdit"

ARRAY TEXT($path;0)
APPEND TO ARRAY($path;$filePath1)
APPEND TO ARRAY($path;$filePath2)

APPLICATION Launch paths ($appName;Launch Without Activation | Launch And Print;$path)
```

```
result:=APPLICATION Get path (appId;pathStyle)
```

Parameter|Type|Description
------------|------------|----
appId|TEXT|
pathStyle|LONGINT|see constants
result|TEXT|

* Path Styles

```
Path Style HFS 0
Path Style POSIX 1
Path Style URL 2
```

returns the absolute or full path for the specified application, in the requested format

```
success:=APPLICATION Launch (appId;options)
```

Parameter|Type|Description
------------|------------|----
appId|TEXT|
options|LONGINT|see constants
success|LONGINT|return value of [launchAppWithBundleIdentifier:options:additionalEventParamDescriptor:launchIdentifier:](https://developer.apple.com/documentation/appkit/nsworkspace/1533335-launchappwithbundleidentifier?language=objc)

success:=APPLICATION Launch paths (appId;options;arg3)

Parameter|Type|Description
------------|------------|----
appId|TEXT|
options|LONGINT|see constants
paths|ARRAY TEXT|paths (internally converted from HFS to URL)
success|LONGINT|return value of [openURLs:withAppBundleIdentifier:options:additionalEventParamDescriptor:launchIdentifiers:](https://developer.apple.com/documentation/appkit/nsworkspace/1535886-openurls?language=objc)

* Launch Options

```
Launch And Print 2
Launch Without Adding Recents 256
Launch Without Activation 512
Launch Asyncronous 65536
Launch New Instance 524288
Launch And Hide 1048576
Launch And Hide Others 2097152
```

