-- Quiet progress strip. Does not activate, so Review stays the key window.
-- Usage: osascript show_progress.applescript /path/to/status.json
use framework "AppKit"
use scripting additions

on run argv
	if (count of argv) is 0 then return
	set statusPath to item 1 of argv
	set nsapp to current application's NSApplication's sharedApplication()
	try
		-- Accessory: no Dock icon and no activation.
		nsapp's setActivationPolicy:1
	end try

	set screen to current application's NSScreen's mainScreen()
	set vf to screen's visibleFrame()
	set origin to item 1 of (vf as list)
	set sz to item 2 of (vf as list)
	set vx to item 1 of (origin as list)
	set vy to item 2 of (origin as list)
	set vw to item 1 of (sz as list)
	set panelW to 460
	set panelH to 86
	set x to vx + (vw - panelW) / 2
	set y to vy + 28
	set rect to current application's NSMakeRect(x, y, panelW, panelH)
	-- NSWindowStyleMaskNonactivatingPanel = 128
	set panel to current application's NSPanel's alloc()'s initWithContentRect:rect styleMask:128 backing:2 defer:false
	panel's setLevel:0
	panel's setHidesOnDeactivate:false
	panel's setFloatingPanel:false
	panel's setOpaque:true
	panel's setHasShadow:true
	panel's setBackgroundColor:(current application's NSColor's colorWithCalibratedRed:0.059 green:0.067 blue:0.082 alpha:1)

	set content to panel's contentView()
	set nameField to makeField(16, 52, 340, 22, 13, 1)
	set countField to makeField(300, 52, 144, 22, 12, 0)
	countField's setAlignment:(current application's NSTextAlignmentRight)
	set phaseField to makeField(16, 30, 428, 18, 12, 0)
	phaseField's setTextColor:(current application's NSColor's colorWithCalibratedWhite:0.62 alpha:1)
	set track to makeBar(16, 14, 428, 6, 0.16, 0.17, 0.2)
	set fill to makeBar(16, 14, 8, 6, 0.376, 0.647, 0.98)
	content's addSubview:track
	content's addSubview:fill
	content's addSubview:nameField
	content's addSubview:countField
	content's addSubview:phaseField

	nameField's setStringValue:"Starting"
	panel's orderFrontRegardless()

	set seen to false
	repeat
		delay 0.25
		set payload to readStatus(statusPath)
		if payload is missing value then
			if seen then exit repeat
		else
			set seen to true
			set jobState to payload's state
			if jobState is "done" or jobState is "error" then exit repeat
			if payload's fileName is not "" then
				nameField's setStringValue:(payload's fileName)
				phaseField's setStringValue:(payload's phase)
			else
				nameField's setStringValue:(payload's phase)
				phaseField's setStringValue:""
			end if
			if payload's total > 1 and payload's index > 0 then
				countField's setStringValue:((payload's index as text) & " of " & (payload's total as text))
			else
				countField's setStringValue:""
			end if
			set frac to payload's fraction
			if frac < 0 then set frac to 0
			if frac > 1 then set frac to 1
			set fillW to 428 * frac
			fill's setFrame:(current application's NSMakeRect(16, 14, fillW, 6))
		end if
	end repeat
	panel's orderOut_(missing value)
end run

on makeBar(x, y, w, h, r, g, b)
	set box to current application's NSBox's alloc()'s initWithFrame:(current application's NSMakeRect(x, y, w, h))
	box's setBoxType:4
	box's setBorderWidth:0
	box's setCornerRadius:3
	box's setFillColor:(current application's NSColor's colorWithCalibratedRed:r green:g blue:b alpha:1)
	return box
end makeBar

on makeField(x, y, w, h, size, isBold)
	set field to current application's NSTextField's alloc()'s initWithFrame:(current application's NSMakeRect(x, y, w, h))
	field's setBezeled:false
	field's setDrawsBackground:false
	field's setEditable:false
	field's setSelectable:false
	field's setTextColor:(current application's NSColor's whiteColor())
	if isBold is 1 then
		field's setFont:(current application's NSFont's boldSystemFontOfSize:size)
	else
		field's setFont:(current application's NSFont's systemFontOfSize:size)
	end if
	return field
end makeField

on readStatus(statusPath)
	try
		set raw to do shell script "python3 - " & quoted form of statusPath & " <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    raise SystemExit(2)
d = json.loads(p.read_text(encoding='utf-8'))
print(d.get('state') or '')
print(d.get('file') or '')
print(d.get('phase') or '')
print(int(d.get('index') or 0))
print(int(d.get('total') or 0))
print(float(d.get('fraction') or 0))
PY"
		set AppleScript's text item delimiters to return
		set parts to text items of raw
		set AppleScript's text item delimiters to ""
		if (count of parts) < 6 then return missing value
		return {state:item 1 of parts, fileName:item 2 of parts, phase:item 3 of parts, index:(item 4 of parts) as integer, total:(item 5 of parts) as integer, fraction:(item 6 of parts) as real}
	on error
		return missing value
	end try
end readStatus
