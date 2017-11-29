4d-plugin-workspace-services
============================

Collection of OS X native file manager commands.

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />

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
