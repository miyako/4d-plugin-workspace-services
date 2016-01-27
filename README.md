4d-plugin-workspace-services
============================

Collection of functions from the NSFileManager and NSWorkSpace classes on OS X 10.5 and later.

###Remarks

These carbon/quicktime commands do nothing on 64 bits:

* FULL SCREEN BEGIN
* FULL SCREEN END

##Commands

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
