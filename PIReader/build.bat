@echo off

C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe ^
/platform:x86 ^
/reference:"C:\Program Files (x86)\PIPC\PISDK\PublicAssemblies\OSIsoft.PISDK.dll" ^
/reference:"C:\Program Files (x86)\PIPC\PISDK\PublicAssemblies\OSIsoft.PISDKCommon.dll" ^
/reference:"C:\Program Files (x86)\PIPC\PISDK\PublicAssemblies\OSIsoft.PITimeServer.dll" ^
/reference:System.Web.Extensions.dll ^
/out:PIReader.exe ^
Program.cs

pause