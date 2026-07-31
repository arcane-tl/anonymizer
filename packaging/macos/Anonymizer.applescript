-- Anonymizer droplet: drop PDF/DOCX/text files onto the app icon.
-- Builds with packaging/macos/install-app.sh (embeds run-anonymize.sh).
--
-- Flow: mode → optional --review (Terminal) → open output? (dialog or Terminal)

property modeLabels : {"strict — full scrub (default)", "standard — people & contact (keep companies)", "extract — text only, no redaction"}

on run
	try
		set theFiles to choose file with prompt "Choose documents to anonymize" with multiple selections allowed
		processFiles(theFiles)
	on error errMsg number errNum
		if errNum is -128 then return -- user cancelled
		display dialog "Anonymizer: " & errMsg buttons {"OK"} default button 1 with icon stop
	end try
end run

on open theFiles
	try
		processFiles(theFiles)
	on error errMsg number errNum
		if errNum is -128 then return
		display dialog "Anonymizer: " & errMsg buttons {"OK"} default button 1 with icon stop
	end try
end open

on processFiles(theFiles)
	set modeChoice to choose from list modeLabels with prompt "Anonymizer mode:" default items {item 1 of modeLabels} OK button name "Continue" cancel button name "Cancel" without multiple selections allowed
	if modeChoice is false then return
	set modeLabel to item 1 of modeChoice
	set modeArg to modeFromLabel(modeLabel)

	set wantReview to false
	if modeArg is not "extract" then
		try
			set reviewBtn to button returned of (display dialog "Review redactions interactively before saving?" & return & return & "Opens Terminal with a checkbox list (space = keep clear, enter = write). Useful for fixing false positives." buttons {"No", "Yes"} default button "No" with title "Anonymizer")
			if reviewBtn is "Yes" then set wantReview to true
		on error number errNum
			if errNum is -128 then return
			error
		end try
	end if

	set helper to resourcePath("run-anonymize.sh")
	set posixFiles to {}
	repeat with f in theFiles
		set end of posixFiles to quoted form of POSIX path of f
	end repeat
	set fileArgs to my joinSpace(posixFiles)

	if wantReview then
		-- --review needs a real TTY; launch Terminal with the helper
		set shellLine to "bash " & quoted form of helper & " --review " & modeArg & " " & fileArgs
		-- Keep window open briefly so the open-prompt is readable
		set termCmd to shellLine & "; echo; echo '---'; echo 'You can close this window when finished.'; exec bash"
		tell application "Terminal"
			activate
			do script termCmd
		end tell
		display notification "Complete the review in Terminal (space / enter). You will be asked whether to open the file(s)." with title "Anonymizer" subtitle "Review mode"
		return
	end if

	-- Non-interactive: run quietly, then offer to open outputs
	set shellCmd to "bash " & quoted form of helper & " " & modeArg & " " & fileArgs
	set exitCode to 0
	set shellOut to ""
	try
		set shellOut to do shell script shellCmd
	on error errMsg number errNum
		set exitCode to errNum
		set shellOut to errMsg
	end try

	if exitCode is not 0 then
		display dialog "Anonymizer failed (mode " & modeArg & "):" & return & return & shellOut buttons {"OK"} default button 1 with icon stop
		return
	end if

	set outPaths to parseOutputLines(shellOut)
	set n to count of outPaths
	if n is 0 then
		display notification "Finished (" & modeArg & "). Look next to your source files for .md output." with title "Anonymizer" subtitle "Success"
		return
	end if

	set openPrompt to "Anonymize finished (" & modeArg & ")." & return & return
	if n is 1 then
		set openPrompt to openPrompt & "Open the anonymized file now?" & return & return & item 1 of outPaths
	else
		set openPrompt to openPrompt & "Open " & n & " anonymized files now?"
	end if

	try
		set openBtn to button returned of (display dialog openPrompt buttons {"Not now", "Open"} default button "Open" with title "Anonymizer")
	on error number errNum
		if errNum is -128 then return
		error
	end try

	if openBtn is "Open" then
		repeat with p in outPaths
			try
				do shell script "open " & quoted form of p
			end try
		end repeat
	end if
	display notification "Done (" & modeArg & ")." with title "Anonymizer" subtitle "Success"
end processFiles

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

on modeFromLabel(modeLabel)
	if modeLabel starts with "extract" then return "extract"
	if modeLabel starts with "standard" then return "standard"
	return "strict"
end modeFromLabel

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
