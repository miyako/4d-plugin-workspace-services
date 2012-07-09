#include "4DPluginAPI.h"
#include "4DPlugin.h"

// --- Finder
void FINDER_Perform_operation(sLONG_PTR *pResult, PackagePtr pParams);
void FINDER_Get_icon_for_file_type(sLONG_PTR *pResult, PackagePtr pParams);

// --- Application
void APPLICATION_Get_path(sLONG_PTR *pResult, PackagePtr pParams);
void APPLICATION_Launch(sLONG_PTR *pResult, PackagePtr pParams);
void APPLICATION_Launch_paths(sLONG_PTR *pResult, PackagePtr pParams);

// --- File
void FILE_Get_localized_name(sLONG_PTR *pResult, PackagePtr pParams);
void FILE_Open_with_application(sLONG_PTR *pResult, PackagePtr pParams);
void FILE_Get_application_name(sLONG_PTR *pResult, PackagePtr pParams);
void FILE_SET_ICON(sLONG_PTR *pResult, PackagePtr pParams);
void FILE_Get_icon(sLONG_PTR *pResult, PackagePtr pParams);

// --- Dock
void DOCK_SET_BADGE_LABEL(sLONG_PTR *pResult, PackagePtr pParams);
void DOCK_Get_icon(sLONG_PTR *pResult, PackagePtr pParams);
void DOCK_Get_badge_label(sLONG_PTR *pResult, PackagePtr pParams);
void DOCK_SET_ICON(sLONG_PTR *pResult, PackagePtr pParams);

// --- Full Screen (QuickTime)
void FULL_SCREEN_BEGIN(sLONG_PTR *pResult, PackagePtr pParams);
void FULL_SCREEN_END();

// --- Folder
void FOLDER_GET_CONTENTS(sLONG_PTR *pResult, PackagePtr pParams);
void FOLDER_GET_SUBPATHS(sLONG_PTR *pResult, PackagePtr pParams);