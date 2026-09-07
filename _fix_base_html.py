# -*- coding: utf-8 -*-
import io, os

PATH = r'c:\Users\İzzet\Documents\trae_projects\course_register\templates\base.html'
LOG  = r'c:\Users\İzzet\Documents\trae_projects\course_register\_fix_log.txt'

log_lines = []
def log(msg):
    log_lines.append(str(msg))

with io.open(PATH, 'r', encoding='utf-8') as f:
    content = f.read()

log(f'Total content length: {len(content)} chars')

# ---- FIND UNIQUE MARKERS ----
# Marker A: the Django URL tag for feedback_submit used in JS getAttribute fallback
# This exact string appears ONCE in the file (the Feedback form submit handler)
MARKER_A = 'getAttribute(\'action\') || "{% url \'core:feedback_submit\' %}"'
idx_A = content.find(MARKER_A)
log(f'MARKER_A position: {idx_A}')
assert idx_A != -1, 'MARKER_A not found - aborting safe'

# Find the START of the block: the FIRST 'setLoading(true);' BEFORE marker_A
# that occurs WITHIN the feedback submit handler (we can scan backwards for it)
search_back = content[:idx_A]
# We want the 'setLoading(true);' nearest to and before idx_A (it's the loading
# call after min-length guard, NOT other setLoading(true) calls elsewhere.)
load_marker = 'setLoading(true);'
idx_load = search_back.rfind(load_marker)
log(f'setLoading(true) nearest before MARKER_A: pos {idx_load}')
assert idx_load != -1, 'setLoading(true) not found before MARKER_A'

# Find LINE start of idx_load (go backwards to \n)
line_start = content.rfind('\n', 0, idx_load)
if line_start == -1:
    line_start = 0
else:
    line_start += 1  # skip the \n itself

# Indent for this level = content[line_start:idx_load]
indent_setLoading = content[line_start:idx_load]
log(f'indent_setLoading repr: {repr(indent_setLoading)} len={len(indent_setLoading)}')

# ---- DERIVE ONE INDENT UNIT ----
# Scan forward a bit for the line: `if (msgVal.length < 10) {` (unique nearby),
# then grab the indent of the NEXT line (inside the if body) -> difference = 1 unit
# Simpler: just count spaces/tabs in indent_setLoading.
# It's level 5 (5 units deep). one_unit = indent_setLoading[: len(indent_setLoading)//5 ]
# (if using spaces it's 20 -> 4. If tabs it's 5 -> 1)
units = 5
one_unit = indent_setLoading[: max(1, len(indent_setLoading) // units)]
log(f'one_unit repr: {repr(one_unit)} len={len(one_unit)}')

NL = '\r\n' if '\r\n' in content[:2000] else '\n'
log(f'Newline style: {repr(NL)}')

# ---- BUILD INDENT LEVELS ----
INDENT   = indent_setLoading                  # 5 units
INDENT_1 = INDENT   + one_unit                # 6 units
INDENT_2 = INDENT_1 + one_unit                # 7 units
INDENT_3 = INDENT_2 + one_unit                # 8 units
INDENT_4 = INDENT_3 + one_unit                # 9 units

# ---- FIND END OF BLOCK ----
# After MARKER_A, the fetch + then + catch chain ends with a line that only
# has indent (INDENT) + "});" (the closing of the .catch chain).
# And after that is the submit listener's closing "});" which is at INDENT level minus one unit.
# So we want to replace UP TO AND INCLUDING the line "                        });"
# that closes the catch chain, BEFORE the submit listener's "                });"
#
# Safer: find the line 'CRITICAL JS EXCEPTION' (unique, only there), then scan
# forward for the FIRST "});" at INDENT level THAT CLOSES THE CATCH —
# it's the "});" that comes right after console.error("CRITICAL JS EXCEPTION:", err);
mark_critical = 'CRITICAL JS EXCEPTION'
idx_crit = content.find(mark_critical, idx_A)
log(f'CRITICAL marker position: {idx_crit}')
assert idx_crit != -1, 'CRITICAL marker not found'
# Now find the FIRST "});" that closes .catch chain AFTER idx_crit
# This "});" is at INDENT level (the same as setLoading's level? No — .catch(function(err)
# closes with "});" at 1 unit deeper than INDENT. Let's look manually:
# level 5 = INDENT = setLoading
# level 6 = INDENT_1 = catch(...) function body inner lines + closing "});" ???
# Actually:
#   .then(...)
#   .catch(function (err) {          <- INDENT_1 level? No, .catch starts with
#                                          6-space deeper than fetch.
#     setLoading(false);             <- INDENT_2
#     alertErrorText...              <- INDENT_2
#     console.error(...);            <- INDENT_2
#   });                              <- INDENT_1 level (closing of catch-function)
# });                                <- INDENT minus 1 unit = closing submit listener
#
# So the block we want to REPLACE ends at the "catch chain closing });"
# which is at INDENT_1 level.

# Scan forward after idx_crit for the FIRST occurrence of "\n" + INDENT_1 + "});"
close_catch_needle = NL + INDENT_1 + "});"
idx_close_catch = content.find(close_catch_needle, idx_crit)
log(f'close_catch at pos: {idx_close_catch}')
assert idx_close_catch != -1, 'catch close }); not found'

# The END (last char index of our replaced region) = idx_close_catch + len(close_catch_needle)
# But close_catch_needle begins with NL, so we need the region to end right AFTER
# the "});". That is: idx_close_catch + len(close_catch_needle) - 1 (includes the trailing }) 
END_POS = idx_close_catch + len(close_catch_needle)
# Actually: close_catch_needle = "\n                    });" - so END_POS after
# the string includes the "});" + next newline start. We want to replace everything
# from line_start (beginning of setLoading line) UP TO BUT NOT INCLUDING the newline
# right after "});".  So set END_POS = idx_close_catch + len(close_catch_needle).
# Let's verify: content[idx_close_catch: idx_close_catch + len(close_catch_needle)]  -> "\n....});"
# After replacement, new content ends with same newline so subsequent line (submit listener close); stays aligned.

START_POS = line_start  # beginning of the "                    setLoading(true);" line

log(f'REPLACE REGION: START={START_POS} END={END_POS}')
old_segment = content[START_POS:END_POS]
log(f'OLD SEGMENT first 120 chars: {repr(old_segment[:120])}')
log(f'OLD SEGMENT last  120 chars: {repr(old_segment[-120:])}')

# ---- BUILD NEW REPLACEMENT SEGMENT ----
def L(level, text):
    mapping = {0:'', 1:INDENT, 2:INDENT_1, 3:INDENT_2, 4:INDENT_3, 5:INDENT_4}
    return mapping[level] + text

new_lines = []
# setLoading(true);
new_lines.append(L(1, 'setLoading(true);'))
new_lines.append('')  # blank line
# try {
new_lines.append(L(1, 'try {'))
#   const csrfToken = ...
new_lines.append(L(2, "const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]')?.value || document.querySelector('[name=csrfmiddlewaretoken]')?.value;"))
new_lines.append('')
#   fetch(....
new_lines.append(L(2, "fetch(form.action || \"{% url 'core:feedback_submit' %}\", {"))
new_lines.append(L(3, "method: 'POST',"))
new_lines.append(L(3, 'headers: {'))
new_lines.append(L(4, "'X-Requested-With': 'XMLHttpRequest',"))
new_lines.append(L(4, "'X-CSRFToken': csrfToken"))
new_lines.append(L(3, '},'))
new_lines.append(L(3, 'body: new FormData(form)'))
new_lines.append(L(2, '})'))
#   .then(response => response.json())
new_lines.append(L(2, '.then(response => response.json())'))
#   .then(data => { ... })
new_lines.append(L(2, '.then(data => {'))
new_lines.append(L(3, "if (data.success || data.status === 'success') {"))
new_lines.append(L(4, 'setLoading(false);'))
new_lines.append(L(4, 'form.reset();'))
new_lines.append(L(4, 'updateCounter();'))
new_lines.append(L(4, 'bootstrap.Modal.getOrCreateInstance(modalEl).hide();'))
new_lines.append(L(4, 'alert(data.message || "Uğurla göndərildi!");'))
new_lines.append(L(4, 'window.location.reload();'))
new_lines.append(L(3, '} else {'))
new_lines.append(L(4, 'setLoading(false);'))
new_lines.append(L(4, 'alertErrorText.textContent = data.message || "Xəta baş verdi.";'))
new_lines.append(L(4, "alertError.classList.add('show');"))
new_lines.append(L(4, 'if (data.errors && data.errors.message && textarea) {'))
new_lines.append(L(5, 'var msgs = Array.isArray(data.errors.message) ? data.errors.message : [data.errors.message];'))
new_lines.append(L(5, "textarea.classList.add('is-invalid');"))
new_lines.append(L(5, 'if (msgErrorEl) {'))
new_lines.append(L(5, 'msgErrorEl.textContent = msgs.join(\'<br>\');'))
new_lines.append(L(5, "msgErrorEl.style.display = 'block';"))
new_lines.append(L(5, '}'))
new_lines.append(L(4, '}'))
new_lines.append(L(4, 'submitText.textContent = "Göndər";'))
new_lines.append(L(4, 'submitBtn.disabled = false;'))
new_lines.append(L(3, '}'))
new_lines.append(L(2, '})'))
#   .catch(error => { ... })
new_lines.append(L(2, '.catch(error => {'))
new_lines.append(L(3, 'setLoading(false);'))
new_lines.append(L(3, 'alert("Şəbəkə və ya proqram xətası: " + error.message);'))
new_lines.append(L(3, 'submitText.textContent = "Göndər";'))
new_lines.append(L(3, 'submitBtn.disabled = false;'))
new_lines.append(L(2, '});'))
# } catch (initError) { ... }
new_lines.append(L(1, '} catch (initError) {'))
new_lines.append(L(2, 'setLoading(false);'))
new_lines.append(L(2, 'alert("Tətbiq işə salma xətası: " + initError.message);'))
new_lines.append(L(2, 'submitText.textContent = "Göndər";'))
new_lines.append(L(2, 'submitBtn.disabled = false;'))
new_lines.append(L(1, '}'))

# Join with newline, ensure last line has newline so "});" submit listener close stays on own line
new_segment = (NL.join(new_lines)) + NL

log(f'NEW SEGMENT length: {len(new_segment)} chars')
log(f'NEW SEGMENT first 120 chars: {repr(new_segment[:120])}')
log(f'NEW SEGMENT last  80 chars: {repr(new_segment[-80:])}')

# ---- PERFORM REPLACEMENT ----
new_content = content[:START_POS] + new_segment + content[END_POS:]
log(f'New content length: {len(new_content)} (was {len(content)})')

with io.open(PATH, 'w', encoding='utf-8') as f:
    f.write(new_content)

log('REPLACEMENT COMPLETED SUCCESSFULLY')

with io.open(LOG, 'w', encoding='utf-8') as g:
    g.write('\n'.join(log_lines))
