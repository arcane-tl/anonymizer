-- Anonymizer droplet: drop PDF/DOCX/text files onto the app icon.
-- Builds with packaging/macos/install-app.sh (embeds run-anonymize.sh).

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
	set modeChoice to choose from list modeLabels with prompt "Anonymizer mode:" default items {item 1 of modeLabels} OK button name "Run" cancel button name "Cancel" without multiple selections allowed
	if modeChoice is false then return
	set modeLabel to item 1 of modeChoice
	set modeArg to modeFromLabel(modeLabel)

	set helper to resourcePath("run-anonymize.sh")
	set posixFiles to {}
	repeat with f in theFiles
		set end of posixFiles to quoted form of POSIX path of f
	end repeat

	set shellCmd to "bash " & quoted form of helper & " " & modeArg & " " & my joinSpace(posixFiles)
	set exitCode to 0
	set shellOut to ""
	try
		set shellOut to do shell script shellCmd
	on error errMsg number errNum
		set exitCode to errNum
		set shellOut to errMsg
	end try

	if exitCode is 0 then
		display notification "Finished (" & modeArg & "). Check the folder next to your files for .md output." with title "Anonymizer" subtitle "Success"
	else
		display dialog "Anonymizer failed (mode " & modeArg & "):" & return & return & shellOut buttons {"OK"} default button 1 with icon stop
	end if
end processFiles

on modeFromLabel(modeLabel)
	if modeLabel starts with "extract" then return "extract"
	if modeLabel starts with "standard" then return "standard"
	return "strict"
end modeFromLabel

on resourcePath(resourceName)
	set appPath to path to me as text
	-- Prefer bundle Resources (installed .app); fall back next to script during dev
	try
		return POSIX path of (path to resource resourceName)
	end try
	set appPosix to POSIX path of (path to me)
	-- If we are a .app, Resources is Contents/Resources
	if appPosix ends with ".app/" or appPosix ends with ".app" then
		set base to appPosix
		if base ends with "/" then set base to text 1 thru -2 of base
		return base & "/Contents/Resources/" & resourceName
	end if
	-- Dev: packaging/macos next to this source when run via osascript file
	return (do shell script "dirname " & quoted form of appPosix) & "/" & resourceName
end resourcePath

on joinSpace(lst)
	set AppleScript's text item delimiters to " "
	set s to lst as text
	set AppleScript's text item delimiters to ""
	return s
end joinSpace
