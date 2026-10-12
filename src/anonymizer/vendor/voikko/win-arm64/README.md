# libvoikko 4.3 for Windows ARM64

`libvoikko-1.dll` is Voikko’s VFST backend (morphology only, no HFST), built
for Windows ARM64 because the upstream Windows SDK ships only x86 and x64.

Source: https://www.puimula.org/htp/testing/voikko-sdk/win-crossbuild/libvoikko-4.3+win1/
License: MPL 1.1 / GPL 2+ / LGPL 2.1+ (upstream libvoikko).

The x64 and x86 installers download the upstream DLL instead of using this file.
The Finnish dictionary is downloaded at install time and is not stored here.
