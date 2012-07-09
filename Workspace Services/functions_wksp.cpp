#include "functions_wksp.h"

#if VERSIONMAC
#define PathTypeHFS     0
#define PathTypePOSIX   1
#define PathTypeURL     2

#define FileOSType      0
#define FileTypeUTI     1
#define FileExtension	2
#define FileTypeMIME    3

#define OperationMove       0
#define OperationCopy       1
#define OperationLink       2
#define OperationCompress   3
#define OperationDecompress 4
#define OperationEncrypt    5
#define OperationDecrypt    6
#define OperationDestroy    7
#define OperationRecycle    8
#define OperationDuplicate  9

//#define PathTypeSystem	3
#include <Quicktime/Quicktime.h>
#include <CoreServices/CoreServices.h>
Ptr	gOldState = NULL;
BOOL gIsFullScreen = FALSE;
#endif

// ------------------------------------ Finder ------------------------------------

#if VERSIONMAC
NSString *_pathToURL(NSString *posix)
{	
	NSString *path = @"";
	
	if(posix){
        
		NSURL *item = [[NSURL alloc]initFileURLWithPath:posix];
		if(item){
			path = [item absoluteString];			
			[item release];		
		}
	}
	return path;
}

NSString *_pathToHFS(NSString *posix)
{	
	NSString *path = @"";
	
	if(posix){
		NSURL *item = [[NSURL alloc]initFileURLWithPath:posix];
		if(item){
			NSString *hfs = (NSString *)CFURLCopyFileSystemPath((CFURLRef)item, kCFURLHFSPathStyle);
			path = [hfs stringByAppendingString:@":"];
			[item release];
			[hfs release];
		}
	}
	return path;
}
#endif

void FINDER_Perform_operation(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_TEXT Param2;
	ARRAY_TEXT Param3;
	C_LONGINT Param4;
	C_LONGINT returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
    Param1.convertPathSystemToPOSIX();    
	Param2.fromParamAtIndex(pParams, 2);
    Param2.convertPathSystemToPOSIX();  
    NSString *source = Param1.copyUTF16String();
    NSString *destination = Param2.copyUTF16String();    
    
	Param3.fromParamAtIndex(pParams, 3);
	Param4.fromParamAtIndex(pParams, 4);
    
    NSMutableArray *files = [[NSMutableArray alloc]init];
    
    for(unsigned int i = 1; i < Param3.getSize(); ++i){
        CUTF16String u;
        Param3.copyUTF16StringAtIndex(&u, i);
        C_TEXT t;
        t.setUTF16String(&u);
        NSString *s = t.copyUTF16String();
        [files addObject:s];
        [s release];
    }   
    
    NSInteger tag = 0;
    NSString *operation;

    switch (Param4.getIntValue()) {
        case OperationMove:
            operation = NSWorkspaceMoveOperation;
            break;
        case OperationCopy:
            operation = NSWorkspaceCopyOperation;            
            break;            
        case OperationLink:
            operation = NSWorkspaceLinkOperation;               
            break;   
        case OperationCompress:
            operation = NSWorkspaceCompressOperation;             
            break;
        case OperationDecompress:
            operation = NSWorkspaceDecompressOperation;             
            break;            
        case OperationEncrypt:
            operation = NSWorkspaceEncryptOperation;            
            break;   
        case OperationDecrypt:
            operation = NSWorkspaceDecryptOperation;              
            break;
        case OperationDestroy:
            operation = NSWorkspaceDestroyOperation;             
            break;            
        case OperationRecycle:
            operation = NSWorkspaceRecycleOperation;               
            break;   
        default:
            operation = NSWorkspaceDuplicateOperation;              
            break;              
    }
    
    returnValue.setIntValue([[NSWorkspace sharedWorkspace]performFileOperation:operation
                                                                       source:source
                                                                  destination:destination
                                                                        files:files
                                                                          tag:&tag]);
                                        
	returnValue.setReturn(pResult);
    
    [source release];    
    [destination release];    
    [files release];
}

void FINDER_Get_icon_for_file_type(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_LONGINT Param2;
	C_PICTURE returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
	Param2.fromParamAtIndex(pParams, 2);
    
    NSString *typeId = Param1.copyUTF16String(); 
	unsigned int fileType = Param2.getIntValue();
    
    NSString *fileUTI = NULL;  
	NSImage *iconImage = NULL;
    
    switch (fileType) {
        case FileTypeMIME:
            fileUTI = (NSString *)UTTypeCopyPreferredTagWithClass(
                                            UTTypeCreatePreferredIdentifierForTag(
                                                                                  kUTTagClassMIMEType, 
                                                                                  (CFStringRef)typeId, 
                                                                                  NULL), 
                                            kUTTagClassFilenameExtension);
            if(fileUTI){
                iconImage = [[NSWorkspace sharedWorkspace]iconForFileType:fileUTI]; 
                [fileUTI release];
            }
            break;
            
        case FileOSType:
            fileUTI = NSFileTypeForHFSTypeCode(UTGetOSTypeFromString((CFStringRef)typeId));
            if(fileUTI) iconImage = [[NSWorkspace sharedWorkspace]iconForFileType:fileUTI];          
            break;
            
        case FileExtension:
            iconImage = [[NSWorkspace sharedWorkspace]iconForFileType:typeId];            
            break; 
            
        default:
            fileUTI = (NSString *)UTTypeCopyPreferredTagWithClass((CFStringRef)typeId, kUTTagClassFilenameExtension);
            if(fileUTI){
                iconImage = [[NSWorkspace sharedWorkspace]iconForFileType:fileUTI]; 
                [fileUTI release];
            } 
            break;            
    }
        
    if(iconImage) returnValue.setImage(iconImage);   
    
	returnValue.setReturn(pResult);

    [typeId release];
}

// ---------------------------------- Application ---------------------------------


void APPLICATION_Get_path(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_LONGINT Param2;
	C_TEXT returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
	Param2.fromParamAtIndex(pParams, 2);
    
    NSString *appId = Param1.copyUTF16String(); 
 	unsigned int pathType = Param2.getIntValue();  
    
    NSString *appPath = [[NSWorkspace sharedWorkspace]absolutePathForAppBundleWithIdentifier:appId];
    if(!appPath) appPath = [[NSWorkspace sharedWorkspace]fullPathForApplication:appId]; 
    
    if(appPath){
        
		switch (pathType){
			case PathTypePOSIX:
                returnValue.setUTF16String(appPath);
				break;
			case PathTypeURL:
                returnValue.setUTF16String(_pathToURL(appPath));
				break;					
            default :    
                returnValue.setUTF16String(_pathToHFS(appPath));
				break;     
        }
    } 

	returnValue.setReturn(pResult);
    
    [appId release];
}

void APPLICATION_Launch(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_LONGINT Param2;
	C_LONGINT returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
	Param2.fromParamAtIndex(pParams, 2);
    NSString *appId = Param1.copyUTF16String(); 
    NSString *appPath = [[NSWorkspace sharedWorkspace]absolutePathForAppBundleWithIdentifier:appId];
    if(!appPath) appPath = [[NSWorkspace sharedWorkspace]fullPathForApplication:appId]; 
    
    if(appPath){
        
        NSBundle *appBundle = [NSBundle bundleWithPath:appPath];
        
        if(appBundle){
            returnValue.setIntValue([[NSWorkspace sharedWorkspace]launchAppWithBundleIdentifier:[appBundle bundleIdentifier] 
                                                                                        options:Param2.getIntValue()
                                                                 additionalEventParamDescriptor:[NSAppleEventDescriptor nullDescriptor]
                                                                               launchIdentifier:nil]);
        }
    }
        
	returnValue.setReturn(pResult);

    [appId release];
}

void APPLICATION_Launch_paths(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_LONGINT Param2;
	ARRAY_TEXT Param3;
	C_LONGINT returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
	Param2.fromParamAtIndex(pParams, 2);
	Param3.fromParamAtIndex(pParams, 3);
    
    NSString *appId = Param1.copyUTF16String(); 
    NSString *appPath = [[NSWorkspace sharedWorkspace]absolutePathForAppBundleWithIdentifier:appId];
    if(!appPath) appPath = [[NSWorkspace sharedWorkspace]fullPathForApplication:appId]; 
    
    if(appPath){
        
        NSBundle *appBundle = [NSBundle bundleWithPath:appPath];
        
        if(appBundle){
            
            NSMutableArray *urls = [[NSMutableArray alloc]init];
            
            for(unsigned int i = 1; i < Param3.getSize(); ++i){
                CUTF16String u;
                Param3.copyUTF16StringAtIndex(&u, i);
                C_TEXT t;
                t.setUTF16String(&u);
                t.convertPathSystemToPOSIX();
                NSString *s = t.copyUTF16String();
                NSURL *url = [NSURL fileURLWithPath:s];
                if(url) [urls addObject:url];
                [s release];
            }            
            
            
            returnValue.setIntValue([[NSWorkspace sharedWorkspace]openURLs:urls
                                                   withAppBundleIdentifier:[appBundle bundleIdentifier]
                                                                   options:Param2.getIntValue()
                                            additionalEventParamDescriptor:[NSAppleEventDescriptor nullDescriptor]
                                                         launchIdentifiers:nil]);
            [urls release];
        }
    } 
        
	returnValue.setReturn(pResult);

    [appId release];
}

// ------------------------------------- File -------------------------------------


void FILE_Get_localized_name(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_TEXT returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
    Param1.convertPathSystemToPOSIX();
    
    NSString *fullPath = Param1.copyUTF16String();      
    NSFileManager *defaultManager = [[NSFileManager alloc]init];	
	NSString *displayNameAtPath = [defaultManager displayNameAtPath:fullPath];
    
    returnValue.setUTF16String(displayNameAtPath);    
	returnValue.setReturn(pResult);
    
	[defaultManager release];	
	[fullPath release];	    
}

void FILE_Open_with_application(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_TEXT Param2;
	C_LONGINT Param3;
	C_LONGINT returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
	Param2.fromParamAtIndex(pParams, 2);
	Param3.fromParamAtIndex(pParams, 3);
    Param1.convertPathSystemToPOSIX();
    
    NSString *fullPath = Param1.copyUTF16String(); 
    NSString *appId = Param2.copyUTF16String(); 
    NSString *appPath = [[NSWorkspace sharedWorkspace]absolutePathForAppBundleWithIdentifier:appId];
    if(!appPath) appPath = [[NSWorkspace sharedWorkspace]fullPathForApplication:appId];        
    
    returnValue.setIntValue([[NSWorkspace sharedWorkspace]openFile:fullPath
                                                   withApplication:appPath 
                                                     andDeactivate:Param3.getIntValue()]);    
    

	returnValue.setReturn(pResult);
    
	[appId release];	      
	[fullPath release];	     
}

void FILE_Get_application_name(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_TEXT returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
    Param1.convertPathSystemToPOSIX();
    
    NSString *fullPath = Param1.copyUTF16String(); 
    NSString *appName;
    NSString *fileType;
    
    if([[NSWorkspace sharedWorkspace]getInfoForFile:fullPath 
                                        application:&appName 
                                               type:&fileType]) returnValue.setUTF16String(appName);
    
	returnValue.setReturn(pResult);
}

void FILE_SET_ICON(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_PICTURE Param2;
    
	Param1.fromParamAtIndex(pParams, 1);    
	Param2.fromParamAtIndex(pParams, 2);
    
    NSImage *iconImage = Param2.copyImage();
    
    if(iconImage){
        Param1.convertPathSystemToPOSIX();        
        NSString *fullPath = Param1.copyUTF16String();  
        
        [[NSWorkspace sharedWorkspace]setIcon:iconImage 
                                      forFile:fullPath 
                                      options:0];
        [fullPath release];
        [iconImage release];        
    }
}

void FILE_Get_icon(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	C_PICTURE returnValue;
    
	Param1.fromParamAtIndex(pParams, 1);
    Param1.convertPathSystemToPOSIX();
    
    NSString *fullPath = Param1.copyUTF16String();
	NSImage *iconImage = [[NSWorkspace sharedWorkspace]iconForFile:fullPath];
    if(iconImage) returnValue.setImage(iconImage);
    [fullPath release];
                          
	returnValue.setReturn(pResult);
}

// ------------------------------------- Dock -------------------------------------


void DOCK_SET_BADGE_LABEL(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
    
	Param1.fromParamAtIndex(pParams, 1);
    NSString *badgeLabel = Param1.copyUTF16String();
    [[[NSApplication sharedApplication] dockTile]setBadgeLabel:badgeLabel];
    [badgeLabel release];
}

void DOCK_Get_icon(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_PICTURE returnValue;
    
	NSImage *iconImage = [[NSApplication sharedApplication] applicationIconImage];
    if(iconImage) returnValue.setImage(iconImage);    
    
	returnValue.setReturn(pResult);
}

void DOCK_Get_badge_label(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT returnValue;
    
	NSString *badgeLabel = [[[NSApplication sharedApplication]dockTile]badgeLabel];
    returnValue.setUTF16String(badgeLabel);
    
	returnValue.setReturn(pResult);
}

void DOCK_SET_ICON(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_PICTURE Param1;
    unsigned int w = 0;
    unsigned int h = 0;
    
	Param1.fromParamAtIndex(pParams, 1);
    Param1.getSize(&w, &h);	
    
    if((w) && (h)){
        NSImage *iconImage = Param1.copyImage();
        if(iconImage){
            [[NSApplication sharedApplication]setApplicationIconImage:iconImage]; 
            [iconImage release];        
        }
    }else{
        [[NSApplication sharedApplication]setApplicationIconImage:nil]; 
    }
}

// ---------------------------- Full Screen (QuickTime) ---------------------------


void FULL_SCREEN_BEGIN(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_LONGINT Param1;
	C_LONGINT Param2;
	C_LONGINT Param3;
    
	Param1.fromParamAtIndex(pParams, 1);
	Param2.fromParamAtIndex(pParams, 2);
	Param3.fromParamAtIndex(pParams, 3);
    
    short w = Param1.getIntValue();
    short h = Param2.getIntValue();
	
	BeginFullScreen(&gOldState, 0, &w, &h, 0, 0, Param3.getIntValue());
	gIsFullScreen = TRUE;
}

void FULL_SCREEN_END()
{
	if(gIsFullScreen)
	{
		EndFullScreen(gOldState,0);
		gIsFullScreen = FALSE;
		gOldState = NULL;
	}
}

// ------------------------------------ Folder ------------------------------------

void FOLDER_GET_CONTENTS(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	ARRAY_TEXT Param2;
	C_LONGINT Param3;
    
	Param1.fromParamAtIndex(pParams, 1);
    Param1.convertPathSystemToPOSIX();
    Param2.setSize(1);
    
    NSMutableString *fullPath = Param1.copyUTF16MutableString();    
	if(![fullPath hasSuffix:@"/"]) [fullPath appendString:@"/"];
	
	Param3.fromParamAtIndex(pParams, 3);
    
    NSFileManager *defaultManager = [[NSFileManager alloc]init];
    NSArray *subpaths = [defaultManager contentsOfDirectoryAtPath:fullPath error:NULL];	
    
	unsigned int pathType = Param3.getIntValue();    
    
	for(unsigned int i = 0 ; i < [subpaths count] ; ++i){
		
		switch (pathType){
			case PathTypePOSIX:
                Param2.appendUTF16String([fullPath stringByAppendingString:[subpaths objectAtIndex:i]]);
				break;
			case PathTypeURL:
                Param2.appendUTF16String(_pathToURL([fullPath stringByAppendingString:[subpaths objectAtIndex:i]]));
				break;					
            default :    
                Param2.appendUTF16String(_pathToHFS([fullPath stringByAppendingString:[subpaths objectAtIndex:i]]));
				break;
		}
	}	    
    
	Param2.toParamAtIndex(pParams, 2);
    
    [defaultManager release];
    [fullPath release];    
}

void FOLDER_GET_SUBPATHS(sLONG_PTR *pResult, PackagePtr pParams)
{
	C_TEXT Param1;
	ARRAY_TEXT Param2;
	C_LONGINT Param3;
    
	Param1.fromParamAtIndex(pParams, 1);
    Param1.convertPathSystemToPOSIX();
    Param2.setSize(1);
    
    NSMutableString *fullPath = Param1.copyUTF16MutableString();    
	if(![fullPath hasSuffix:@"/"]) [fullPath appendString:@"/"];
	
	Param3.fromParamAtIndex(pParams, 3);
    
    NSFileManager *defaultManager = [[NSFileManager alloc]init];
    NSArray *subpaths = [defaultManager subpathsOfDirectoryAtPath:fullPath error:NULL];	
    
	unsigned int pathType = Param3.getIntValue();    
    
	for(unsigned int i = 0 ; i < [subpaths count] ; ++i){
		
		switch (pathType){
			case PathTypePOSIX:
                Param2.appendUTF16String([fullPath stringByAppendingString:[subpaths objectAtIndex:i]]);
				break;
			case PathTypeURL:
                Param2.appendUTF16String(_pathToURL([fullPath stringByAppendingString:[subpaths objectAtIndex:i]]));
				break;					
            default :    
                Param2.appendUTF16String(_pathToHFS([fullPath stringByAppendingString:[subpaths objectAtIndex:i]]));
				break;
		}
	}	    
    
	Param2.toParamAtIndex(pParams, 2);
    
    [defaultManager release];
    [fullPath release]; 
}