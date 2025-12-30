from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch


SECTION_HEADERS = {
    "SUMMARY", "EDUCATION", "EXPERIENCE", "SKILLS", "PROJECTS", "CERTIFICATIONS", "AWARDS"
}

def render_resume_pdf(resume_text: str) -> BytesIO:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER

    # margins
    left = 0.75 * inch
    right = 0.75 * inch
    top = 0.75 * inch
    bottom = 0.75 * inch

    # typography
    font_body = "Helvetica"
    font_bold = "Helvetica-Bold"
    body_size = 10.5
    header_size = 12.5
    leading = 13.5

    # layout
    y = height - top
    max_width = width - left - right

    def new_page():
        nonlocal y
        c.showPage()
        y = height - top

    def ensure_space(lines_needed: int = 1):
        nonlocal y
        if y - (leading * lines_needed) <= bottom:
            new_page()

    def wrap_text(text: str, font: str, size: float, avail_width: float) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        cur = words[0]
        for w in words[1:]:
            test = cur + " " + w
            if c.stringWidth(test, font, size) <= avail_width:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    def draw_line(text: str, font: str, size: float, x: float, avail_width: float):
        nonlocal y
        c.setFont(font, size)
        for line in wrap_text(text, font, size, avail_width):
            ensure_space(1)
            c.drawString(x, y, line)
            y -= leading

    def draw_blank(lines: int = 1):
        nonlocal y
        ensure_space(lines)
        y -= leading * lines

    def is_section_header(line: str) -> bool:
        s = line.strip()
        return s.isupper() and s in SECTION_HEADERS

    def is_bullet(line: str) -> bool:
        s = line.lstrip()
        return s.startswith("•") or s.startswith("-") or s.startswith("*")

    # Parse lines
    lines = resume_text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\n")
        line = raw.rstrip()

        # blank line
        if line.strip() == "":
            draw_blank(0.5)
            i += 1
            continue

        # SECTION HEADER
        if is_section_header(line):
            # extra top space between sections
            draw_blank(0.3)
            ensure_space(2)
            c.setFont(font_bold, header_size)
            c.drawString(left, y, line.strip())
            y -= leading * 1.1

            # divider line
            c.setLineWidth(0.6)
            c.line(left, y + 4, width - right, y + 4)
            y -= leading * 0.5

            # Special handling: 2-column SKILLS block if present
            if line.strip() == "SKILLS":
                # Collect consecutive non-empty lines until next section header
                block: list[str] = []
                j = i + 1
                while j < len(lines):
                    nxt = lines[j].rstrip()
                    if nxt.strip() == "":
                        # keep going but don't include empties in skills block
                        j += 1
                        continue
                    if is_section_header(nxt):
                        break
                    block.append(nxt.strip())
                    j += 1

                if block:
                    # Flatten skill items. Supports:
                    # - "• Category: item, item"
                    # - "Category: item, item"
                    # - "item, item"
                    items: list[str] = []
                    for b in block:
                        b2 = b.lstrip("•").strip()
                        # if "Category: ..." keep the whole line as an item
                        items.append(b2)

                    # Draw in 2 columns
                    col_gap = 0.4 * inch
                    col_w = (max_width - col_gap) / 2
                    x1 = left
                    x2 = left + col_w + col_gap

                    # Render as wrapped lines in two columns, balancing by index
                    # (simple approach; good enough for MVP)
                    left_items = items[0::2]
                    right_items = items[1::2]

                    # Measure how many wrapped lines will be used, to ensure space
                    def count_wrapped(it_list: list[str], avail: float) -> int:
                        n = 0
                        for it in it_list:
                            n += len(wrap_text(it, font_body, body_size, avail))
                        return n

                    needed = max(count_wrapped(left_items, col_w), count_wrapped(right_items, col_w)) + 1
                    ensure_space(needed)

                    # Draw left column
                    y_start = y
                    y_left = y_start
                    c.setFont(font_body, body_size)
                    for it in left_items:
                        for wline in wrap_text(it, font_body, body_size, col_w):
                            if y_left - leading <= bottom:
                                new_page()
                                y_start = y
                                y_left = y_start
                            c.drawString(x1, y_left, wline)
                            y_left -= leading

                    # Draw right column
                    y_right = y_start
                    for it in right_items:
                        for wline in wrap_text(it, font_body, body_size, col_w):
                            if y_right - leading <= bottom:
                                new_page()
                                y_start = y
                                y_right = y_start
                            c.drawString(x2, y_right, wline)
                            y_right -= leading

                    # Move y down by the max used
                    y = min(y_left, y_right) - leading * 0.3

                i = j
                continue

            i += 1
            continue

        # BULLETS (indent nicely)
        if is_bullet(line):
            bullet_indent = 0.18 * inch
            text_indent = 0.35 * inch
            bullet_char = "•"
            bullet_text = line.lstrip()
            # normalize bullet marker
            bullet_text = bullet_text.lstrip("•-*").strip()

            ensure_space(1)
            c.setFont(font_body, body_size)
            c.drawString(left + bullet_indent, y, bullet_char)

            # wrap bullet content with hanging indent
            avail = max_width - text_indent
            wrapped = wrap_text(bullet_text, font_body, body_size, avail)
            if wrapped:
                c.drawString(left + text_indent, y, wrapped[0])
                y -= leading
                for cont in wrapped[1:]:
                    ensure_space(1)
                    c.drawString(left + text_indent, y, cont)
                    y -= leading
            else:
                y -= leading

            i += 1
            continue

        # Name line (first non-empty line) -> slightly bigger + bold
        if i == 0:
            ensure_space(2)
            c.setFont(font_bold, 14)
            c.drawString(left, y, line.strip())
            y -= leading * 1.3
            i += 1
            continue

        # If line looks like role/company heading -> bold
        # heuristic: short-ish line without bullet and not a section header
        if len(line) <= 60 and ("|" in line or "Developer" in line or "Engineer" in line):
            draw_line(line.strip(), font_bold, body_size, left, max_width)
            i += 1
            continue

        # Normal line
        draw_line(line.strip(), font_body, body_size, left, max_width)
        i += 1

    c.save()
    buf.seek(0)
    return buf
