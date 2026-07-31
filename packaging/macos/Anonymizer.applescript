-- Anonymizer droplet: single options window after drop (ASObjC + AppKit).
-- Mode is an in-window radio list (not a popup). Checkboxes for review / open.
-- Builds with packaging/macos/install-app.sh (embeds run-anonymize.sh).

use AppleScript version "2.4"
use framework "Foundation"
use framework "AppKit"
use scripting additions

property modeTitles : {¬
	"Remove personal details (recommended)", ¬
	"Remove identity only (keep company names)", ¬
	"Convert to text only (no privacy scrub)"}
property modeArgs : {"strict", "standard", "extract"}

on run
	try
		set theFiles to choose file with prompt "Choose documents to anonymize" with multiple selections allowed
		processFiles(normalizeFileList(theFiles))
	on error errMsg number errNum
		if errNum is -128 then return
		display dialog "Anonymizer: " & errMsg buttons {"OK"} default button 1 with icon stop
	end try
end run

on open theFiles
	try
		processFiles(normalizeFileList(theFiles))
	on error errMsg number errNum
		if errNum is -128 then return
		display dialog "Anonymizer: " & errMsg buttons {"OK"} default button 1 with icon stop
	end try
end open

on normalizeFileList(theFiles)
	try
		if class of theFiles is list then return theFiles
	end try
	return {theFiles}
end normalizeFileList

on filePOSIXPath(fRef)
	try
		return POSIX path of (fRef as alias)
	end try
	try
		return POSIX path of fRef
	end try
	try
		return fRef as text
	end try
	error "Could not read path for dropped file."
end filePOSIXPath

on processFiles(theFiles)
	set fileNames to {}
	set posixFiles to {}
	set nIn to count of theFiles
	repeat with i from 1 to nIn
		set fRef to item i of theFiles
		set pp to filePOSIXPath(fRef)
		if pp ends with "/" then set pp to text 1 thru -2 of pp
		set end of posixFiles to quoted form of pp
		set end of fileNames to do shell script "basename " & quoted form of pp
	end repeat
	set nFiles to count of fileNames
	if nFiles is 0 then return

	-- One window: files + mode list + checkboxes
	set choices to showOptionsPanel(fileNames)
	if choices is missing value then return

	set modeArg to modeArg of choices
	set wantReview to wantReview of choices
	set wantOpen to wantOpen of choices
	if modeArg is "extract" then set wantReview to false

	set helper to resourcePath("run-anonymize.sh")
	set fileArgs to my joinSpace(posixFiles)
	set openEnv to "0"
	if wantOpen then set openEnv to "1"

	if wantReview then
		display notification "Complete the checklist in Terminal (space / enter)." with title "Anonymizer" subtitle "Review"
		set shellLine to "export ANONYMIZER_OPEN=" & openEnv & "; bash " & quoted form of helper & " --review " & modeArg & " " & fileArgs
		set termCmd to shellLine & "; echo; echo '--- Finished. You can close this window. ---'; exec bash"
		tell application "Terminal"
			activate
			do script termCmd
		end tell
		return
	end if

	display notification "Working on " & (nFiles as text) & " file" & pluralS(nFiles) & "…" with title "Anonymizer"

	set shellCmd to "export ANONYMIZER_OPEN=0; bash " & quoted form of helper & " " & modeArg & " " & fileArgs
	set exitCode to 0
	set shellOut to ""
	try
		set shellOut to do shell script shellCmd
	on error errMsg number errNum
		set exitCode to errNum
		set shellOut to errMsg
	end try

	if exitCode is not 0 then
		display dialog "Something went wrong:" & return & return & shellOut buttons {"OK"} default button 1 with icon stop with title "Anonymizer"
		return
	end if

	set outPaths to parseOutputLines(shellOut)
	set nOut to count of outPaths

	if wantOpen and nOut > 0 then
		repeat with p in outPaths
			try
				do shell script "open " & quoted form of p
			end try
		end repeat
	end if

	set resultBody to "Done" & return & return
	if nOut is 0 then
		set resultBody to resultBody & "Finished. Check next to your original files for .md output."
	else
		set resultBody to resultBody & "Created:" & return & fileListSummary(basenameList(outPaths))
	end if

	try
		set doneBtn to button returned of (display dialog resultBody ¬
			buttons {"Show in Finder", "OK"} default button "OK" with title "Anonymizer")
	on error number errNum
		if errNum is -128 then return
		error
	end try
	if doneBtn is "Show in Finder" and nOut > 0 then
		try
			do shell script "open -R " & quoted form of (item 1 of outPaths)
		end try
	end if
end processFiles

-- Single options window: NSAlert + accessory view (radio mode list + checkboxes)
on showOptionsPanel(fileNames)
	set nFiles to count of fileNames
	set header to (nFiles as text) & " document" & pluralS(nFiles) & " ready"
	set filesText to fileListSummary(fileNames)

	set alert to current application's NSAlert's alloc()'s init()
	alert's setMessageText:"Anonymizer"
	alert's setInformativeText:(header & return & "Choose a mode and options, then Start." & return & return & "Output is saved next to each original file. Work stays on this Mac.")
	alert's addButtonWithTitle:"Start"
	alert's addButtonWithTitle:"Cancel"

	-- Accessory layout (AppKit: origin bottom-left)
	set panelW to 420
	set panelH to 300
	set accessory to current application's NSView's alloc()'s initWithFrame:{{0, 0}, {panelW, panelH}}

	-- File names (top)
	set filesField to current application's NSTextField's alloc()'s initWithFrame:{{12, 188}, {panelW - 24, 100}}
	filesField's setStringValue:filesText
	filesField's setEditable:false
	filesField's setBezeled:true
	filesField's setBordered:true
	filesField's setDrawsBackground:true
	filesField's setSelectable:true
	filesField's setFont:(current application's NSFont's systemFontOfSize:11)
	accessory's addSubview:filesField

	-- Mode label
	set modeLabel to current application's NSTextField's alloc()'s initWithFrame:{{12, 162}, {panelW - 24, 18}}
	modeLabel's setStringValue:"Mode"
	modeLabel's setEditable:false
	modeLabel's setBezeled:false
	modeLabel's setDrawsBackground:false
	modeLabel's setFont:(current application's NSFont's boldSystemFontOfSize:12)
	accessory's addSubview:modeLabel

	-- Radio list of all modes (visible together — not a popup)
	set proto to current application's NSButtonCell's alloc()'s init()
	proto's setButtonType:(current application's NSButtonTypeRadio)
	proto's setFont:(current application's NSFont's systemFontOfSize:12)
	proto's setControlSize:(current application's NSControlSizeRegular)
	proto's setWraps:true

	set matrix to current application's NSMatrix's alloc()'s initWithFrame:{{12, 78}, {panelW - 24, 80}} ¬
		mode:(current application's NSRadioModeMatrix) ¬
		prototype:proto ¬
		numberOfRows:3 ¬
		numberOfColumns:1
	matrix's setAutosizesCells:true
	matrix's setMode:(current application's NSRadioModeMatrix)
	repeat with i from 0 to 2
		set cell to matrix's cellAtRow:i column:0
		cell's setTitle:(item (i + 1) of modeTitles)
		cell's setTag:i
	end repeat
	matrix's selectCellAtRow:0 column:0
	matrix's sizeToCells()
	-- After sizeToCells, re-set frame width for long labels
	set mf to matrix's frame()
	set mf's size's width to (panelW - 24)
	set mf's size's height to 80
	set mf's origin's y to 78
	set mf's origin's x to 12
	matrix's setFrame:mf
	matrix's setToolTip:"All modes are listed here — pick one."
	accessory's addSubview:matrix

	-- Review checkbox
	set reviewBox to current application's NSButton's alloc()'s initWithFrame:{{12, 44}, {panelW - 24, 28}}
	reviewBox's setButtonType:(current application's NSButtonTypeSwitch)
	reviewBox's setTitle:"Review findings before saving (opens Terminal checklist)"
	reviewBox's setState:(current application's NSControlStateValueOff)
	reviewBox's setFont:(current application's NSFont's systemFontOfSize:12)
	accessory's addSubview:reviewBox

	-- Open checkbox
	set openBox to current application's NSButton's alloc()'s initWithFrame:{{12, 14}, {panelW - 24, 28}}
	openBox's setButtonType:(current application's NSButtonTypeSwitch)
	openBox's setTitle:"Open result when finished"
	openBox's setState:(current application's NSControlStateValueOn)
	openBox's setFont:(current application's NSFont's systemFontOfSize:12)
	accessory's addSubview:openBox

	alert's setAccessoryView:accessory

	-- Activate so the dialog is frontmost after a drop
	current application's NSApp's activateIgnoringOtherApps:true
	set response to alert's runModal()
	if response is not (current application's NSAlertFirstButtonReturn) then
		return missing value
	end if

	set selRow to matrix's selectedRow() as integer
	if selRow < 0 then set selRow to 0
	if selRow > 2 then set selRow to 0
	set modeArg to item (selRow + 1) of modeArgs

	set wantReview to false
	if (reviewBox's state() as integer) is (current application's NSControlStateValueOn as integer) then
		set wantReview to true
	end if
	-- Also treat raw 1 as on
	if (reviewBox's state() as integer) is 1 then set wantReview to true

	set wantOpen to false
	if (openBox's state() as integer) is (current application's NSControlStateValueOn as integer) then
		set wantOpen to true
	end if
	if (openBox's state() as integer) is 1 then set wantOpen to true

	if modeArg is "extract" then set wantReview to false

	return {modeArg:modeArg, wantReview:wantReview, wantOpen:wantOpen}
end showOptionsPanel

on fileListSummary(names)
	set maxShow to 10
	set s to ""
	set i to 0
	repeat with nm in names
		set i to i + 1
		if i > maxShow then
			set moreCount to (count of names) - maxShow
			set s to s & "• … and " & (moreCount as text) & " more"
			return s
		end if
		set s to s & "• " & (nm as text) & return
	end repeat
	return s
end fileListSummary

on basenameList(paths)
	set names to {}
	repeat with p in paths
		set end of names to do shell script "basename " & quoted form of (p as text)
	end repeat
	return names
end basenameList

on pluralS(n)
	if n is 1 then return ""
	return "s"
end pluralS

on parseOutputLines(shellOut)
	set outPaths to {}
	set AppleScript's text item delimiters to return
	set linesList to text items of shellOut
	set AppleScript's text item delimiters to ""
	repeat with ln in linesList
		set s to ln as text
		if s starts with "OUTPUT:" then
			set p to text 8 thru -1 of s
			if length of p > 0 then set end of outPaths to p
		end if
	end repeat
	return outPaths
end parseOutputLines

on resourcePath(resourceName)
	try
		return POSIX path of (path to resource resourceName)
	end try
	set appPosix to POSIX path of (path to me)
	if appPosix ends with ".app/" or appPosix ends with ".app" then
		set base to appPosix
		if base ends with "/" then set base to text 1 thru -2 of base
		return base & "/Contents/Resources/" & resourceName
	end if
	return (do shell script "dirname " & quoted form of appPosix) & "/" & resourceName
end resourcePath

on joinSpace(lst)
	set AppleScript's text item delimiters to " "
	set s to lst as text
	set AppleScript's text item delimiters to ""
	return s
end joinSpace
