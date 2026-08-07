-- Anonymizer droplet: options window after drop (ASObjC + AppKit).
-- Mode + output style on main panel; allow/deny lists in a separate Lists… dialog.
-- Lists persist to ~/.config/anonymizer/config.yaml via lists-io.sh on Done.
-- Builds with packaging/macos/install-app.sh (embeds run-anonymize.sh + lists-io.sh).

use AppleScript version "2.4"
use framework "Foundation"
use framework "AppKit"
use scripting additions

property modeTitles : {¬
	"Remove personal details (recommended)", ¬
	"Remove identity only (keep company names)", ¬
	"Convert to text only (no privacy scrub)"}
property modeArgs : {"strict", "standard", "extract"}
-- Modal result for custom options panel buttons (0=cancel, 1=start, 2=lists)
property optionsModalCode : 0

on clickOptionsStart_(sender)
	set optionsModalCode to 1
	current application's NSApp's stopModal()
end clickOptionsStart_

on clickOptionsLists_(sender)
	set optionsModalCode to 2
	current application's NSApp's stopModal()
end clickOptionsLists_

on clickOptionsCancel_(sender)
	set optionsModalCode to 0
	current application's NSApp's stopModal()
end clickOptionsCancel_

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
	-- Fallback if lists-io.sh / Python unavailable (keep in sync with DEFAULT_ALLOWLIST)
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
	do shell script "printf '%s' " & quoted form of theText & " > " & quoted form of posixPath
end writeTextToFile

on countNonEmptyLines(theText)
	set n to 0
	if theText is missing value then return 0
	if theText is "" then return 0
	set oldDelims to AppleScript's text item delimiters
	set AppleScript's text item delimiters to {return, linefeed}
	set parts to text items of theText
	set AppleScript's text item delimiters to oldDelims
	repeat with p in parts
		set s to p as text
		-- trim leading spaces/tabs
		repeat while (s starts with " ") or (s starts with tab)
			if (length of s) < 2 then
				set s to ""
				exit repeat
			end if
			set s to text 2 thru -1 of s
		end repeat
		if s is not "" then
			if s does not start with "#" then
				set n to n + 1
			end if
		end if
	end repeat
	return n
end countNonEmptyLines

on listsStatusLine(allowText, denyText)
	set nAllow to countNonEmptyLines(allowText)
	set nDeny to countNonEmptyLines(denyText)
	return "Allowlist " & (nAllow as text) & "  ·  Denylist " & (nDeny as text) & "  —  edit with Lists…"
end listsStatusLine

on loadListsFromConfig()
	-- Returns {allowText:..., denyText:...}
	try
		set io to resourcePath("lists-io.sh")
		set raw to do shell script "bash " & quoted form of io & " print"
		set allowText to ""
		set denyText to ""
		set section to ""
		set oldDelims to AppleScript's text item delimiters
		set AppleScript's text item delimiters to {linefeed, return}
		set linesList to text items of raw
		set AppleScript's text item delimiters to oldDelims
		repeat with ln in linesList
			set t to ln as text
			if t is "---ALLOW---" then
				set section to "allow"
			else if t is "---DENY---" then
				set section to "deny"
			else if section is "allow" then
				if allowText is "" then
					set allowText to t
				else
					set allowText to allowText & return & t
				end if
			else if section is "deny" then
				if denyText is "" then
					set denyText to t
				else
					set denyText to denyText & return & t
				end if
			end if
		end repeat
		return {allowText:allowText, denyText:denyText}
	on error
		return {allowText:defaultAllowlistText(), denyText:""}
	end try
end loadListsFromConfig

on saveListsToConfig(allowText, denyText)
	set allowFile to do shell script "mktemp ${TMPDIR:-/tmp}/anonymizer-allow.XXXXXX"
	set denyFile to do shell script "mktemp ${TMPDIR:-/tmp}/anonymizer-deny.XXXXXX"
	writeTextToFile(allowText, allowFile)
	writeTextToFile(denyText, denyFile)
	try
		set io to resourcePath("lists-io.sh")
		do shell script "bash " & quoted form of io & " save --allow-from " & quoted form of allowFile & " --deny-from " & quoted form of denyFile
	on error errMsg
		try
			do shell script "rm -f " & quoted form of allowFile & " " & quoted form of denyFile
		end try
		error errMsg
	end try
	try
		do shell script "rm -f " & quoted form of allowFile & " " & quoted form of denyFile
	end try
end saveListsToConfig

-- Section header: readable primary label (Mode, Output style, …)
on makeLabel(titleText, x, y, w, h)
	set lab to current application's NSTextField's alloc()'s initWithFrame:{{x, y}, {w, h}}
	lab's setStringValue:titleText
	lab's setEditable:false
	lab's setBezeled:false
	lab's setDrawsBackground:false
	lab's setFont:(current application's NSFont's boldSystemFontOfSize:13)
	try
		lab's setTextColor:(current application's NSColor's labelColor())
	end try
	return lab
end makeLabel

-- Supporting copy: secondary, slightly smaller
on makeCaption(titleText, x, y, w, h)
	set lab to current application's NSTextField's alloc()'s initWithFrame:{{x, y}, {w, h}}
	lab's setStringValue:titleText
	lab's setEditable:false
	lab's setBezeled:false
	lab's setDrawsBackground:false
	lab's setFont:(current application's NSFont's systemFontOfSize:12)
	try
		lab's setTextColor:(current application's NSColor's secondaryLabelColor())
	end try
	return lab
end makeCaption

-- Fine print under lists / file meta
on makeFinePrint(titleText, x, y, w, h)
	set lab to current application's NSTextField's alloc()'s initWithFrame:{{x, y}, {w, h}}
	lab's setStringValue:titleText
	lab's setEditable:false
	lab's setBezeled:false
	lab's setDrawsBackground:false
	lab's setFont:(current application's NSFont's systemFontOfSize:11)
	try
		lab's setTextColor:(current application's NSColor's tertiaryLabelColor())
	end try
	return lab
end makeFinePrint

on makeScrollText(initialText, x, y, w, h)
	set scroll to current application's NSScrollView's alloc()'s initWithFrame:{{x, y}, {w, h}}
	scroll's setHasVerticalScroller:true
	scroll's setHasHorizontalScroller:false
	scroll's setAutohidesScrollers:true
	scroll's setBorderType:(current application's NSBezelBorder)
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

-- Read NSTextView contents. Must use |string|() — bare string() is an AppleScript keyword.
on textViewContents(tv)
	try
		set s to (tv's |string|()) as text
		return s
	on error
		try
			return (tv's stringValue() as text)
		on error
			return ""
		end try
	end try
end textViewContents

-- Secondary dialog: edit lists; Done saves to ~/.config/anonymizer/config.yaml
on showListsPanel(allowText, denyText)
	set alert to current application's NSAlert's alloc()'s init()
	applyAlertChrome(alert)
	alert's setInformativeText:"One phrase per line. Allowlist is never redacted; denylist is always redacted. Done saves to ~/.config/anonymizer/config.yaml."
	alert's addButtonWithTitle:"Done"
	alert's addButtonWithTitle:"Cancel"

	-- Match main-panel margins and type scale
	set margin to 16
	set gapLabel to 6
	set gapSection to 18
	set panelW to 460
	set labelH to 18
	set allowBoxH to 112
	set denyBoxH to 112
	set panelH to margin + labelH + gapLabel + allowBoxH + gapSection + labelH + gapLabel + denyBoxH + margin
	set accessory to current application's NSView's alloc()'s initWithFrame:{{0, 0}, {panelW, panelH}}
	set innerW to panelW - margin * 2

	set y to panelH - margin - labelH
	accessory's addSubview:(makeLabel("Allowlist — never redact", margin, y, innerW, labelH))
	set y to y - gapLabel - allowBoxH
	set allowScroll to current application's NSScrollView's alloc()'s initWithFrame:{{margin, y}, {innerW, allowBoxH}}
	allowScroll's setHasVerticalScroller:true
	allowScroll's setHasHorizontalScroller:false
	allowScroll's setAutohidesScrollers:true
	allowScroll's setBorderType:(current application's NSBezelBorder)
	set allowTV to current application's NSTextView's alloc()'s initWithFrame:{{0, 0}, {innerW - 4, allowBoxH - 4}}
	allowTV's setString:allowText
	allowTV's setFont:(current application's NSFont's systemFontOfSize:12)
	allowTV's setRichText:false
	allowTV's setImportsGraphics:false
	allowTV's setEditable:true
	allowTV's setSelectable:true
	allowTV's setVerticallyResizable:true
	allowTV's setHorizontallyResizable:false
	allowTV's textContainer()'s setContainerSize:{innerW - 16, 1.0E+7}
	allowTV's textContainer()'s setWidthTracksTextView:true
	allowScroll's setDocumentView:allowTV
	accessory's addSubview:allowScroll

	set y to y - gapSection - labelH
	accessory's addSubview:(makeLabel("Denylist — always redact", margin, y, innerW, labelH))
	set y to y - gapLabel - denyBoxH
	set denyScroll to current application's NSScrollView's alloc()'s initWithFrame:{{margin, y}, {innerW, denyBoxH}}
	denyScroll's setHasVerticalScroller:true
	denyScroll's setHasHorizontalScroller:false
	denyScroll's setAutohidesScrollers:true
	denyScroll's setBorderType:(current application's NSBezelBorder)
	set denyTV to current application's NSTextView's alloc()'s initWithFrame:{{0, 0}, {innerW - 4, denyBoxH - 4}}
	denyTV's setString:denyText
	denyTV's setFont:(current application's NSFont's systemFontOfSize:12)
	denyTV's setRichText:false
	denyTV's setImportsGraphics:false
	denyTV's setEditable:true
	denyTV's setSelectable:true
	denyTV's setVerticallyResizable:true
	denyTV's setHorizontallyResizable:false
	denyTV's textContainer()'s setContainerSize:{innerW - 16, 1.0E+7}
	denyTV's textContainer()'s setWidthTracksTextView:true
	denyScroll's setDocumentView:denyTV
	accessory's addSubview:denyScroll

	alert's setAccessoryView:accessory
	current application's NSApp's activateIgnoringOtherApps:true
	set response to alert's runModal()
	if response is not (current application's NSAlertFirstButtonReturn) then
		return missing value
	end if

	set newAllow to textViewContents(allowTV)
	set newDeny to textViewContents(denyTV)
	try
		saveListsToConfig(newAllow, newDeny)
	on error errMsg
		display dialog "Could not save lists to config:" & return & return & errMsg buttons {"OK"} default button 1 with icon caution with title "Anonymizer"
	end try
	return {allowText:newAllow, denyText:newDeny}
end showListsPanel

-- Main options panel: clear hierarchy, breathing room, HIG action bar
on showOptionsPanel(fileNames)
	set nFiles to count of fileNames
	set header to (nFiles as text) & " document" & pluralS(nFiles) & " ready"
	set filesText to fileListSummary(fileNames)

	set listState to loadListsFromConfig()
	set allowText to allowText of listState
	set denyText to denyText of listState

	set lastModeRow to 0
	set lastStyleRow to 0
	set lastReview to false
	set lastOpen to true

	-- Design scale (comfortable, not sparse)
	set margin to 24
	set gapXs to 6 -- label → control
	set gapSm to 10 -- related controls
	set gapMd to 16 -- within a section cluster
	set gapLg to 22 -- between major sections
	set gapXl to 28 -- before action bar
	set panelW to 500
	set iconSize to 44
	set titleRowH to iconSize
	set subH to 18
	set filesLabelH to 18
	set filesH to 72
	set modeLabelH to 18
	set modeMatrixH to 90 -- 3 radio rows with room to breathe
	set styleLabelH to 18
	set styleMatrixH to 54 -- 2 radio rows
	set listsLabelH to 18
	set listsStatusH to 16
	set checkH to 22
	set btnH to 32
	set btnW to 96
	set btnGap to 10

	-- Exact height: sum of blocks + gaps (top → bottom)
	set panelH to margin + titleRowH + gapSm + subH + gapLg + filesLabelH + gapXs + filesH + gapLg + modeLabelH + gapXs + modeMatrixH + gapLg + styleLabelH + gapXs + styleMatrixH + gapLg + listsLabelH + gapXs + listsStatusH + gapMd + checkH + gapSm + checkH + gapXl + btnH + margin

	repeat
		set panelRect to current application's NSMakeRect(0, 0, panelW, panelH)
		set thePanel to (current application's NSPanel's alloc())
		set thePanel to (thePanel's initWithContentRect:panelRect styleMask:7 backing:2 defer:false)
		thePanel's setTitle:""
		thePanel's setLevel:8
		thePanel's |center|()

		set content to thePanel's contentView()
		set innerW to panelW - margin * 2

		-- Top-down cursor (AppKit Y grows upward; y is BOTTOM of each block)
		set y to panelH - margin - titleRowH
		addTitleRow(content, panelW, y)

		set y to y - gapSm - subH
		content's addSubview:(makeCaption(header & "  ·  Saves next to original  ·  Private on this Mac", margin, y, innerW, subH))

		set y to y - gapLg - filesLabelH
		content's addSubview:(makeLabel("Files", margin, y, innerW, filesLabelH))

		set y to y - gapXs - filesH
		set filesField to current application's NSTextField's alloc()'s initWithFrame:{{margin, y}, {innerW, filesH}}
		filesField's setStringValue:filesText
		filesField's setEditable:false
		filesField's setBezeled:true
		filesField's setBordered:true
		filesField's setDrawsBackground:true
		filesField's setSelectable:true
		filesField's setFont:(current application's NSFont's systemFontOfSize:12)
		try
			filesField's setTextColor:(current application's NSColor's labelColor())
			filesField's setBackgroundColor:(current application's NSColor's controlBackgroundColor())
		end try
		content's addSubview:filesField

		set y to y - gapLg - modeLabelH
		content's addSubview:(makeLabel("Mode", margin, y, innerW, modeLabelH))

		set y to y - gapXs - modeMatrixH
		set proto to current application's NSButtonCell's alloc()'s init()
		proto's setButtonType:(current application's NSButtonTypeRadio)
		proto's setFont:(current application's NSFont's systemFontOfSize:13)
		proto's setControlSize:(current application's NSControlSizeRegular)
		proto's setWraps:true

		set matrix to current application's NSMatrix's alloc()'s initWithFrame:{{margin, y}, {innerW, modeMatrixH}} ¬
			mode:(current application's NSRadioModeMatrix) ¬
			prototype:proto ¬
			numberOfRows:3 ¬
			numberOfColumns:1
		matrix's setAutosizesCells:true
		matrix's setMode:(current application's NSRadioModeMatrix)
		try
			matrix's setIntercellSpacing:{0, 4}
		end try
		repeat with i from 0 to 2
			set cell to matrix's cellAtRow:i column:0
			cell's setTitle:(item (i + 1) of modeTitles)
			cell's setTag:i
		end repeat
		matrix's selectCellAtRow:lastModeRow column:0
		matrix's setFrame:{{margin, y}, {innerW, modeMatrixH}}
		content's addSubview:matrix

		set y to y - gapLg - styleLabelH
		content's addSubview:(makeLabel("Output style", margin, y, innerW, styleLabelH))

		set y to y - gapXs - styleMatrixH
		set styleProto to current application's NSButtonCell's alloc()'s init()
		styleProto's setButtonType:(current application's NSButtonTypeRadio)
		styleProto's setFont:(current application's NSFont's systemFontOfSize:13)
		styleProto's setWraps:true
		set styleMatrix to current application's NSMatrix's alloc()'s initWithFrame:{{margin, y}, {innerW, styleMatrixH}} ¬
			mode:(current application's NSRadioModeMatrix) ¬
			prototype:styleProto ¬
			numberOfRows:2 ¬
			numberOfColumns:1
		styleMatrix's setAutosizesCells:true
		try
			styleMatrix's setIntercellSpacing:{0, 4}
		end try
		(styleMatrix's cellAtRow:0 column:0)'s setTitle:"Replace with tags  [PERSON_1]"
		(styleMatrix's cellAtRow:0 column:0)'s setTag:0
		(styleMatrix's cellAtRow:1 column:0)'s setTitle:"Delete text entirely (no tags)"
		(styleMatrix's cellAtRow:1 column:0)'s setTag:1
		styleMatrix's selectCellAtRow:lastStyleRow column:0
		styleMatrix's setFrame:{{margin, y}, {innerW, styleMatrixH}}
		content's addSubview:styleMatrix

		set y to y - gapLg - listsLabelH
		content's addSubview:(makeLabel("Custom lists", margin, y, innerW, listsLabelH))
		set y to y - gapXs - listsStatusH
		content's addSubview:(makeFinePrint(listsStatusLine(allowText, denyText), margin, y, innerW, listsStatusH))

		set y to y - gapMd - checkH
		set reviewBox to current application's NSButton's alloc()'s initWithFrame:{{margin, y}, {innerW, checkH}}
		reviewBox's setButtonType:(current application's NSButtonTypeSwitch)
		reviewBox's setTitle:"Review findings before saving (opens Terminal)"
		if lastReview then
			reviewBox's setState:(current application's NSControlStateValueOn)
		else
			reviewBox's setState:(current application's NSControlStateValueOff)
		end if
		reviewBox's setFont:(current application's NSFont's systemFontOfSize:13)
		content's addSubview:reviewBox

		set y to y - gapSm - checkH
		set openBox to current application's NSButton's alloc()'s initWithFrame:{{margin, y}, {innerW, checkH}}
		openBox's setButtonType:(current application's NSButtonTypeSwitch)
		openBox's setTitle:"Open result when finished"
		if lastOpen then
			openBox's setState:(current application's NSControlStateValueOn)
		else
			openBox's setState:(current application's NSControlStateValueOff)
		end if
		openBox's setFont:(current application's NSFont's systemFontOfSize:13)
		content's addSubview:openBox

		-- Action bar (HIG): Cancel left · Lists… + Start right
		set y to margin
		set cancelBtn to makeDialogButton("Cancel", margin, y, btnW, btnH, "clickOptionsCancel:")
		try
			cancelBtn's setKeyEquivalent:(ASCII character 27)
		end try
		set startX to margin + innerW - btnW
		set listsX to startX - btnGap - btnW
		set listsBtn to makeDialogButton("Lists…", listsX, y, btnW, btnH, "clickOptionsLists:")
		set startBtn to makeDialogButton("Start", startX, y, btnW, btnH, "clickOptionsStart:")
		startBtn's setKeyEquivalent:return
		try
			-- Emphasize primary action (blue when focused)
			startBtn's setKeyEquivalentModifierMask:0
		end try
		content's addSubview:cancelBtn
		content's addSubview:listsBtn
		content's addSubview:startBtn

		set optionsModalCode to -1
		current application's NSApp's activateIgnoringOtherApps:true
		thePanel's makeKeyAndOrderFront_(missing value)
		current application's NSApp's runModalForWindow_(thePanel)
		set response to optionsModalCode

		set lastModeRow to matrix's selectedRow() as integer
		if lastModeRow < 0 then set lastModeRow to 0
		if lastModeRow > 2 then set lastModeRow to 0
		set lastStyleRow to styleMatrix's selectedRow() as integer
		if lastStyleRow < 0 then set lastStyleRow to 0
		set lastReview to false
		if (reviewBox's state() as integer) is 1 then set lastReview to true
		if (reviewBox's state() as integer) is (current application's NSControlStateValueOn as integer) then set lastReview to true
		set lastOpen to false
		if (openBox's state() as integer) is 1 then set lastOpen to true
		if (openBox's state() as integer) is (current application's NSControlStateValueOn as integer) then set lastOpen to true

		thePanel's orderOut_(missing value)

		if response is 1 then
			set modeArg to item (lastModeRow + 1) of modeArgs
			set redactStyle to "placeholder"
			if lastStyleRow is 1 then set redactStyle to "remove"
			set wantReview to lastReview
			set wantOpen to lastOpen
			if modeArg is "extract" then set wantReview to false
			return {modeArg:modeArg, wantReview:wantReview, wantOpen:wantOpen, redactStyle:redactStyle, allowText:allowText, denyText:denyText}
		else if response is 2 then
			set edited to showListsPanel(allowText, denyText)
			if edited is not missing value then
				set allowText to allowText of edited
				set denyText to denyText of edited
			end if
		else
			return missing value
		end if
	end repeat
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

on appVersion()
	-- Written at build time from pyproject.toml into Resources/VERSION
	try
		set v to do shell script "tr -d '[:space:]' < " & quoted form of resourcePath("VERSION")
		if v is not "" then return v
	end try
	return "dev"
end appVersion

on appTitle()
	return "Anonymizer (version " & appVersion() & ")"
end appTitle

on dialogIconImage()
	try
		set iconPath to resourcePath("Anonymizer-dialog.png")
		set img to current application's NSImage's alloc()'s initByReferencingFile:iconPath
		if img is missing value then return missing value
		return img
	on error
		return missing value
	end try
end dialogIconImage

-- Compact chrome for secondary NSAlert (Lists): squircle icon + title on system title line
on applyAlertChrome(alertRef)
	alertRef's setMessageText:appTitle()
	set img to dialogIconImage()
	if img is not missing value then alertRef's setIcon:img
end applyAlertChrome

-- Title strip: squircle + version, vertically centered. yBottom = bottom of row.
-- Returns row height used (for layout math). Keep margin in sync with showOptionsPanel.
on addTitleRow(parentView, panelW, yBottom)
	set margin to 24
	set iconSize to 44
	set iconGap to 14
	set titleH to 22
	set rowH to iconSize
	set iconY to yBottom
	set titleY to yBottom + ((iconSize - titleH) / 2)

	set img to dialogIconImage()
	if img is not missing value then
		set iv to current application's NSImageView's alloc()'s initWithFrame:{{margin, iconY}, {iconSize, iconSize}}
		iv's setImage:img
		iv's setImageScaling:(current application's NSImageScaleProportionallyUpOrDown)
		iv's setEditable:false
		parentView's addSubview:iv
	end if

	set titleField to current application's NSTextField's alloc()'s initWithFrame:{{margin + iconSize + iconGap, titleY}, {panelW - margin * 2 - iconSize - iconGap, titleH}}
	titleField's setStringValue:appTitle()
	titleField's setEditable:false
	titleField's setBezeled:false
	titleField's setDrawsBackground:false
	titleField's setFont:(current application's NSFont's boldSystemFontOfSize:17)
	titleField's setSelectable:false
	try
		titleField's setTextColor:(current application's NSColor's labelColor())
	end try
	parentView's addSubview:titleField
	return rowH
end addTitleRow

on makeDialogButton(titleText, x, y, w, h, actionName)
	set btn to current application's NSButton's alloc()'s initWithFrame:{{x, y}, {w, h}}
	btn's setTitle:titleText
	btn's setBezelStyle:(current application's NSBezelStyleRounded)
	btn's setControlSize:(current application's NSControlSizeRegular)
	btn's setFont:(current application's NSFont's systemFontOfSize:13)
	btn's setTarget:me
	btn's setAction:actionName
	return btn
end makeDialogButton

on joinSpace(lst)
	set AppleScript's text item delimiters to " "
	set s to lst as text
	set AppleScript's text item delimiters to ""
	return s
end joinSpace
