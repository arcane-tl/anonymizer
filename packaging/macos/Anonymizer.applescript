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

	-- One window: mode, output style, allow/deny lists, review/open
	set choices to showOptionsPanel(fileNames)
	if choices is missing value then return

	set modeArg to modeArg of choices
	set wantReview to wantReview of choices
	set wantOpen to wantOpen of choices
	set redactStyle to redactStyle of choices
	set allowText to allowText of choices
	set denyText to denyText of choices
	if modeArg is "extract" then set wantReview to false
	if redactStyle is "remove" then set wantReview to false

	set helper to resourcePath("run-anonymize.sh")
	set fileArgs to my joinSpace(posixFiles)
	set openEnv to "0"
	if wantOpen then set openEnv to "1"

	-- Temp list files for helper (--allow-from / --deny-from)
	set allowFile to do shell script "mktemp ${TMPDIR:-/tmp}/anonymizer-allow.XXXXXX"
	set denyFile to do shell script "mktemp ${TMPDIR:-/tmp}/anonymizer-deny.XXXXXX"
	writeTextToFile(allowText, allowFile)
	writeTextToFile(denyText, denyFile)

	set extraOpts to " --redact-style " & quoted form of redactStyle & " --allow-from " & quoted form of allowFile & " --deny-from " & quoted form of denyFile

	if wantReview then
		display notification "Complete the checklist in Terminal (space / enter)." with title "Anonymizer" subtitle "Review"
		set shellLine to "export ANONYMIZER_OPEN=" & openEnv & "; bash " & quoted form of helper & " --review" & extraOpts & " " & modeArg & " " & fileArgs & "; rm -f " & quoted form of allowFile & " " & quoted form of denyFile
		set termCmd to shellLine & "; echo; echo '--- Finished. You can close this window. ---'; exec bash"
		tell application "Terminal"
			activate
			do script termCmd
		end tell
		return
	end if

	display notification "Working on " & (nFiles as text) & " file" & pluralS(nFiles) & "…" with title "Anonymizer"

	set shellCmd to "export ANONYMIZER_OPEN=0; bash " & quoted form of helper & extraOpts & " " & modeArg & " " & fileArgs & "; rm -f " & quoted form of allowFile & " " & quoted form of denyFile
	set exitCode to 0
	set shellOut to ""
	try
		set shellOut to do shell script shellCmd
	on error errMsg number errNum
		set exitCode to errNum
		set shellOut to errMsg
		try
			do shell script "rm -f " & quoted form of allowFile & " " & quoted form of denyFile
		end try
	end try

	if exitCode is not 0 then
		display dialog "Something went wrong:" & return & return & shellOut buttons {"OK"} default button 1 with icon stop with title "Anonymizer"
		return
	end if

	set outPaths to parseOutputLines(shellOut)
	set nOut to count of outPaths

	-- User already chose "Open result when finished" in the options panel:
	-- open the file(s) and stop — no second dialog (Show in Finder / OK).
	if wantOpen then
		if nOut > 0 then
			repeat with p in outPaths
				try
					do shell script "open " & quoted form of p
				end try
			end repeat
			display notification "Opened " & (nOut as text) & " result file" & pluralS(nOut) & "." with title "Anonymizer" subtitle "Done"
		else
			display notification "Finished. Look next to your original files for .md." with title "Anonymizer" subtitle "Done"
		end if
		return
	end if

	-- Open was unchecked: one result dialog so they can still reveal in Finder
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

on defaultAllowlistText()
	-- Keep in sync with anonymizer.anonymize.config.DEFAULT_ALLOWLIST
	return "Y-tunnus
Y tunnus
Hetu
Henkilötunnus
ALV-numero
ALV numero
ALV
VAT
IBAN
Email
Phone"
end defaultAllowlistText

on writeTextToFile(theText, posixPath)
	set quotedPath to quoted form of posixPath
	-- Use printf %s for full UTF-8 text without interpreting escapes oddly
	do shell script "printf '%s' " & quoted form of theText & " > " & quotedPath
end writeTextToFile

on makeLabel(titleText, x, y, w, h)
	set lab to current application's NSTextField's alloc()'s initWithFrame:{{x, y}, {w, h}}
	lab's setStringValue:titleText
	lab's setEditable:false
	lab's setBezeled:false
	lab's setDrawsBackground:false
	lab's setFont:(current application's NSFont's boldSystemFontOfSize:12)
	return lab
end makeLabel

on makeScrollText(initialText, x, y, w, h)
	set scroll to current application's NSScrollView's alloc()'s initWithFrame:{{x, y}, {w, h}}
	scroll's setHasVerticalScroller:true
	scroll's setHasHorizontalScroller:false
	scroll's setAutohidesScrollers:true
	scroll's setBorderType:(current application's NSBezelBorder)
	set contentSize to scroll's contentSize()
	-- contentSize may be a record; use fixed frame for text view
	set tv to current application's NSTextView's alloc()'s initWithFrame:{{0, 0}, {w - 4, h - 4}}
	tv's setString:initialText
	tv's setFont:(current application's NSFont's systemFontOfSize:11)
	tv's setRichText:false
	tv's setImportsGraphics:false
	tv's setEditable:true
	tv's setSelectable:true
	tv's setVerticallyResizable:true
	tv's setHorizontallyResizable:false
	tv's setAutoresizingMask:(current application's NSViewWidthSizable)
	tv's textContainer()'s setContainerSize:{w - 16, 1.0E+7}
	tv's textContainer()'s setWidthTracksTextView:true
	scroll's setDocumentView:tv
	return {scroll:scroll, textView:tv}
end makeScrollText

-- Single options window: mode, redaction style, allow/deny, review/open
on showOptionsPanel(fileNames)
	set nFiles to count of fileNames
	set header to (nFiles as text) & " document" & pluralS(nFiles) & " ready"
	set filesText to fileListSummary(fileNames)

	set alert to current application's NSAlert's alloc()'s init()
	alert's setMessageText:"Anonymizer"
	alert's setInformativeText:(header & return & "Choose options, then Start. Output is saved next to each original file.")
	alert's addButtonWithTitle:"Start"
	alert's addButtonWithTitle:"Cancel"

	-- Accessory layout (AppKit: origin bottom-left). Taller for lists.
	set panelW to 460
	set panelH to 520
	set accessory to current application's NSView's alloc()'s initWithFrame:{{0, 0}, {panelW, panelH}}

	-- File names (top)
	set filesField to current application's NSTextField's alloc()'s initWithFrame:{{12, 430}, {panelW - 24, 78}}
	filesField's setStringValue:filesText
	filesField's setEditable:false
	filesField's setBezeled:true
	filesField's setBordered:true
	filesField's setDrawsBackground:true
	filesField's setSelectable:true
	filesField's setFont:(current application's NSFont's systemFontOfSize:11)
	accessory's addSubview:filesField

	accessory's addSubview:(makeLabel("Mode", 12, 408, panelW - 24, 18))

	set proto to current application's NSButtonCell's alloc()'s init()
	proto's setButtonType:(current application's NSButtonTypeRadio)
	proto's setFont:(current application's NSFont's systemFontOfSize:12)
	proto's setControlSize:(current application's NSControlSizeRegular)
	proto's setWraps:true

	set matrix to current application's NSMatrix's alloc()'s initWithFrame:{{12, 330}, {panelW - 24, 76}} ¬
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
	matrix's setFrame:{{12, 330}, {panelW - 24, 76}}
	accessory's addSubview:matrix

	accessory's addSubview:(makeLabel("Output style", 12, 308, panelW - 24, 18))

	set styleProto to current application's NSButtonCell's alloc()'s init()
	styleProto's setButtonType:(current application's NSButtonTypeRadio)
	styleProto's setFont:(current application's NSFont's systemFontOfSize:12)
	styleProto's setWraps:true
	set styleMatrix to current application's NSMatrix's alloc()'s initWithFrame:{{12, 268}, {panelW - 24, 38}} ¬
		mode:(current application's NSRadioModeMatrix) ¬
		prototype:styleProto ¬
		numberOfRows:2 ¬
		numberOfColumns:1
	styleMatrix's setAutosizesCells:true
	(styleMatrix's cellAtRow:0 column:0)'s setTitle:"Replace with tags  [PERSON_1]"
	(styleMatrix's cellAtRow:0 column:0)'s setTag:0
	(styleMatrix's cellAtRow:1 column:0)'s setTitle:"Delete text entirely (no tags)"
	(styleMatrix's cellAtRow:1 column:0)'s setTag:1
	styleMatrix's selectCellAtRow:0 column:0
	styleMatrix's setFrame:{{12, 268}, {panelW - 24, 38}}
	accessory's addSubview:styleMatrix

	accessory's addSubview:(makeLabel("Allowlist — never redact (one per line)", 12, 246, panelW - 24, 18))
	set allowPair to makeScrollText(defaultAllowlistText(), 12, 168, panelW - 24, 74)
	accessory's addSubview:(scroll of allowPair)

	accessory's addSubview:(makeLabel("Denylist — always redact (one per line)", 12, 146, panelW - 24, 18))
	set denyPair to makeScrollText("", 12, 68, panelW - 24, 74)
	accessory's addSubview:(scroll of denyPair)

	set reviewBox to current application's NSButton's alloc()'s initWithFrame:{{12, 36}, {panelW - 24, 26}}
	reviewBox's setButtonType:(current application's NSButtonTypeSwitch)
	reviewBox's setTitle:"Review findings before saving (tags only; opens Terminal)"
	reviewBox's setState:(current application's NSControlStateValueOff)
	reviewBox's setFont:(current application's NSFont's systemFontOfSize:12)
	accessory's addSubview:reviewBox

	set openBox to current application's NSButton's alloc()'s initWithFrame:{{12, 10}, {panelW - 24, 26}}
	openBox's setButtonType:(current application's NSButtonTypeSwitch)
	openBox's setTitle:"Open result when finished"
	openBox's setState:(current application's NSControlStateValueOn)
	openBox's setFont:(current application's NSFont's systemFontOfSize:12)
	accessory's addSubview:openBox

	alert's setAccessoryView:accessory

	current application's NSApp's activateIgnoringOtherApps:true
	set response to alert's runModal()
	if response is not (current application's NSAlertFirstButtonReturn) then
		return missing value
	end if

	set selRow to matrix's selectedRow() as integer
	if selRow < 0 then set selRow to 0
	if selRow > 2 then set selRow to 0
	set modeArg to item (selRow + 1) of modeArgs

	set styleRow to styleMatrix's selectedRow() as integer
	if styleRow < 0 then set styleRow to 0
	set redactStyle to "placeholder"
	if styleRow is 1 then set redactStyle to "remove"

	set allowText to ((textView of allowPair)'s string()) as text
	set denyText to ((textView of denyPair)'s string()) as text

	set wantReview to false
	if (reviewBox's state() as integer) is (current application's NSControlStateValueOn as integer) then set wantReview to true
	if (reviewBox's state() as integer) is 1 then set wantReview to true

	set wantOpen to false
	if (openBox's state() as integer) is (current application's NSControlStateValueOn as integer) then set wantOpen to true
	if (openBox's state() as integer) is 1 then set wantOpen to true

	if modeArg is "extract" then set wantReview to false
	if redactStyle is "remove" then set wantReview to false

	return {modeArg:modeArg, wantReview:wantReview, wantOpen:wantOpen, redactStyle:redactStyle, allowText:allowText, denyText:denyText}
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
