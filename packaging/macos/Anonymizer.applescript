-- Anonymizer droplet: one short wizard at drop time, then run.
-- Builds with packaging/macos/install-app.sh (embeds run-anonymize.sh).
--
-- Wizard: files → goal → review? → open? → confirm → run → result

property goalLabels : {¬
	"Remove personal details (recommended)", ¬
	"Remove identity only (keep company names)", ¬
	"Convert to text only (no privacy scrub)"}

on run
	try
		set theFiles to choose file with prompt "Choose documents to anonymize" with multiple selections allowed
		processFiles(theFiles)
	on error errMsg number errNum
		if errNum is -128 then return
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
	-- Step 0: confirm which files
	set fileNames to {}
	set posixFiles to {}
	repeat with f in theFiles
		set end of fileNames to name of f
		set end of posixFiles to quoted form of POSIX path of f
	end repeat
	set nFiles to count of fileNames
	if nFiles is 0 then return

	set fileSummary to fileListSummary(fileNames)
	try
		set contBtn to button returned of (display dialog ¬
			(nFiles as text) & " document" & pluralS(nFiles) & " ready" & return & return & fileSummary ¬
			buttons {"Cancel", "Continue"} default button "Continue" cancel button "Cancel" with title "Anonymizer")
	on error number errNum
		if errNum is -128 then return
		error
	end try
	if contBtn is not "Continue" then return

	-- Step 1: goal (mode) in plain language
	set modeChoice to choose from list goalLabels with prompt ¬
		"What do you want to do?" default items {item 1 of goalLabels} ¬
		OK button name "Continue" cancel button name "Cancel" without multiple selections allowed
	if modeChoice is false then return
	set goalLabel to item 1 of modeChoice
	set modeArg to modeFromGoal(goalLabel)
	set goalShort to goalShortName(goalLabel)

	-- Step 2a: review? (only if scrubbing)
	set wantReview to false
	if modeArg is not "extract" then
		try
			set reviewBtn to button returned of (display dialog ¬
				"Review findings before saving?" & return & return & ¬
				"Optional. Opens Terminal so you can un-check mistakes (false positives) before the file is written." & return & return & ¬
				"Skip for the fastest result." ¬
				buttons {"No", "Yes"} default button "No" with title "Anonymizer")
			if reviewBtn is "Yes" then set wantReview to true
		on error number errNum
			if errNum is -128 then return
			error
		end try
	end if

	-- Step 2b: open when finished? (always, up front)
	set wantOpen to true
	try
		set openBtn to button returned of (display dialog ¬
			"Open the result when finished?" & return & return & ¬
			"Opens the Markdown file in your default app after processing." ¬
			buttons {"No", "Yes"} default button "Yes" with title "Anonymizer")
		if openBtn is "No" then set wantOpen to false
	on error number errNum
		if errNum is -128 then return
		error
	end try

	-- Step 3: confirm summary
	set reviewLine to "No"
	if wantReview then set reviewLine to "Yes (in Terminal)"
	set openLine to "No"
	if wantOpen then set openLine to "Yes when done"
	set outHint to "Next to each original (name.anonymized.md)"
	if modeArg is "extract" then set outHint to "Next to each original (name.md)"

	set confirmText to "Ready to run" & return & return & ¬
		"Files:  " & (nFiles as text) & " document" & pluralS(nFiles) & return & ¬
		"Goal:   " & goalShort & return & ¬
		"Review: " & reviewLine & return & ¬
		"Open:   " & openLine & return & ¬
		"Output: " & outHint

	try
		set startBtn to button returned of (display dialog confirmText ¬
			buttons {"Cancel", "Start"} default button "Start" cancel button "Cancel" with title "Anonymizer")
	on error number errNum
		if errNum is -128 then return
		error
	end try
	if startBtn is not "Start" then return

	set helper to resourcePath("run-anonymize.sh")
	set fileArgs to my joinSpace(posixFiles)
	set openEnv to "0"
	if wantOpen then set openEnv to "1"

	if wantReview then
		-- Expectation, then Terminal (needs TTY for checkbox review)
		try
			display dialog ¬
				"Terminal will open for review." & return & return & ¬
				"• Space — keep that item in clear text (false positive)" & return & ¬
				"• Enter — save the file" & return & return & ¬
				"When review finishes, results open only if you chose that earlier." ¬
				buttons {"Cancel", "Open Terminal"} default button "Open Terminal" cancel button "Cancel" with title "Anonymizer"
		on error number errNum
			if errNum is -128 then return
			error
		end try

		set shellLine to "export ANONYMIZER_OPEN=" & openEnv & "; bash " & quoted form of helper & " --review " & modeArg & " " & fileArgs
		set termCmd to shellLine & "; echo; echo '--- Finished. You can close this window. ---'; exec bash"
		tell application "Terminal"
			activate
			do script termCmd
		end tell
		display notification "Complete the checklist in Terminal (space / enter)." with title "Anonymizer" subtitle "Review"
		return
	end if

	-- Non-interactive run
	display notification "Working on " & (nFiles as text) & " file" & pluralS(nFiles) & "…" with title "Anonymizer" subtitle goalShort

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

	-- Step 4: result (no new decisions about open)
	set resultBody to "Done" & return & return
	if nOut is 0 then
		set resultBody to resultBody & "Finished, but no output paths were reported. Check next to your original files for .md."
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

on fileListSummary(names)
	set maxShow to 8
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

on modeFromGoal(goalLabel)
	if goalLabel starts with "Convert to text" then return "extract"
	if goalLabel starts with "Remove identity" then return "standard"
	return "strict"
end modeFromGoal

on goalShortName(goalLabel)
	if goalLabel starts with "Convert to text" then return "Text only (no scrub)"
	if goalLabel starts with "Remove identity" then return "Identity only (keep companies)"
	return "Remove personal details"
end goalShortName

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
