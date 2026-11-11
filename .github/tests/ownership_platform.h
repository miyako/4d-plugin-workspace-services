#import <Carbon/Carbon.h>
#import <Cocoa/Cocoa.h>
#import <CoreServices/CoreServices.h>
#import <ImageIO/ImageIO.h>
#include <cstring>

// All external workspace boundaries are replaced before compiling actual sources.
@interface OwnershipURL : NSObject {
    NSString *_text;
}
- (id)initWithString:(NSString *)value;
- (id)initFileURLWithPath:(NSString *)value;
+ (id)fileURLWithPath:(NSString *)value;
- (NSString *)absoluteString;
@end
@class OwnershipImage;
@interface OwnershipPlatform : NSObject
+ (OwnershipPlatform *)sharedWorkspace;
+ (OwnershipPlatform *)sharedApplication;
+ (OwnershipPlatform *)defaultManager;
+ (OwnershipPlatform *)bundleWithPath:(NSString *)path;
+ (id)nullDescriptor;
- (NSString *)absolutePathForAppBundleWithIdentifier:(NSString *)value;
- (NSString *)fullPathForApplication:(NSString *)value;
- (NSString *)bundleIdentifier;
- (BOOL)launchAppWithBundleIdentifier:(NSString *)value options:(NSUInteger)options
       additionalEventParamDescriptor:(id)event launchIdentifier:(void *)identifier;
- (BOOL)openURLs:(NSArray *)urls withAppBundleIdentifier:(NSString *)value
         options:(NSUInteger)options additionalEventParamDescriptor:(id)event
launchIdentifiers:(void *)identifiers;
- (BOOL)openFile:(NSString *)path withApplication:(NSString *)application
  andDeactivate:(BOOL)deactivate;
- (BOOL)performFileOperation:(NSString *)operation source:(NSString *)source
                destination:(NSString *)destination files:(NSArray *)files tag:(NSInteger *)tag;
- (OwnershipImage *)iconForFileType:(NSString *)type;
- (OwnershipImage *)iconForFile:(NSString *)file;
- (BOOL)setIcon:(id)icon forFile:(NSString *)file options:(NSUInteger)options;
- (BOOL)getInfoForFile:(NSString *)file application:(NSString **)application type:(NSString **)type;
- (NSString *)displayNameAtPath:(NSString *)path;
- (NSArray *)contentsOfDirectoryAtPath:(NSString *)path error:(NSError **)error;
- (NSArray *)subpathsOfDirectoryAtPath:(NSString *)path error:(NSError **)error;
- (OwnershipPlatform *)dockTile;
- (void)setBadgeLabel:(NSString *)value;
- (NSString *)badgeLabel;
- (OwnershipImage *)applicationIconImage;
- (void)setApplicationIconImage:(id)image;
@end
@interface OwnershipImage : NSObject
@property NSSize size;
- (id)initWithCGImage:(CGImageRef)image size:(NSSize)size;
- (CGImageRef)CGImageForProposedRect:(NSRect *)rect context:(id)context hints:(id)hints;
- (NSData *)TIFFRepresentation;
@end
CFURLRef OwnershipCreateURL(CFAllocatorRef, CFStringRef, CFURLPathStyle, Boolean);
CFStringRef OwnershipCopyPath(CFURLRef, CFURLPathStyle);
CFStringRef OwnershipUTI(CFStringRef, CFStringRef, CFStringRef);
CFStringRef OwnershipTag(CFStringRef, CFStringRef);
OSType OwnershipOSType(CFStringRef);
NSString *OwnershipFileType(OSType);
CGImageDestinationRef OwnershipDestination(CFMutableDataRef, CFStringRef, size_t, CFDictionaryRef);
void OwnershipAddImage(CGImageDestinationRef, CGImageRef, CFDictionaryRef);
bool OwnershipFinalize(CGImageDestinationRef);

#define NSURL OwnershipURL
#define NSWorkspace OwnershipPlatform
#define NSFileManager OwnershipPlatform
#define NSApplication OwnershipPlatform
#define NSBundle OwnershipPlatform
#define NSAppleEventDescriptor OwnershipPlatform
#define NSImage OwnershipImage
#define CFURLCreateWithFileSystemPath OwnershipCreateURL
#define CFURLCopyFileSystemPath OwnershipCopyPath
#define UTTypeCreatePreferredIdentifierForTag OwnershipUTI
#define UTTypeCopyPreferredTagWithClass OwnershipTag
#define UTGetOSTypeFromString OwnershipOSType
#define NSFileTypeForHFSTypeCode OwnershipFileType
#define CGImageDestinationCreateWithData OwnershipDestination
#define CGImageDestinationAddImage OwnershipAddImage
#define CGImageDestinationFinalize OwnershipFinalize
#define NSWorkspaceMoveOperation @"fixture-move"
#define NSWorkspaceCopyOperation @"fixture-copy"
#define NSWorkspaceLinkOperation @"fixture-link"
#define NSWorkspaceCompressOperation @"fixture-compress"
#define NSWorkspaceDecompressOperation @"fixture-decompress"
#define NSWorkspaceEncryptOperation @"fixture-encrypt"
#define NSWorkspaceDecryptOperation @"fixture-decrypt"
#define NSWorkspaceDestroyOperation @"fixture-destroy"
#define NSWorkspaceRecycleOperation @"fixture-recycle"
#define NSWorkspaceDuplicateOperation @"fixture-duplicate"
