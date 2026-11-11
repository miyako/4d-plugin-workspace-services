#include "4DPluginAPI.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"
#include <cstdio>
#include <cstdlib>
#include <set>
#include <type_traits>

static void require(bool ok, const char *message) {
    if (!ok) { fprintf(stderr, "%s\n", message); std::exit(1); }
}
static void denied() { require(false, "unexpected platform operation"); }
static NSString *sample;
static bool platformFailure;
static unsigned platformCalls;
static int urlOwners, platformOwners;
@implementation OwnershipURL
- (id)initWithString:(NSString *)value {
    self=[super init]; if (self) { _text=[value copy]; ++urlOwners; } return self;
}
- (id)initFileURLWithPath:(NSString *)value { return [self initWithString:value]; }
+ (id)fileURLWithPath:(NSString *)value {
    return [[[self alloc] initWithString:value] autorelease];
}
- (NSString *)absoluteString { return _text; }
- (void)dealloc { --urlOwners; [_text release]; [super dealloc]; }
@end
CFURLRef OwnershipCreateURL(CFAllocatorRef, CFStringRef text, CFURLPathStyle, Boolean) {
    return (CFURLRef)[[OwnershipURL alloc] initWithString:(NSString *)text];
}
CFStringRef OwnershipCopyPath(CFURLRef value, CFURLPathStyle) {
    return (CFStringRef)[[(OwnershipURL *)value absoluteString] copy];
}
CFStringRef OwnershipUTI(CFStringRef, CFStringRef, CFStringRef) { return (CFStringRef)[sample copy]; }
CFStringRef OwnershipTag(CFStringRef, CFStringRef) { return (CFStringRef)[sample copy]; }
OSType OwnershipOSType(CFStringRef) { return 0; }
NSString *OwnershipFileType(OSType) { return sample; }
CGImageDestinationRef OwnershipDestination(CFMutableDataRef, CFStringRef, size_t, CFDictionaryRef) {
    denied(); return nullptr;
}
void OwnershipAddImage(CGImageDestinationRef, CGImageRef, CFDictionaryRef) { denied(); }
bool OwnershipFinalize(CGImageDestinationRef) { denied(); return false; }
@implementation OwnershipImage
- (NSSize)size { denied(); return NSZeroSize; }
- (void)setSize:(NSSize)value { denied(); }
- (id)initWithCGImage:(CGImageRef)image size:(NSSize)size { denied(); return nil; }
- (CGImageRef)CGImageForProposedRect:(NSRect *)rect context:(id)context hints:(id)hints {
    denied(); return nullptr;
}
- (NSData *)TIFFRepresentation { denied(); return nil; }
@end
@implementation OwnershipPlatform
- (id)init { self=[super init]; if (self) ++platformOwners; return self; }
- (void)dealloc { --platformOwners; [super dealloc]; }
+ (OwnershipPlatform *)sharedWorkspace { ++platformCalls; return [[[self alloc] init] autorelease]; }
+ (OwnershipPlatform *)sharedApplication { ++platformCalls; return [[[self alloc] init] autorelease]; }
+ (OwnershipPlatform *)defaultManager { ++platformCalls; return [[[self alloc] init] autorelease]; }
+ (OwnershipPlatform *)bundleWithPath:(NSString *)path { return [[[self alloc] init] autorelease]; }
+ (id)nullDescriptor { return nil; }
- (NSString *)absolutePathForAppBundleWithIdentifier:(NSString *)value {
    return platformFailure ? nil : sample;
}
- (NSString *)fullPathForApplication:(NSString *)value { return platformFailure ? nil : sample; }
- (NSString *)bundleIdentifier { return sample; }
- (BOOL)launchAppWithBundleIdentifier:(NSString *)value options:(NSUInteger)options
       additionalEventParamDescriptor:(id)event launchIdentifier:(void *)identifier { return YES; }
- (BOOL)openURLs:(NSArray *)urls withAppBundleIdentifier:(NSString *)value
         options:(NSUInteger)options additionalEventParamDescriptor:(id)event
launchIdentifiers:(void *)identifiers {
    require([urls count]==2, "synthetic launch paths"); return YES;
}
- (BOOL)openFile:(NSString *)path withApplication:(NSString *)application
  andDeactivate:(BOOL)deactivate { return !platformFailure; }
- (BOOL)performFileOperation:(NSString *)operation source:(NSString *)source
                destination:(NSString *)destination files:(NSArray *)files tag:(NSInteger *)tag {
    require([files count]==2, "synthetic Finder inputs"); *tag=0; return !platformFailure;
}
- (OwnershipImage *)iconForFileType:(NSString *)type { return nil; }
- (OwnershipImage *)iconForFile:(NSString *)file { return nil; }
- (BOOL)setIcon:(id)icon forFile:(NSString *)file options:(NSUInteger)options {
    denied(); return NO;
}
- (BOOL)getInfoForFile:(NSString *)file application:(NSString **)application type:(NSString **)type {
    *application=sample; *type=sample; return !platformFailure;
}
- (NSString *)displayNameAtPath:(NSString *)path { return sample; }
- (NSArray *)contentsOfDirectoryAtPath:(NSString *)path error:(NSError **)error {
    return platformFailure ? nil : @[sample, sample];
}
- (NSArray *)subpathsOfDirectoryAtPath:(NSString *)path error:(NSError **)error {
    return [self contentsOfDirectoryAtPath:path error:error];
}
- (OwnershipPlatform *)dockTile { return self; }
- (void)setBadgeLabel:(NSString *)value { require([value isEqualToString:sample], "badge input"); }
- (NSString *)badgeLabel { return sample; }
- (OwnershipImage *)applicationIconImage { return nil; }
- (void)setApplicationIconImage:(id)image { denied(); }
@end

static std::set<PA_Unichar *> strings;
static std::map<PA_Picture, int> pictures;
static std::map<PA_Handle, size_t> handles;
static bool nullEmpty, commandFailure, handleFailure, creationFailure, owningResult;
static CUTF16String fixture, conversionType;
static unsigned commandCount, pointerReads;
static PA_Unistring makeString(const CUTF16String &text) {
    PA_Unistring value={};
    if (text.empty() && nullEmpty) return value;
    value.fLength=text.size();
    value.fString=new PA_Unichar[text.size()+1];
    std::copy(text.begin(),text.end(),value.fString);
    value.fString[text.size()]=0;
    strings.insert(value.fString);
    return value;
}
static CUTF16String content(PA_Unistring value) {
    require(!value.fString || strings.count(value.fString), "read dead string");
    require(value.fString || !value.fLength, "null nonempty string");
    require(!value.fString || value.fString[value.fLength]==0, "missing string terminator");
    return value.fLength ? CUTF16String(value.fString,value.fLength) : CUTF16String();
}
static void disposeString(PA_Unistring value) {
    if (!value.fString) return;
    require(strings.erase(value.fString)==1,"duplicate/unowned string disposal");
    delete[] value.fString;
}
static PA_Picture makePicture() { auto p=new char; pictures[p]=1; return p; }
static void releasePicture(PA_Picture p) {
    if (!p) return;
    auto found=pictures.find(p);
    require(found!=pictures.end(),"unowned picture disposal");
    if (--found->second==0) { pictures.erase(found); delete static_cast<char *>(p); }
}
static void clear(PA_Variable *v) {
    switch (v->fType) {
    case eVK_Unistring: disposeString(v->uValue.fString); break;
    case eVK_Picture: releasePicture(v->uValue.fPicture); break;
    case eVK_ArrayUnicode: {
        auto h=v->uValue.fArray.fData;
        if (h) {
            auto values=reinterpret_cast<PA_Unistring *>(*h);
            for (long i=0;i<=v->uValue.fArray.fNbElements;++i) disposeString(values[i]);
            PA_DisposeHandle(h);
        }
        break;
    }
    case eVK_Undefined: case eVK_Longint: break;
    default: require(false,"unexpected clear kind");
    }
    v->fType=eVK_Undefined;
}
static void engine(short selector, EngineBlock *eb) {
    switch (selector) {
    case EX_CREATE_UNISTRING:
        eb->fUniString1=makeString(CUTF16String(reinterpret_cast<PA_Unichar *>(eb->fHandle)));
        break;
    case EX_SET_UNISTRING: {
        CUTF16String copy(reinterpret_cast<PA_Unichar *>(eb->fHandle));
        disposeString(eb->fUniString1); eb->fUniString1=makeString(copy); break;
    }
    case EX_DISPOSE_UNISTRING: disposeString(eb->fUniString1); break;
    case EX_CREATE_PICTURE:
        eb->fPicture=creationFailure ? reinterpret_cast<void *>(99) : makePicture();
        eb->fError=creationFailure ? eER_IncompatibleTypes : eER_NoErr; break;
    case EX_CREATE_NATIVE_PICTURE_FOR_SCREEN: eb->fHandle=nullptr; eb->fError=eER_NoErr; break;
    case EX_DISPOSE_PICTURE: releasePicture(eb->fPicture); break;
    case EX_DUPLICATE_PICTURE:
        require(eb->fParam1==0,"unexpected deep duplication");
        if (eb->fPicture) {
            require(pictures.count(eb->fPicture),"retain dead picture"); ++pictures[eb->fPicture];
        }
        break;
    case EX_GET_PICTURE_DATA:
        require(pictures.count(eb->fPicture),"query dead picture");
        eb->fError=eER_IncompatibleTypes;
        // A failed return is unspecified; it must not be adopted or disposed.
        eb->fUniString1.fString=reinterpret_cast<PA_Unichar *>(99); break;
    case EX_CLEAR_VARIABLE: clear(static_cast<PA_Variable *>(eb->fPtr1)); break;
    case EX_HANDLE_MANAGER: {
        eb->fError=0; auto h=eb->fHandle;
        switch (eb->fParam1) {
        case 1:
            if (handleFailure) { eb->fHandle=nullptr; eb->fError=eER_IncompatibleTypes; break; }
            h=new char *; *h=new char[eb->fParam2]();
            handles[h]=eb->fParam2; eb->fHandle=h; break;
        case 2:
            require(handles.erase(h)==1,"dispose unowned handle"); delete[] *h; delete h; break;
        case 3: {
            require(handles.count(h),"resize unowned handle"); size_t size=eb->fParam2;
            char *data=new char[size](); memcpy(data,*h,std::min(size,handles[h]));
            delete[] *h; *h=data; handles[h]=size; break;
        }
        case 4: require(handles.count(h),"size unowned handle"); eb->fParam2=handles[h]; break;
        case 5: require(handles.count(h),"lock unowned handle"); eb->fParam3=(sLONG_PTR)*h; break;
        case 6: require(handles.count(h),"unlock unowned handle"); break;
        default: denied();
        }
        break;
    }
    case EX_CONVERT_CHARSET_TO_CHARSET: {
        require(eb->fParam2==eVTC_UTF_8 && eb->fParam4==eVTC_UTF_16,"converter encoding");
        NSString *s=[[[NSString alloc] initWithBytes:eb->fPtr1 length:eb->fParam1
                                          encoding:NSUTF8StringEncoding] autorelease];
        require(s!=nil,"converter input");
        size_t bytes=[s length]*sizeof(PA_Unichar);
        require(bytes<=static_cast<size_t>(eb->fParam3),"converter byte capacity");
        [s getCharacters:static_cast<unichar *>(eb->fPtr2) range:NSMakeRange(0,[s length])];
        eb->fParam3=bytes; eb->fError=eER_NoErr; break;
    }
    case EX_EXECUTE_COMMAND_BY_ID: {
        ++commandCount; auto args=static_cast<PA_Variable **>(eb->fPtr1);
        eb->fError=commandFailure ? eER_IncompatibleTypes : eER_NoErr;
        auto result=static_cast<PA_Variable *>(eb->fPtr2);
        if (commandFailure) {
            result->fType=0; result->uValue.fString.fString=reinterpret_cast<PA_Unichar *>(99);
            break;
        }
        result->fType=eVK_Undefined;
        if (owningResult) { auto s=makeString(fixture); PA_SetStringVariable(result,&s); }
        switch (eb->fParam1) {
        case 678:
            require(eb->fParam2==2 && content(args[0]->uValue.fString)==fixture,"path content/length");
            clear(args[1]); PA_SetPictureVariable(args[1],makePicture()); break;
        case 1002:
            require(eb->fParam2==2 && content(args[1]->uValue.fString)==conversionType,
                    "conversion type content/units"); break;
        case 988: require(eb->fParam2==2,"gray arguments"); break;
        case 457:
            require(eb->fParam2==3,"size arguments");
            PA_SetLongintVariable(args[1],13); PA_SetLongintVariable(args[2],17); break;
        case 679:
            require(eb->fParam2==4,"thumbnail arguments");
            clear(args[1]); PA_SetPictureVariable(args[1],makePicture()); break;
        default: denied();
        }
        break;
    }
    case EX_GET_POINTER_VALUE_PROPERTIES:
        eb->fParam1=eVK_Unistring; eb->fParam2=fixture.size(); eb->fParam3=0;
        eb->fError=eER_NoErr; break;
    case EX_GET_INFORMATION: eb->fParam1=0; break;
    case EX_GET_POINTER_VALUE: {
        ++pointerReads;
        auto v=static_cast<PA_Variable *>(static_cast<void *>(eb->fHandle));
        auto s=makeString(fixture); PA_SetStringVariable(v,&s); eb->fError=eER_NoErr; break;
    }
    default: require(false,"unexpected engine selector");
    }
}
static void balanced() {
    require(strings.empty(),"unbalanced string allocations");
    require(pictures.empty(),"unbalanced picture references");
    require(handles.empty(),"unbalanced handles");
    puts("strings=0 pictures=0 handles=0");
}
static void pictureCase(const char *name) {
    {
        CPicture p;
        if (!strcmp(name,"path")) {
            CUTF8String text; C_TEXT source;
            source.setUTF16String(fixture.c_str(),fixture.size()); source.copyUTF8String(&text);
            p.fromFileAtPath(&text);
        } else if (!strcmp(name,"bytes") || !strcmp(name,"creation-failure")) {
            auto original=p.getPicture(); creationFailure=!strcmp(name,"creation-failure");
            const uint8_t bytes[]={1,2,3}; p.setBytes(bytes,sizeof(bytes));
            if (creationFailure) {
                require(PA_GetLastError()==eER_IncompatibleTypes,"creation error lost");
                require(p.getPicture()==original,"creation failure replaced owner");
            } else require(pictures[p.getPicture()]==1,"creation owner not released");
        } else if (!strcmp(name,"gray")) {
            auto result=p.createGrayScale(); PA_DisposePicture(result);
        } else if (!strcmp(name,"copy")) {
            auto result=p.createCopy([sample UTF8String]); PA_DisposePicture(result);
        } else if (!strcmp(name,"size")) {
            unsigned width=0,height=0; p.getSize(&width,&height);
            require(width==(!commandFailure && !handleFailure ? 13u : 0u),"size width");
            require(height==(!commandFailure && !handleFailure ? 17u : 0u),"size height");
        } else if (!strcmp(name,"thumbnail")) {
            auto result=p.createThumbnail(3,5); PA_DisposePicture(result);
        } else denied();
        require(pictures.count(p.getPicture()),"wrapper lost picture");
    }
    balanced();
}
static void arrayCase() {
    PA_Variable array=PA_CreateVariable(eVK_ArrayUnicode);
    BytePtr params[]={reinterpret_cast<BytePtr>(&array)};
    {
        ARRAY_TEXT text; text.setSize(1); text.appendUTF16String(fixture.c_str(),fixture.size());
        for (int repeat=0;repeat<3;++repeat) {
            text.toParamAtIndex(params,1);
            std::vector<CUTF16String> churn(128,fixture);
            require(content(PA_GetStringInArray(array,1))==fixture,"array after churn");
            ARRAY_TEXT copy; copy.fromParamAtIndex(params,1);
            auto replacement=makeString(CUTF16String()); PA_SetStringInArray(array,1,&replacement);
            CUTF16String read; copy.copyUTF16StringAtIndex(&read,1);
            require(read==fixture,"borrowed array copied before mutation");
        }
        PA_ResizeArray(&array,0);
    }
    PA_ClearVariable(&array);
    {
        ARRAY_TEXT text; text.setSize(1); text.appendUTF16String(fixture.c_str(),fixture.size());
        array=PA_CreateVariable(eVK_Undefined); text.toParamAtIndex(params,1);
        require(content(PA_GetStringInArray(array,1))==fixture,"undefined array adoption");
        PA_ClearVariable(&array);
    }
    auto value=makeString(fixture);
    auto wrong=PA_CreateVariable(eVK_Longint); PA_SetStringInArray(wrong,0,&value);
    PA_DisposeUnistring(&value);
    array=PA_CreateVariable(eVK_ArrayUnicode); value=makeString(fixture);
    PA_SetStringInArray(array,-1,&value); PA_SetStringInArray(array,1,&value);
    auto noData=array; noData.uValue.fArray.fData=nullptr; PA_SetStringInArray(noData,0,&value);
    PA_SetStringInArray(array,0,nullptr); PA_SetStringInArray(array,0,&value);
    require(content(PA_GetStringInArray(array,0))==fixture,"index zero transfer");
    PA_ClearVariable(&array); balanced();
}
static void scalarCase() {
    {
        C_TEXT text; text.setUTF16String(fixture.c_str(),fixture.size());
        auto value=makeString(CUTF16String()); BytePtr params[]={reinterpret_cast<BytePtr>(&value)};
        text.toParamAtIndex(params,1); require(content(value)==fixture,"scalar output");
        C_TEXT copy; copy.fromParamAtIndex(params,1); PA_DisposeUnistring(&value);
        require(CUTF16String(copy.getUTF16StringPtr(),copy.getUTF16Length())==fixture,"scalar copy");
        value=makeString(CUTF16String()); sLONG_PTR result=reinterpret_cast<sLONG_PTR>(&value);
        copy.setReturn(&result); require(content(value)==fixture,"scalar return");
        PA_DisposeUnistring(&value);
    }
    balanced();
}
static void pointerCase() {
    PointerBlock block={}; block.fClass=1; block.fScope=1;
    block.uValue.fVariable.fTag=41; block.uValue.fVariable.fIndice=9;
    block.uValue.fVariable.fName[0]='x';
    C_POINTER pointer; BytePtr params[]={reinterpret_cast<BytePtr>(&block)};
    pointer.fromParamAtIndex(params,1);
    PA_Variable expected={},actual={};
    PA_SetVariableOrFieldReference(&expected,&block); pointer.getVariable(&actual);
    require(!pointerReads,"reference helper fetched an owning value");
    require(actual.fType==expected.fType && actual.fFiller==expected.fFiller &&
            actual.uValue.fVariableDefinition.fTag==41 &&
            actual.uValue.fVariableDefinition.fIndice==9 &&
            actual.uValue.fVariableDefinition.fType==expected.uValue.fVariableDefinition.fType &&
            !memcmp(actual.uValue.fVariableDefinition.fName,expected.uValue.fVariableDefinition.fName,
                    sizeof(actual.uValue.fVariableDefinition.fName)),"SDK reference metadata");
    balanced();
}
static void dispatcherCase() {
    for (int selector=1;selector<=18;++selector) {
        int variants=selector==1 ? 10 : selector==2 ? 4 : 3;
        for (int variant=0;variant<variants;++variant) {
            auto input=makeString(fixture),second=makeString(fixture),output=makeString(CUTF16String());
            auto array=PA_CreateVariable(eVK_ArrayUnicode); PA_ResizeArray(&array,2);
            for (int i=1;i<=2;++i) { auto value=makeString(fixture); PA_SetStringInArray(array,i,&value); }
            PA_long32 number=variant,pictureResultStorage=0;
            PA_Picture picture=nullptr;
            BytePtr args[4]={reinterpret_cast<BytePtr>(&input),reinterpret_cast<BytePtr>(&second),
                            reinterpret_cast<BytePtr>(&number),reinterpret_cast<BytePtr>(&number)};
            sLONG_PTR result=reinterpret_cast<sLONG_PTR>(&output);
            switch (selector) {
            case 1: args[2]=reinterpret_cast<BytePtr>(&array); break;
            case 2: case 3: case 4: args[1]=reinterpret_cast<BytePtr>(&number); break;
            case 5: args[1]=reinterpret_cast<BytePtr>(&number);
                    args[2]=reinterpret_cast<BytePtr>(&array); break;
            case 9: args[1]=reinterpret_cast<BytePtr>(&picture); break;
            case 14: args[0]=reinterpret_cast<BytePtr>(&picture); break;
            case 15: args[0]=args[1]=reinterpret_cast<BytePtr>(&number); break;
            case 17: case 18: args[1]=reinterpret_cast<BytePtr>(&array); break;
            }
            bool textResult=selector==3 || selector==6 || selector==8 || selector==13;
            if (!textResult) result=pictureResultStorage;
            CommandDispatcher(selector,&result,args);
            if (textResult) {
                CUTF16String expected=fixture;
                if ((selector==3 || selector==8) && platformFailure) expected.clear();
                if (selector==3 && variant==0 && !platformFailure) expected.push_back(':');
                require(content(output)==expected,"dispatcher scalar output");
            }
            if (selector==17 || selector==18) {
                require(array.uValue.fArray.fNbElements==(platformFailure ? 0 : 2),"folder row count");
                if (!platformFailure) {
                    NSMutableString *full=[[sample mutableCopy] autorelease];
                    if (![full hasSuffix:@"/"]) [full appendString:@"/"];
                    [full appendString:sample];
                    if (variant==0) [full appendString:@":"];
                    CUTF16String expected([full length],0);
                    if (!expected.empty()) [full getCharacters:&expected[0] range:NSMakeRange(0,[full length])];
                    require(content(PA_GetStringInArray(array,1))==expected,"folder text");
                }
            }
            PA_ClearVariable(&array); PA_DisposeUnistring(&input);
            PA_DisposeUnistring(&second); PA_DisposeUnistring(&output);
        }
    }
    require(platformCalls>0,"dispatcher boundary not exercised"); balanced();
}
template<class T,bool copyable=std::is_copy_constructible<T>::value> struct CopyCase {
    static void run() { T original; { T copy(original); } }
};
template<class T> struct CopyCase<T,false> {
    static void run() { static_assert(!std::is_copy_assignable<T>::value,"copy assignment disabled"); }
};
static void traitsCase(const char *name) {
#define CHECK_TYPE(type) if (!strcmp(name,#type)) { CopyCase<type>::run(); balanced(); return; }
    CHECK_TYPE(ARRAY_BOOLEAN) CHECK_TYPE(ARRAY_DATE) CHECK_TYPE(ARRAY_INTEGER)
    CHECK_TYPE(ARRAY_LONGINT) CHECK_TYPE(ARRAY_REAL) CHECK_TYPE(ARRAY_TEXT) CHECK_TYPE(ARRAY_TIME)
    CHECK_TYPE(C_BLOB) CHECK_TYPE(CPicture) CHECK_TYPE(C_PICTURE) CHECK_TYPE(C_TEXT)
#undef CHECK_TYPE
    require(!strcmp(name,"values"),"unknown copy case");
    static_assert(std::is_copy_constructible<CBytes>::value,"value bytes");
    static_assert(std::is_copy_constructible<C_DATE>::value,"value date");
    static_assert(std::is_copy_constructible<C_INTEGER>::value,"value integer");
    static_assert(std::is_copy_constructible<C_LONGINT>::value,"value longint");
    static_assert(std::is_copy_constructible<C_REAL>::value,"value real");
    static_assert(std::is_copy_constructible<C_TIME>::value,"value time");
    static_assert(std::is_copy_constructible<C_POINTER>::value,"borrowed pointer");
    balanced();
}
int main(int argc,char **argv) {
    @autoreleasepool {
        require(argc==5,"arguments"); gCall4D=engine;
        nullEmpty=!strcmp(argv[3],"null"); commandFailure=!strcmp(argv[4],"command");
        handleFailure=!strcmp(argv[4],"handle"); owningResult=!strcmp(argv[4],"owned-result");
        platformFailure=!strcmp(argv[4],"denied");
        sample=[NSString stringWithUTF8String:argv[2]];
        fixture.resize([sample length]);
        if (!fixture.empty()) [sample getCharacters:&fixture[0] range:NSMakeRange(0,[sample length])];
        conversionType=fixture;
        if (!strcmp(argv[1],"traits")) traitsCase(argv[2]);
        else if (!strcmp(argv[1],"arrays")) arrayCase();
        else if (!strcmp(argv[1],"scalar")) scalarCase();
        else if (!strcmp(argv[1],"pointer")) pointerCase();
        else if (!strcmp(argv[1],"dispatch")) dispatcherCase();
        else pictureCase(argv[1]);
    }
    require(!urlOwners && !platformOwners,"unbalanced synthetic platform owners");
    puts("urls=0 platform-objects=0");
}
