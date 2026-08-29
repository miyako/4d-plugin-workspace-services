//%attributes = {}
//you can also set the icon of a folder
$path:=System folder:C487(Desktop:K41:16)+Generate UUID:C1066+Folder separator:K24:12

CREATE FOLDER:C475($path; *)

$iconPath:=Get 4D folder:C485(Current resources folder:K5:16)+"4d-main.icns"
READ PICTURE FILE:C678($iconPath; $icon)

FILE SET ICON($path; $icon)