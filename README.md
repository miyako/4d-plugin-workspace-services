4d-plugin-workspace-services
============================

Collection of OS X native file manager commands.

##Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|10.6|10.8|✖️|✖️|

###Remarks

These carbon/quicktime commands do nothing on 64 bits:

* FULL SCREEN BEGIN
* FULL SCREEN END

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
