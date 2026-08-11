-- Anonymizer droplet: options window after drop (ASObjC + AppKit).
-- Mode + output style/format on main panel; Templates… opens a native
-- AppKit Templates panel (same chrome as options; data via templates-io.sh).
-- Builds with packaging/macos/install-app.sh.

use AppleScript version "2.4"
use framework "Foundation"
use framework "AppKit"
use scripting additions

property modeTitles : {¬
	"Strict - Remove all sensitive data (recommended)", ¬
	"Standard - Remove sensitive personal data", ¬
	"Extract - Keep all the data"}
property modeArgs : {"strict", "standard", "extract"}
property styleTitles : {¬
	"Replace redacted data with stable placeholders", ¬
	"Delete redacted data"}
property styleArgs : {"placeholder", "remove"}
property formatTitles : {¬
	"Markdown", ¬
	"Source filetype", ¬
	"Both (Markdown & source filetype)"}
property formatArgs : {"md", "source", "both"}
-- Modal result for custom options panel buttons (0=cancel, 1=start, 2=lists)
property optionsModalCode : 0
-- "options" | "templates" | "editPack" — which panel owns windowShouldClose_ / stopModal
property currentModalKind : "options"
-- Templates enable list (0=cancel, 1=done, 3=rebuild list after new/delete)
property templatesModalCode : 0
property tmplPacks : missing value
property tmplEnableBoxes : {}
property tmplListPanel : missing value
-- Edit-pack sheet/panel
property editModalCode : 0
property editPackId : ""
property editAllowTV : missing value
property editDenyTV : missing value
property editTitleLabel : missing value
property editTitleField : missing value
property editTitlePencil : missing value
property editDescLabel : missing value
property editDescScroll : missing value
property editDescTV : missing value
property editDescPencil : missing value
property editTitleEditing : false
property editDescEditing : false
property editSaveBtn : missing value
property editCloseBtn : missing value
-- After duplicate, enable the new template on list rebuild
property templatesExtraEnableId : ""

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

on clickTemplatesDone_(sender)
	set templatesModalCode to 1
	current application's NSApp's stopModal()
end clickTemplatesDone_

on clickTemplatesCancel_(sender)
	set templatesModalCode to 0
	current application's NSApp's stopModal()
end clickTemplatesCancel_

on clickTemplatesNew_(sender)
	templatesCreateAndEdit()
end clickTemplatesNew_

on clickTemplatesEdit_(sender)
	set idx to 0
	try
		set idx to sender's tag() as integer
	end try
	set tid to packIdAtIndex(idx)
	if tid is "" then return
	showEditPackPanel(tid)
	set templatesModalCode to 3
	current application's NSApp's stopModal()
end clickTemplatesEdit_

on clickTemplatesDuplicate_(sender)
	set idx to 0
	try
		set idx to sender's tag() as integer
	end try
	set tid to packIdAtIndex(idx)
	if tid is "" then return
	try
		set newId to templatesIO("fork " & quoted form of tid)
		set newId to trimWhitespace(newId)
		set templatesExtraEnableId to newId
		set templatesModalCode to 3
		current application's NSApp's stopModal()
	on error errMsg
		display dialog "Could not duplicate template:" & return & return & errMsg buttons {"OK"} default button 1 with icon stop with title "Anonymizer"
	end try
end clickTemplatesDuplicate_

on clickTemplatesDelete_(sender)
	set idx to 0
	try
		set idx to sender's tag() as integer
	end try
	set p to packAtIndex(idx)
	if p is missing value then return
	set isBuiltin to false
	try
		set isBuiltin to (p's objectForKey:"builtin") as boolean
	end try
	if isBuiltin then
		display dialog "Builtin templates cannot be deleted." buttons {"OK"} default button 1 with icon note with title "Anonymizer"
		return
	end if
	set tid to textFromObj(p's objectForKey:"id")
	set ttl to textFromObj(p's objectForKey:"title")
	try
		display dialog "Delete template “" & ttl & "”?" & return & "This cannot be undone." buttons {"Cancel", "Delete"} default button "Cancel" with icon caution with title "Anonymizer"
	on error
		return
	end try
	try
		templatesIO("delete " & quoted form of tid)
		set templatesModalCode to 3
		current application's NSApp's stopModal()
	on error errMsg
		display dialog "Could not delete template:" & return & return & errMsg buttons {"OK"} default button 1 with icon stop with title "Anonymizer"
	end try
end clickTemplatesDelete_

on clickEditSave_(sender)
	editSaveCurrent()
end clickEditSave_

on clickEditClose_(sender)
	set editModalCode to 0
	current application's NSApp's stopModal()
end clickEditClose_

on clickEditTitleLabel_(sender)
	if editTitleEditing then return
	beginTitleEdit()
end clickEditTitleLabel_

on clickEditDescLabel_(sender)
	if editDescEditing then return
	beginDescEdit()
end clickEditDescLabel_

on beginTitleEdit()
	if editTitleField is missing value or editTitleLabel is missing value then return
	try
		endDescEdit()
	end try
	try
		set t to (editTitleLabel's stringValue() as text)
		editTitleField's setStringValue:t
		editTitleLabel's setHidden:true
		editTitleField's setHidden:false
		editTitleField's |window|()'s makeFirstResponder:editTitleField
		editTitleField's selectText:(missing value)
		set editTitleEditing to true
	end try
end beginTitleEdit

on endTitleEdit()
	if editTitleField is missing value or editTitleLabel is missing value then return
	if not editTitleEditing then return
	try
		set t to trimWhitespace(editTitleField's stringValue() as text)
		if t is "" then set t to (editTitleLabel's stringValue() as text)
		editTitleLabel's setStringValue:t
		editTitleField's setHidden:true
		editTitleLabel's setHidden:false
		set editTitleEditing to false
	end try
end endTitleEdit

on beginDescEdit()
	if editDescTV is missing value or editDescLabel is missing value then return
	try
		endTitleEdit()
	end try
	try
		set t to (editDescLabel's stringValue() as text)
		if t is "No description" then set t to ""
		editDescTV's setString:t
		editDescLabel's setHidden:true
		if editDescScroll is not missing value then editDescScroll's setHidden:false
		editDescTV's |window|()'s makeFirstResponder:editDescTV
		set editDescEditing to true
	end try
end beginDescEdit

on endDescEdit()
	if editDescTV is missing value or editDescLabel is missing value then return
	if not editDescEditing then return
	try
		set t to textViewContents(editDescTV)
		set showT to t
		if showT is "" then set showT to "No description"
		editDescLabel's setStringValue:showT
		if editDescScroll is not missing value then editDescScroll's setHidden:true
		editDescLabel's setHidden:false
		set editDescEditing to false
	end try
end endDescEdit

-- Hide title/description editors as soon as focus leaves them
on controlTextDidEndEditing_(notification)
	try
		set obj to notification's |object|()
		if editTitleEditing and editTitleField is not missing value then
			if (obj is editTitleField) or (obj's isEqualTo:editTitleField) then endTitleEdit()
		end if
	end try
end controlTextDidEndEditing_

on textDidEndEditing_(notification)
	try
		set obj to notification's |object|()
		if editDescEditing and editDescTV is not missing value then
			if (obj is editDescTV) or (obj's isEqualTo:editDescTV) then endDescEdit()
		end if
	end try
end textDidEndEditing_

on addClickAndHover(viewRef, clickAction)
	-- Click to edit; pointing-hand cursor on hover
	try
		set gr to current application's NSClickGestureRecognizer's alloc()'s initWithTarget:me action:clickAction
		viewRef's addGestureRecognizer:gr
	end try
	try
		set opts to (current application's NSTrackingMouseEnteredAndExited as integer)
		set opts to opts + (current application's NSTrackingActiveAlways as integer)
		set opts to opts + (current application's NSTrackingInVisibleRect as integer)
		set ta to current application's NSTrackingArea's alloc()'s initWithRect:{0, 0, 0, 0} options:opts owner:me userInfo:(missing value)
		viewRef's addTrackingArea:ta
	end try
end addClickAndHover

on mouseEntered_(theEvent)
	try
		current application's NSCursor's pointingHandCursor()'s |push|()
	end try
end mouseEntered_

on mouseExited_(theEvent)
	try
		current application's NSCursor's |pop|()
	end try
end mouseExited_

on descAreaHeightForText(t, maxW)
	-- Dynamic height so description is fully readable (scroll only if very long)
	set raw to t as text
	if raw is "" or raw is "No description" then return 36
	set h to heightForWrappingText(raw, maxW, 12)
	if h < 36 then set h to 36
	if h > 280 then set h to 280
	return h
end descAreaHeightForText

on currentEditTitle()
	if editTitleEditing and editTitleField is not missing value then
		return trimWhitespace(editTitleField's stringValue() as text)
	end if
	if editTitleLabel is not missing value then
		return trimWhitespace(editTitleLabel's stringValue() as text)
	end if
	return ""
end currentEditTitle

on currentEditDescription()
	set t to ""
	if editDescEditing and editDescTV is not missing value then
		set t to textViewContents(editDescTV)
	else if editDescLabel is not missing value then
		set t to editDescLabel's stringValue() as text
	end if
	if t is "No description" then return ""
	return t
end currentEditDescription

-- Red traffic-light (×) must end the modal session (same as Cancel).
-- Without stopModal, runModalForWindow_ never returns and the droplet zombies.
on windowShouldClose_(sender)
	if currentModalKind is "editPack" then
		set editModalCode to 0
	else if currentModalKind is "templates" then
		set templatesModalCode to 0
	else
		set optionsModalCode to 0
	end if
	current application's NSApp's stopModal()
	return true
end windowShouldClose_

-- Allow ⌘Q while the options panel is modal.
on applicationShouldTerminate_(sender)
	try
		current application's NSApp's stopModal()
	end try
	set optionsModalCode to 0
	return current application's NSTerminateNow
end applicationShouldTerminate_

on quitAnonymizerApp()
	-- Droplets can linger after AppKit modal; exit once open/run is done.
	try
		current application's NSApp's terminate_(missing value)
	on error
		try
			tell me to quit
		end try
	end try
end quitAnonymizerApp

on run
	try
		set theFiles to choose file with prompt "Choose documents to anonymize" with multiple selections allowed
		processFiles(normalizeFileList(theFiles))
	on error errMsg number errNum
		if errNum is -128 then
			quitAnonymizerApp()
			return
		end if
		display dialog "Anonymizer: " & errMsg buttons {"OK"} default button 1 with icon stop
	end try
	quitAnonymizerApp()
end run

on open theFiles
	try
		processFiles(normalizeFileList(theFiles))
	on error errMsg number errNum
		if errNum is -128 then
			quitAnonymizerApp()
			return
		end if
		display dialog "Anonymizer: " & errMsg buttons {"OK"} default button 1 with icon stop
	end try
	quitAnonymizerApp()
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

	-- One window: mode, style, format, templates, review/open
	set choices to showOptionsPanel(fileNames)
	if choices is missing value then return

	set modeArg to modeArg of choices
	set wantReview to wantReview of choices
	set wantOpen to wantOpen of choices
	set outputFormat to outputFormat of choices
	set redactStyle to redactStyle of choices
	set templateCSV to templateCSV of choices
	if modeArg is "extract" then
		set wantReview to false
		-- Extract has no native redaction
		set outputFormat to "md"
	end if

	set helper to resourcePath("run-anonymize.sh")
	set fileArgs to my joinSpace(posixFiles)
	set openEnv to "0"
	if wantOpen then set openEnv to "1"

	set extraOpts to " --redact-style " & quoted form of redactStyle & " --format " & quoted form of outputFormat
	if templateCSV is not "" then set extraOpts to extraOpts & " --template " & quoted form of templateCSV

	if wantReview then
		display notification "Review window will open after analysis." with title "Anonymizer" subtitle "Review"
		set shellLine to "export ANONYMIZER_OPEN=" & openEnv & "; bash " & quoted form of helper & " --review" & extraOpts & " " & modeArg & " " & fileArgs
		set termCmd to shellLine & "; echo; echo '--- Finished. You can close this window. ---'; exec bash"
		tell application "Terminal"
			activate
			do script termCmd
		end tell
		return
	end if

	display notification "Working on " & (nFiles as text) & " file" & pluralS(nFiles) & "…" with title "Anonymizer"

	set shellCmd to "export ANONYMIZER_OPEN=0; bash " & quoted form of helper & extraOpts & " " & modeArg & " " & fileArgs
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
		set resultBody to resultBody & "Finished. Check next to your original files for Markdown and/or redacted source output."
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
	-- Fallback if lists-io.sh / Python unavailable.
	-- Prefer domain_lexicon seeds; keep short form labels if Python is down.
	return "Y-tunnus
Y tunnus
Hetu
Henkilötunnus
ALV-numero
ALV numero
ALV
VAT
IBAN
BIC
SWIFT
Email
E-mail
Sähköposti
Phone
Puhelin
Address
Osoite
Postinumero
Name
Nimi
Asiakas
Myyjä
Ostaja
Toimittaja
Tilaaja
Osapuoli
Client
Customer
Supplier
Force Majeure
Letter of Intent
Green Card"
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

on templatesStatusLine(templateCSV)
	-- Ids only (wraps in UI); no count prefix / Templates… suffix
	if templateCSV is "" then return "No templates selected"
	set AppleScript's text item delimiters to ","
	set parts to text items of templateCSV
	set AppleScript's text item delimiters to ""
	set shown to ""
	repeat with p in parts
		if shown is not "" then set shown to shown & ", "
		set shown to shown & (p as text)
	end repeat
	return shown
end templatesStatusLine

on heightForWrappingText(titleText, maxW, fontSize)
	-- Measure multi-line height for fine-print status
	try
		set ns to current application's NSString's stringWithString:(titleText as text)
		set fnt to current application's NSFont's systemFontOfSize:fontSize
		set attrs to current application's NSDictionary's dictionaryWithObject:fnt forKey:(current application's NSFontAttributeName)
		set opts to (current application's NSStringDrawingUsesLineFragmentOrigin) as integer
		set rect to ns's boundingRectWithSize:{maxW, 1.0E+4} options:opts attributes:attrs
		set rList to rect as list
		set h to item 2 of item 2 of rList
		if h < 18 then set h to 18
		if h > 96 then set h to 96
		return (h as integer) + 4
	on error
		return 36
	end try
end heightForWrappingText

on makeWrappingFinePrint(titleText, x, y, w, h)
	set lab to current application's NSTextField's alloc()'s initWithFrame:{{x, y}, {w, h}}
	lab's setStringValue:titleText
	lab's setEditable:false
	lab's setBezeled:false
	lab's setBordered:false
	lab's setDrawsBackground:false
	lab's setFont:(current application's NSFont's systemFontOfSize:11)
	try
		lab's setTextColor:(current application's NSColor's tertiaryLabelColor())
	end try
	try
		lab's setAlignment:(current application's NSTextAlignmentLeft)
		lab's cell()'s setWraps:true
		lab's cell()'s setScrollable:false
		lab's setLineBreakMode:(current application's NSLineBreakByWordWrapping)
		lab's setMaximumNumberOfLines:0
	end try
	return lab
end makeWrappingFinePrint

on loadEnabledTemplatesCSV()
	try
		set io to resourcePath("templates-io.sh")
		return do shell script "bash " & quoted form of io & " print-enabled"
	on error
		try
			set out to do shell script "export PATH=\"$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH\"; anonymize templates print-enabled 2>/dev/null"
			return out
		on error
			return "en-field-labels,en-legal-boilerplate,fi-field-labels,fi-legal-boilerplate"
		end try
	end try
end loadEnabledTemplatesCSV

on templatesIO(args)
	-- args is a shell fragment after the script path (already quoted pieces)
	set io to resourcePath("templates-io.sh")
	return do shell script "bash " & quoted form of io & " " & args
end templatesIO

on parseJSON(jsonStr)
	set s to current application's NSString's stringWithString:(jsonStr as text)
	set d to s's dataUsingEncoding:(current application's NSUTF8StringEncoding)
	set obj to current application's NSJSONSerialization's JSONObjectWithData:d options:0 |error|:(missing value)
	if obj is missing value then error "Could not parse templates JSON"
	return obj
end parseJSON

on textFromObj(obj)
	try
		if obj is missing value then return ""
		return obj as text
	on error
		return ""
	end try
end textFromObj

on packAtIndex(idx)
	if tmplPacks is missing value then return missing value
	set n to tmplPacks's |count|() as integer
	if idx < 0 or idx >= n then return missing value
	return tmplPacks's objectAtIndex:idx
end packAtIndex

on packIdAtIndex(idx)
	set p to packAtIndex(idx)
	if p is missing value then return ""
	return textFromObj(p's objectForKey:"id")
end packIdAtIndex

on joinLines(arr)
	set out to ""
	try
		set n to arr's |count|() as integer
		set i to 0
		repeat while i < n
			set oneLine to textFromObj(arr's objectAtIndex:i)
			if out is "" then
				set out to oneLine
			else
				set out to out & return & oneLine
			end if
			set i to i + 1
		end repeat
		return out
	on error
		set out to ""
		repeat with oneLine in arr
			if out is "" then
				set out to oneLine as text
			else
				set out to out & return & (oneLine as text)
			end if
		end repeat
		return out
	end try
end joinLines

on templatesReloadPacks()
	set raw to templatesIO("list")
	set tmplPacks to parseJSON(raw)
end templatesReloadPacks

on templatesCollectEnabledCSV()
	set csv to ""
	repeat with itemRef in tmplEnableBoxes
		set packId to packId of itemRef
		set btn to btn of itemRef
		set onState to false
		try
			if (btn's state() as integer) is 1 then set onState to true
			if (btn's state() as integer) is (current application's NSControlStateValueOn as integer) then set onState to true
		end try
		if onState then
			if csv is "" then
				set csv to packId
			else
				set csv to csv & "," & packId
			end if
		end if
	end repeat
	return csv
end templatesCollectEnabledCSV

on trimWhitespace(s)
	set t to s as text
	try
		set t to do shell script "printf %s " & quoted form of t & " | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'"
	end try
	return t
end trimWhitespace

on csvContainsId(csv, tid)
	set AppleScript's text item delimiters to ","
	set parts to text items of csv
	set AppleScript's text item delimiters to ""
	repeat with p in parts
		if (p as text) is tid then return true
	end repeat
	return false
end csvContainsId

on csvAddId(csv, tid)
	if tid is "" then return csv
	if csvContainsId(csv, tid) then return csv
	if csv is "" then return tid
	return csv & "," & tid
end csvAddId

on templatesCreateAndEdit()
	-- No name dialog: placeholder "New template", user renames in Edit
	try
		set newId to templatesIO("new")
		set newId to trimWhitespace(newId)
		set templatesExtraEnableId to newId
		showEditPackPanel(newId)
		set templatesModalCode to 3
		current application's NSApp's stopModal()
	on error errMsg
		display dialog "Could not create template:" & return & return & errMsg buttons {"OK"} default button 1 with icon stop with title "Anonymizer"
	end try
end templatesCreateAndEdit

on loadPackDict(packId)
	set raw to templatesIO("get " & quoted form of packId)
	return parseJSON(raw)
end loadPackDict

on editSaveCurrent()
	if editPackId is "" then return
	set p to missing value
	try
		set p to loadPackDict(editPackId)
	end try
	if p is missing value then return
	set isBuiltin to false
	try
		set isBuiltin to (p's objectForKey:"builtin") as boolean
	end try
	if isBuiltin then
		display dialog "Builtin templates are read-only. Use the copy icon in the list to duplicate one." buttons {"OK"} default button 1 with icon note with title "Anonymizer"
		return
	end if
	try
		endTitleEdit()
		endDescEdit()
	end try
	set titleText to currentEditTitle()
	if titleText is "" then
		display dialog "Name is required." buttons {"OK"} default button 1 with icon caution with title "Anonymizer"
		return
	end if
	set descText to currentEditDescription()
	set allowText to textViewContents(editAllowTV)
	set denyText to textViewContents(editDenyTV)
	set allowFile to do shell script "mktemp ${TMPDIR:-/tmp}/anonymizer-allow.XXXXXX"
	set denyFile to do shell script "mktemp ${TMPDIR:-/tmp}/anonymizer-deny.XXXXXX"
	set titleFile to do shell script "mktemp ${TMPDIR:-/tmp}/anonymizer-title.XXXXXX"
	set descFile to do shell script "mktemp ${TMPDIR:-/tmp}/anonymizer-desc.XXXXXX"
	try
		do shell script "printf %s " & quoted form of allowText & " > " & quoted form of allowFile
		do shell script "printf %s " & quoted form of denyText & " > " & quoted form of denyFile
		do shell script "printf %s " & quoted form of titleText & " > " & quoted form of titleFile
		do shell script "printf %s " & quoted form of descText & " > " & quoted form of descFile
		templatesIO("save " & quoted form of editPackId & " --allow-from " & quoted form of allowFile & " --deny-from " & quoted form of denyFile & " --title-from " & quoted form of titleFile & " --description-from " & quoted form of descFile)
		set editModalCode to 1
		current application's NSApp's stopModal()
	on error errMsg
		display dialog "Could not save template:" & return & return & errMsg buttons {"OK"} default button 1 with icon stop with title "Anonymizer"
	end try
	try
		do shell script "rm -f " & quoted form of allowFile & " " & quoted form of denyFile & " " & quoted form of titleFile & " " & quoted form of descFile
	end try
end editSaveCurrent

on makeInlineTitleLabel(initialText, x, y, w, h)
	set lab to current application's NSTextField's alloc()'s initWithFrame:{{x, y}, {w, h}}
	lab's setStringValue:initialText
	lab's setEditable:false
	lab's setSelectable:false
	lab's setBezeled:false
	lab's setBordered:false
	lab's setDrawsBackground:false
	lab's setFont:(current application's NSFont's boldSystemFontOfSize:15)
	try
		lab's setTextColor:(current application's NSColor's labelColor())
		lab's setLineBreakMode:(current application's NSLineBreakByTruncatingTail)
		lab's setToolTip:"Click to edit name"
	end try
	return lab
end makeInlineTitleLabel

on makeInlineDescLabel(initialText, x, y, w, h)
	set lab to current application's NSTextField's alloc()'s initWithFrame:{{x, y}, {w, h}}
	lab's setStringValue:initialText
	lab's setEditable:false
	lab's setSelectable:false
	lab's setBezeled:false
	lab's setBordered:false
	lab's setDrawsBackground:false
	lab's setFont:(current application's NSFont's systemFontOfSize:12)
	try
		lab's setTextColor:(current application's NSColor's secondaryLabelColor())
		lab's cell()'s setWraps:true
		lab's setLineBreakMode:(current application's NSLineBreakByWordWrapping)
		lab's setMaximumNumberOfLines:0
		lab's setToolTip:"Click to edit description"
	end try
	return lab
end makeInlineDescLabel

on makeInlineTitleField(initialText, x, y, w, h)
	set fillC to wellFillColor()
	set field to current application's NSTextField's alloc()'s initWithFrame:{{x, y}, {w, h}}
	field's setStringValue:initialText
	field's setEditable:true
	field's setSelectable:true
	field's setBezeled:false
	field's setBordered:false
	field's setDrawsBackground:true
	field's setFont:(current application's NSFont's boldSystemFontOfSize:15)
	field's setHidden:true
	field's setDelegate:me
	try
		field's setTextColor:(current application's NSColor's labelColor())
		field's setBackgroundColor:fillC
		field's setFocusRingType:(current application's NSFocusRingTypeNone)
	end try
	applyRoundedWell(field, 6)
	return field
end makeInlineTitleField

-- Focused edit panel. Click name/description to edit in place.
on showEditPackPanel(packId)
	set editPackId to packId
	set prevKind to currentModalKind
	set editTitleEditing to false
	set editDescEditing to false
	set p to missing value
	try
		set p to loadPackDict(editPackId)
	on error errMsg
		display dialog "Could not load template:" & return & return & errMsg buttons {"OK"} default button 1 with icon stop with title "Anonymizer"
		set currentModalKind to prevKind
		return
	end try
	if p is missing value then
		set currentModalKind to prevKind
		return
	end if

	set isBuiltin to false
	try
		set isBuiltin to (p's objectForKey:"builtin") as boolean
	end try
	set tmplTitle to textFromObj(p's objectForKey:"title")
	set tmplDesc to textFromObj(p's objectForKey:"description")
	set allowText to joinLines(p's objectForKey:"allow")
	set denyText to joinLines(p's objectForKey:"deny")

	set margin to 24
	set gapXs to 6
	set gapSm to 10
	set gapMd to 16
	set gapLg to 22
	set gapXl to 28
	set panelW to 500
	set iconSize to 44
	set titleRowH to iconSize
	set nameRowH to 26
	set fieldLabelH to 18
	set helpH to 16
	set boxH to 100
	set btnH to 32
	set btnW to 110
	set btnGap to 10
	set innerW to panelW - margin * 2
	set descShow to tmplDesc
	if descShow is "" then set descShow to "No description"
	set descRowH to descAreaHeightForText(descShow, innerW)

	set panelH to margin + titleRowH + gapSm + nameRowH + gapXs + descRowH + gapLg + fieldLabelH + gapXs + helpH + gapXs + boxH + gapMd + fieldLabelH + gapXs + helpH + gapXs + boxH + gapXl + btnH + margin

	set panelRect to current application's NSMakeRect(0, 0, panelW, panelH)
	set editPanel to (current application's NSPanel's alloc())
	set editPanel to (editPanel's initWithContentRect:panelRect styleMask:7 backing:2 defer:false)
	editPanel's setTitle:""
	editPanel's setLevel:9
	editPanel's setDelegate:me
	editPanel's setReleasedWhenClosed:false
	try
		editPanel's setPreventsApplicationTerminationWhenModal:false
	end try
	editPanel's |center|()

	set content to editPanel's contentView()

	set y to panelH - margin - titleRowH
	addTitleRowNamed(content, panelW, y, "Edit template")

	-- Name: bold label; user clicks to edit in place
	set y to y - gapSm - nameRowH
	set editTitleLabel to makeInlineTitleLabel(tmplTitle, margin, y, innerW, nameRowH)
	content's addSubview:editTitleLabel
	if isBuiltin then
		content's addSubview:(makeFinePrint("builtin", margin + innerW - 54, y + 4, 54, 16))
		set editTitleField to missing value
	else
		set editTitleField to makeInlineTitleField(tmplTitle, margin, y, innerW, nameRowH)
		content's addSubview:editTitleField
		addClickAndHover(editTitleLabel, "clickEditTitleLabel:")
	end if
	set editTitlePencil to missing value

	-- Description: full height for text; click to edit (user)
	set y to y - gapXs - descRowH
	set editDescLabel to makeInlineDescLabel(descShow, margin, y, innerW, descRowH)
	content's addSubview:editDescLabel
	if isBuiltin then
		set editDescTV to missing value
		set editDescScroll to missing value
	else
		set descPair to makeScrollText(tmplDesc, margin, y, innerW, descRowH)
		set editDescScroll to scroll of descPair
		set editDescTV to textView of descPair
		try
			editDescTV's setDelegate:me
		end try
		editDescScroll's setHidden:true
		content's addSubview:editDescScroll
		addClickAndHover(editDescLabel, "clickEditDescLabel:")
	end if
	set editDescPencil to missing value

	set y to y - gapLg - fieldLabelH
	content's addSubview:(makeLabel("Never redact (allow)", margin, y, innerW, fieldLabelH))
	set y to y - gapXs - helpH
	content's addSubview:(makeFinePrint("One word or phrase per line.", margin, y, innerW, helpH))
	set y to y - gapXs - boxH
	set allowPair to makeScrollText(allowText, margin, y, innerW, boxH)
	content's addSubview:(scroll of allowPair)
	set editAllowTV to textView of allowPair
	editAllowTV's setEditable:(not isBuiltin)

	set y to y - gapMd - fieldLabelH
	content's addSubview:(makeLabel("Always redact (deny)", margin, y, innerW, fieldLabelH))
	set y to y - gapXs - helpH
	content's addSubview:(makeFinePrint("One word or phrase per line.", margin, y, innerW, helpH))
	set y to y - gapXs - boxH
	set denyPair to makeScrollText(denyText, margin, y, innerW, boxH)
	content's addSubview:(scroll of denyPair)
	set editDenyTV to textView of denyPair
	editDenyTV's setEditable:(not isBuiltin)

	set y to margin
	if isBuiltin then
		set editCloseBtn to makeDialogButton("Close", margin + innerW - btnW, y, btnW, btnH, "clickEditClose:")
		content's addSubview:editCloseBtn
		try
			editCloseBtn's setKeyEquivalent:return
		end try
	else
		set saveX to margin + innerW - btnW
		set cancelX to saveX - btnGap - btnW
		set cancelBtn to makeDialogButton("Cancel", cancelX, y, btnW, btnH, "clickEditClose:")
		try
			cancelBtn's setKeyEquivalent:(ASCII character 27)
		end try
		set editSaveBtn to makeDialogButton("Save", saveX, y, btnW, btnH, "clickEditSave:")
		try
			editSaveBtn's setKeyEquivalent:return
		end try
		content's addSubview:cancelBtn
		content's addSubview:editSaveBtn
	end if

	set editModalCode to -1
	set currentModalKind to "editPack"
	current application's NSApp's activateIgnoringOtherApps:true
	editPanel's makeKeyAndOrderFront_(missing value)
	current application's NSApp's runModalForWindow_(editPanel)

	try
		editPanel's orderOut_(missing value)
		editPanel's setDelegate:(missing value)
		editPanel's |close|()
	end try
	set editAllowTV to missing value
	set editDenyTV to missing value
	set editTitleLabel to missing value
	set editTitleField to missing value
	set editTitlePencil to missing value
	set editDescLabel to missing value
	set editDescScroll to missing value
	set editDescTV to missing value
	set editDescPencil to missing value
	set editTitleEditing to false
	set editDescEditing to false
	set currentModalKind to prevKind
end showEditPackPanel

on capturePanelFrame(panelRef)
	-- NSRect as {{x, y}, {w, h}} list for rebuild restore
	try
		return panelRef's |frame|() as list
	on error
		return missing value
	end try
end capturePanelFrame

on placeTemplatesPanel(panelRef, panelW, panelH, savedFrame)
	-- First open: center. Rebuilds: keep top edge stable without jumping.
	-- IMPORTANT: setFrame uses *window* frame (includes title bar).
	-- panelW/panelH are *content* size — convert via frameRectForContentRect.
	if savedFrame is missing value then
		panelRef's |center|()
		return
	end if
	try
		set contentRect to current application's NSMakeRect(0, 0, panelW, panelH)
		set outerRect to panelRef's frameRectForContentRect:contentRect
		set outerList to outerRect as list
		set newW to item 1 of item 2 of outerList
		set newH to item 2 of item 2 of outerList
		set ox to item 1 of item 1 of savedFrame
		set oy to item 2 of item 1 of savedFrame
		set oldH to item 2 of item 2 of savedFrame
		-- Keep top edge fixed when height changes after add/delete
		set oy to oy + (oldH - newH)
		panelRef's setFrame:{{ox, oy}, {newW, newH}} display:true
	on error
		panelRef's |center|()
	end try
end placeTemplatesPanel

-- Enable-list panel only (options chrome). Edit opens a separate panel.
on showTemplatesPanel(enabledCSV)
	set workingCSV to enabledCSV
	set resultCSV to missing value
	set savedFrame to missing value

	repeat
		try
			templatesReloadPacks()
		on error errMsg
			display dialog "Could not load templates:" & return & return & errMsg & return & return & "Is the anonymize CLI installed?" buttons {"OK"} default button 1 with icon stop with title "Anonymizer"
			return missing value
		end try

		set nPacks to 0
		try
			set nPacks to tmplPacks's |count|() as integer
		end try
		if nPacks is 0 then
			display dialog "No templates found." buttons {"OK"} default button 1 with icon caution with title "Anonymizer"
			return missing value
		end if

		set margin to 24
		set gapXs to 6
		set gapSm to 10
		set gapLg to 22
		set panelW to 500
		set iconSize to 44
		set titleRowH to iconSize
		set subH to 40
		set rowH to 30
		set iconBtnW to 28
		set iconGap to 2
		-- pencil + duplicate + trash (trash only drawn for user)
		set iconsW to (iconBtnW * 3) + (iconGap * 2)
		set listH to (nPacks * rowH) + 16
		if listH > 280 then set listH to 280
		if listH < 120 then set listH to 120
		set btnH to 32
		set btnW to 110
		set midBtnW to 100
		set btnGap to 10

		-- No section title; one action row
		set panelH to margin + titleRowH + gapSm + subH + gapLg + listH + gapLg + btnH + margin

		set panelRect to current application's NSMakeRect(0, 0, panelW, panelH)
		set thePanel to (current application's NSPanel's alloc())
		set thePanel to (thePanel's initWithContentRect:panelRect styleMask:7 backing:2 defer:false)
		thePanel's setTitle:""
		thePanel's setLevel:8
		thePanel's setDelegate:me
		thePanel's setReleasedWhenClosed:false
		try
			thePanel's setPreventsApplicationTerminationWhenModal:false
		end try
		placeTemplatesPanel(thePanel, panelW, panelH, savedFrame)
		set tmplListPanel to thePanel

		set content to thePanel's contentView()
		set innerW to panelW - margin * 2
		set fillC to windowFillColor()

		set y to panelH - margin - titleRowH
		addTitleRowNamed(content, panelW, y, "Templates")

		set y to y - gapSm - subH
		content's addSubview:(makeCaption("Turn templates on for this run. Pencil edits lists; copy duplicates; trash deletes user templates.", margin, y, innerW, subH))

		set y to y - gapLg - listH

		set listScroll to current application's NSScrollView's alloc()'s initWithFrame:{{margin, y}, {innerW, listH}}
		listScroll's setHasVerticalScroller:true
		listScroll's setHasHorizontalScroller:false
		listScroll's setAutohidesScrollers:true
		applyRoundedScrollWell(listScroll)
		set docH to nPacks * rowH + 8
		if docH < listH then set docH to listH
		set listDoc to current application's NSView's alloc()'s initWithFrame:{{0, 0}, {innerW - 4, docH}}
		try
			listDoc's setWantsLayer:true
			listDoc's layer()'s setBackgroundColor:(fillC's CGColor())
		end try
		set tmplEnableBoxes to {}
		set i to 0
		repeat while i < nPacks
			set p to tmplPacks's objectAtIndex:i
			set pid to textFromObj(p's objectForKey:"id")
			set ttl to textFromObj(p's objectForKey:"title")
			set isBuiltin to false
			set kindLabel to "user"
			try
				if (p's objectForKey:"builtin") as boolean then
					set isBuiltin to true
					set kindLabel to "builtin"
				end if
			end try
			set rowY to docH - 4 - (i + 1) * rowH
			set cbW to innerW - 16 - iconsW - 10
			set cb to current application's NSButton's alloc()'s initWithFrame:{{8, rowY}, {cbW, rowH - 4}}
			cb's setButtonType:(current application's NSButtonTypeSwitch)
			cb's setTitle:(ttl & "  ·  " & kindLabel)
			cb's setFont:(current application's NSFont's systemFontOfSize:13)
			if csvContainsId(workingCSV, pid) then
				cb's setState:(current application's NSControlStateValueOn)
			else
				cb's setState:(current application's NSControlStateValueOff)
			end if
			listDoc's addSubview:cb
			set end of tmplEnableBoxes to {packId:pid, btn:cb}
			set ix to 8 + cbW + 4
			set iy to rowY + 1
			set ih to rowH - 6
			listDoc's addSubview:(makeIconButton(ix, iy, iconBtnW, ih, i, "pencil", "Edit template", "clickTemplatesEdit:"))
			set ix to ix + iconBtnW + iconGap
			listDoc's addSubview:(makeIconButton(ix, iy, iconBtnW, ih, i, "plus.square.on.square", "Duplicate template", "clickTemplatesDuplicate:"))
			set ix to ix + iconBtnW + iconGap
			if not isBuiltin then
				listDoc's addSubview:(makeIconButton(ix, iy, iconBtnW, ih, i, "trash", "Delete template", "clickTemplatesDelete:"))
			end if
			set i to i + 1
		end repeat
		listScroll's setDocumentView:listDoc
		content's addSubview:listScroll

		-- Action bar: + New left · Cancel + Done right (same logic as options)
		set y to margin
		set newBtn to makeDialogButton("+ New", margin, y, midBtnW, btnH, "clickTemplatesNew:")
		set doneX to margin + innerW - btnW
		set cancelX to doneX - btnGap - btnW
		set cancelBtn to makeDialogButton("Cancel", cancelX, y, btnW, btnH, "clickTemplatesCancel:")
		try
			cancelBtn's setKeyEquivalent:(ASCII character 27)
		end try
		set doneBtn to makeDialogButton("Done", doneX, y, btnW, btnH, "clickTemplatesDone:")
		doneBtn's setKeyEquivalent:return
		try
			doneBtn's setKeyEquivalentModifierMask:0
		end try
		content's addSubview:newBtn
		content's addSubview:cancelBtn
		content's addSubview:doneBtn

		set templatesModalCode to -1
		set currentModalKind to "templates"
		current application's NSApp's activateIgnoringOtherApps:true
		thePanel's makeKeyAndOrderFront_(missing value)
		current application's NSApp's runModalForWindow_(thePanel)
		set response to templatesModalCode

		-- Preserve toggles across rebuild; enable freshly duplicated templates
		try
			set workingCSV to templatesCollectEnabledCSV()
		end try
		if templatesExtraEnableId is not "" then
			set workingCSV to csvAddId(workingCSV, templatesExtraEnableId)
			set templatesExtraEnableId to ""
		end if

		-- Remember where the user put the window (rebuild must not re-center)
		set savedFrame to capturePanelFrame(thePanel)

		try
			thePanel's orderOut_(missing value)
			thePanel's setDelegate:(missing value)
			thePanel's |close|()
		end try
		set tmplListPanel to missing value
		set tmplEnableBoxes to {}

		if response is 1 then
			set resultCSV to workingCSV
			try
				templatesIO("set-enabled " & quoted form of resultCSV)
			on error errMsg
				display dialog "Could not save enabled templates:" & return & return & errMsg buttons {"OK"} default button 1 with icon caution with title "Anonymizer"
			end try
			exit repeat
		else if response is 3 then
			-- rebuild after edit/new/duplicate/delete — keep savedFrame
		else
			set resultCSV to missing value
			exit repeat
		end if
	end repeat

	set currentModalKind to "options"
	return resultCSV
end showTemplatesPanel

on openTemplatesUI(enabledCSV)
	return showTemplatesPanel(enabledCSV)
end openTemplatesUI

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

-- Exclusive choice pop-up (pull-down list). selectedIndex is 0-based.
on makeOptionsPopup(titles, selectedIndex, x, y, w, h)
	set popup to current application's NSPopUpButton's alloc()'s initWithFrame:{{x, y}, {w, h}} pullsDown:false
	popup's removeAllItems()
	repeat with t in titles
		popup's addItemWithTitle:(t as text)
	end repeat
	set idx to selectedIndex as integer
	if idx < 0 then set idx to 0
	if idx > ((count of titles) - 1) then set idx to 0
	popup's selectItemAtIndex:idx
	try
		popup's setFont:(current application's NSFont's systemFontOfSize:13)
	end try
	return popup
end makeOptionsPopup

on wellFillColor()
	-- Editable text wells (allow/deny): slightly elevated control fill
	return current application's NSColor's controlBackgroundColor()
end wellFillColor

on windowFillColor()
	-- Files list + Templates list: blend with panel background
	return current application's NSColor's windowBackgroundColor()
end windowFillColor

on applyRoundedWell(viewRef, radius)
	-- Modern Mac rounded outline (no NSBezelBorder — bezel is square)
	try
		viewRef's setWantsLayer:true
		viewRef's layer()'s setCornerRadius:radius
		viewRef's layer()'s setMasksToBounds:true
		try
			viewRef's layer()'s setBorderWidth:0.5
			viewRef's layer()'s setBorderColor:(current application's NSColor's separatorColor()'s CGColor())
		end try
	end try
end applyRoundedWell

on makeScrollText(initialText, x, y, w, h)
	-- Rounded scroll well for allow/deny (control fill for contrast)
	set fillC to wellFillColor()
	set scroll to current application's NSScrollView's alloc()'s initWithFrame:{{x, y}, {w, h}}
	scroll's setHasVerticalScroller:true
	scroll's setHasHorizontalScroller:false
	scroll's setAutohidesScrollers:true
	scroll's setBorderType:(current application's NSNoBorder)
	try
		scroll's setDrawsBackground:true
		scroll's setBackgroundColor:fillC
	end try
	set tv to current application's NSTextView's alloc()'s initWithFrame:{{0, 0}, {w - 8, h - 8}}
	tv's setString:initialText
	tv's setFont:(current application's NSFont's systemFontOfSize:12)
	tv's setRichText:false
	tv's setImportsGraphics:false
	tv's setEditable:true
	tv's setSelectable:true
	tv's setVerticallyResizable:true
	tv's setHorizontallyResizable:false
	tv's setAutoresizingMask:(current application's NSViewWidthSizable)
	tv's textContainer()'s setContainerSize:{w - 20, 1.0E+7}
	tv's textContainer()'s setWidthTracksTextView:true
	try
		tv's setDrawsBackground:true
		tv's setBackgroundColor:fillC
		tv's setTextColor:(current application's NSColor's labelColor())
		tv's setInsertionPointColor:(current application's NSColor's labelColor())
	end try
	scroll's setDocumentView:tv
	applyRoundedWell(scroll, 8)
	return {scroll:scroll, textView:tv}
end makeScrollText

on applyRoundedScrollWell(scrollRef)
	-- Templates list: window-colored well + rounded outline
	set fillC to windowFillColor()
	try
		scrollRef's setBorderType:(current application's NSNoBorder)
		scrollRef's setDrawsBackground:true
		scrollRef's setBackgroundColor:fillC
	end try
	applyRoundedWell(scrollRef, 8)
end applyRoundedScrollWell

on filesListRowHeight()
	return 18
end filesListRowHeight

on filesListColumnCount(nFiles)
	if nFiles > 1 then return 2
	return 1
end filesListColumnCount

on filesListHeightForNames(names)
	-- Dynamic height: 1 column if single file, else 2 columns
	set n to count of names
	if n < 1 then set n to 1
	set cols to filesListColumnCount(n)
	set rows to (n + cols - 1) div cols
	set rowH to filesListRowHeight()
	set h to rows * rowH + 4
	if h < rowH + 4 then set h to rowH + 4
	if h > 120 then set h to 120
	return h
end filesListHeightForNames

on makeFilesListWell(names, x, y, w, h)
	-- Window-colored, no border; 1–2 columns of file names
	set fillC to windowFillColor()
	set shell to current application's NSView's alloc()'s initWithFrame:{{x, y}, {w, h}}
	try
		shell's setWantsLayer:true
		shell's layer()'s setBackgroundColor:(fillC's CGColor())
		shell's layer()'s setBorderWidth:0
	end try
	set n to count of names
	if n < 1 then return shell
	set cols to filesListColumnCount(n)
	set rows to (n + cols - 1) div cols
	set rowH to filesListRowHeight()
	set colGap to 12
	set colW to (w - colGap * (cols - 1)) / cols
	set i to 0
	repeat while i < n
		set col to i mod cols
		set row to i div cols
		-- y from bottom of shell
		set ly to h - 2 - (row + 1) * rowH
		set lx to col * (colW + colGap)
		set nm to item (i + 1) of names as text
		set lab to current application's NSTextField's alloc()'s initWithFrame:{{lx, ly}, {colW, rowH}}
		lab's setStringValue:("• " & nm)
		lab's setEditable:false
		lab's setSelectable:true
		lab's setBezeled:false
		lab's setBordered:false
		lab's setDrawsBackground:false
		lab's setFont:(current application's NSFont's systemFontOfSize:12)
		try
			lab's setTextColor:(current application's NSColor's labelColor())
			lab's setBackgroundColor:(current application's NSColor's clearColor())
			lab's cell()'s setDrawsBackground:false
			lab's setLineBreakMode:(current application's NSLineBreakByTruncatingTail)
		end try
		shell's addSubview:lab
		set i to i + 1
	end repeat
	return shell
end makeFilesListWell

on makeIconButton(x, y, w, h, tagIndex, symbolName, tooltipText, actionName)
	-- SF Symbol icon button (pencil / copy / trash)
	set btn to current application's NSButton's alloc()'s initWithFrame:{{x, y}, {w, h}}
	btn's setBezelStyle:(current application's NSBezelStyleInline)
	try
		btn's setBordered:false
	end try
	btn's setTarget:me
	btn's setAction:actionName
	btn's setTag:tagIndex
	set fallback to "•"
	if symbolName is "pencil" then set fallback to "✎"
	if symbolName is "trash" then set fallback to "⌫"
	if symbolName is "plus.square.on.square" then set fallback to "⧉"
	try
		set img to current application's NSImage's imageWithSystemSymbolName:symbolName accessibilityDescription:tooltipText
		if img is not missing value then
			btn's setImage:img
			btn's setImagePosition:(current application's NSImageOnly)
			try
				btn's setContentTintColor:(current application's NSColor's secondaryLabelColor())
			end try
		else
			btn's setTitle:fallback
			btn's setFont:(current application's NSFont's systemFontOfSize:13)
		end if
	on error
		btn's setTitle:fallback
		btn's setFont:(current application's NSFont's systemFontOfSize:13)
	end try
	try
		btn's setToolTip:tooltipText
	end try
	return btn
end makeIconButton

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
	set displayNames to fileNamesForDisplay(fileNames)

	set templateCSV to loadEnabledTemplatesCSV()

	set lastModeRow to 0
	set lastStyleRow to 0
	set lastFormatRow to 0 -- 0=md, 1=source, 2=both
	set lastReview to true
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
	set filesH to filesListHeightForNames(displayNames)
	set modeLabelH to 18
	set styleLabelH to 18
	set formatLabelH to 18
	set tmplLabelH to 18
	set popupH to 28 -- NSPopUpButton row height
	set checkH to 22
	set btnH to 32
	set btnW to 110
	set btnGap to 10
	set innerWForMeasure to panelW - margin * 2
	set statusLineText to templatesStatusLine(templateCSV)
	set tmplStatusH to heightForWrappingText(statusLineText, innerWForMeasure, 11)

	-- Popups + templates status + 2 checkboxes
	set panelH to margin + titleRowH + gapSm + subH + gapLg + filesLabelH + gapXs + filesH + gapLg + modeLabelH + gapXs + popupH + gapLg + styleLabelH + gapXs + popupH + gapLg + formatLabelH + gapXs + popupH + gapLg + tmplLabelH + gapXs + tmplStatusH + gapMd + checkH + gapSm + checkH + gapXl + btnH + margin

	repeat
		-- Status may change after Templates…; remeasure and grow/shrink panel
		set statusLineText to templatesStatusLine(templateCSV)
		set tmplStatusH to heightForWrappingText(statusLineText, panelW - margin * 2, 11)
		set filesH to filesListHeightForNames(displayNames)
		set panelH to margin + titleRowH + gapSm + subH + gapLg + filesLabelH + gapXs + filesH + gapLg + modeLabelH + gapXs + popupH + gapLg + styleLabelH + gapXs + popupH + gapLg + formatLabelH + gapXs + popupH + gapLg + tmplLabelH + gapXs + tmplStatusH + gapMd + checkH + gapSm + checkH + gapXl + btnH + margin
		set panelRect to current application's NSMakeRect(0, 0, panelW, panelH)
		set thePanel to (current application's NSPanel's alloc())
		set thePanel to (thePanel's initWithContentRect:panelRect styleMask:7 backing:2 defer:false)
		thePanel's setTitle:""
		thePanel's setLevel:8
		thePanel's setDelegate:me
		thePanel's setReleasedWhenClosed:false
		try
			-- So ⌘Q is not blocked while runModalForWindow_ is active
			thePanel's setPreventsApplicationTerminationWhenModal:false
		end try
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
		content's addSubview:(makeFilesListWell(displayNames, margin, y, innerW, filesH))

		set y to y - gapLg - modeLabelH
		content's addSubview:(makeLabel("Mode", margin, y, innerW, modeLabelH))

		set y to y - gapXs - popupH
		set modePopup to makeOptionsPopup(modeTitles, lastModeRow, margin, y, innerW, popupH)
		content's addSubview:modePopup

		set y to y - gapLg - styleLabelH
		content's addSubview:(makeLabel("Output style", margin, y, innerW, styleLabelH))

		set y to y - gapXs - popupH
		set stylePopup to makeOptionsPopup(styleTitles, lastStyleRow, margin, y, innerW, popupH)
		content's addSubview:stylePopup

		set y to y - gapLg - formatLabelH
		content's addSubview:(makeLabel("Output format", margin, y, innerW, formatLabelH))

		set y to y - gapXs - popupH
		set formatPopup to makeOptionsPopup(formatTitles, lastFormatRow, margin, y, innerW, popupH)
		content's addSubview:formatPopup

		set y to y - gapLg - tmplLabelH
		content's addSubview:(makeLabel("Active templates", margin, y, innerW, tmplLabelH))
		set y to y - gapXs - tmplStatusH
		set tmplStatusField to makeWrappingFinePrint(statusLineText, margin, y, innerW, tmplStatusH)
		content's addSubview:tmplStatusField

		set y to y - gapMd - checkH
		set reviewBox to current application's NSButton's alloc()'s initWithFrame:{{margin, y}, {innerW, checkH}}
		reviewBox's setButtonType:(current application's NSButtonTypeSwitch)
		reviewBox's setTitle:"Review findings before saving"
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

		-- Action bar: Templates… left · Cancel + Start right
		set y to margin
		set listsBtn to makeDialogButton("Templates…", margin, y, btnW, btnH, "clickOptionsLists:")
		set startX to margin + innerW - btnW
		set cancelX to startX - btnGap - btnW
		set cancelBtn to makeDialogButton("Cancel", cancelX, y, btnW, btnH, "clickOptionsCancel:")
		try
			cancelBtn's setKeyEquivalent:(ASCII character 27)
		end try
		set startBtn to makeDialogButton("Start", startX, y, btnW, btnH, "clickOptionsStart:")
		startBtn's setKeyEquivalent:return
		try
			-- Emphasize primary action (blue when focused)
			startBtn's setKeyEquivalentModifierMask:0
		end try
		content's addSubview:listsBtn
		content's addSubview:cancelBtn
		content's addSubview:startBtn

		set optionsModalCode to -1
		current application's NSApp's activateIgnoringOtherApps:true
		thePanel's makeKeyAndOrderFront_(missing value)
		current application's NSApp's runModalForWindow_(thePanel)
		set response to optionsModalCode

		set lastModeRow to modePopup's indexOfSelectedItem() as integer
		if lastModeRow < 0 then set lastModeRow to 0
		if lastModeRow > 2 then set lastModeRow to 0
		set lastStyleRow to stylePopup's indexOfSelectedItem() as integer
		if lastStyleRow < 0 then set lastStyleRow to 0
		if lastStyleRow > 1 then set lastStyleRow to 0
		set lastFormatRow to formatPopup's indexOfSelectedItem() as integer
		if lastFormatRow < 0 then set lastFormatRow to 0
		if lastFormatRow > 2 then set lastFormatRow to 0
		set lastReview to false
		if (reviewBox's state() as integer) is 1 then set lastReview to true
		if (reviewBox's state() as integer) is (current application's NSControlStateValueOn as integer) then set lastReview to true
		set lastOpen to false
		if (openBox's state() as integer) is 1 then set lastOpen to true
		if (openBox's state() as integer) is (current application's NSControlStateValueOn as integer) then set lastOpen to true

		-- Drop floating level so Tk Templates can stack above this panel.
		-- Keep panel ordered front (visible underneath) for Templates…;
		-- hide + close for Start/Cancel so no zombie level-8 panels linger.
		try
			thePanel's setLevel:0
		end try

		if response is 1 then
			try
				thePanel's orderOut_(missing value)
				thePanel's setDelegate:(missing value)
				-- |close| escapes AppleScript reserved word "close"
				thePanel's |close|()
			end try
			set modeArg to item (lastModeRow + 1) of modeArgs
			set redactStyle to item (lastStyleRow + 1) of styleArgs
			set outputFormat to item (lastFormatRow + 1) of formatArgs
			set wantReview to lastReview
			set wantOpen to lastOpen
			if modeArg is "extract" then
				set wantReview to false
				set outputFormat to "md"
			end if
			return {modeArg:modeArg, wantReview:wantReview, wantOpen:wantOpen, outputFormat:outputFormat, redactStyle:redactStyle, templateCSV:templateCSV}
		else if response is 2 then
			-- Templates… → shared Tk dialog; options stays visible under it
			try
				thePanel's orderFront_(missing value)
			end try
			set newCSV to openTemplatesUI(templateCSV)
			try
				thePanel's orderOut_(missing value)
				thePanel's setDelegate:(missing value)
				thePanel's |close|()
			end try
			if newCSV is not missing value then
				set templateCSV to newCSV
			end if
			-- Next loop recreates panel at floating level 8 again
		else
			try
				thePanel's orderOut_(missing value)
				thePanel's setDelegate:(missing value)
				thePanel's |close|()
			end try
			return missing value
		end if
	end repeat
end showOptionsPanel

on fileNamesForDisplay(names)
	-- Cap long lists; last row notes remaining count
	set maxShow to 20
	set out to {}
	set i to 0
	set n to count of names
	repeat with nm in names
		set i to i + 1
		if i > maxShow then
			set moreCount to n - maxShow
			set end of out to "… and " & (moreCount as text) & " more"
			exit repeat
		end if
		set end of out to (nm as text)
	end repeat
	return out
end fileNamesForDisplay

on fileListSummary(names)
	-- Used by result dialogs (single column text)
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

-- Title strip: squircle + title text, vertically centered. yBottom = bottom of row.
on addTitleRowNamed(parentView, panelW, yBottom, titleText)
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
	titleField's setStringValue:titleText
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
end addTitleRowNamed

-- Title strip: squircle + version, vertically centered. yBottom = bottom of row.
on addTitleRow(parentView, panelW, yBottom)
	return addTitleRowNamed(parentView, panelW, yBottom, appTitle())
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
