import curses


HELP_TEXT = "Arrow keys: navigate | Enter: new line | Backspace: delete | Ctrl+S: save & exit | Esc: cancel"


def edit_card_list(cards: list[str]) -> list[str] | None:
    """Open an interactive terminal editor for a list of card names.

    Returns the edited list, or None if the user cancelled (Esc).
    """
    lines = [c for c in cards] if cards else [""]
    return curses.wrapper(_editor_main, lines)


def _editor_main(stdscr: curses.window, lines: list[str]) -> list[str] | None:
    curses.curs_set(1)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)

    cursor_y = 0
    cursor_x = 0
    scroll_offset = 0
    saved = False

    while True:
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()
        edit_height = max_y - 2  # reserve 2 lines for status/help

        # Draw header
        header = f" Editing {len(lines)} card(s) "
        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        stdscr.addnstr(0, 0, header.ljust(max_x), max_x)
        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        # Draw card lines
        for row in range(edit_height):
            line_idx = scroll_offset + row
            screen_row = row + 1  # offset by header

            if line_idx < len(lines):
                # Line number gutter
                gutter = f"{line_idx + 1:>4} "
                stdscr.attron(curses.color_pair(2))
                stdscr.addnstr(screen_row, 0, gutter, max_x)
                stdscr.attroff(curses.color_pair(2))

                # Card text (truncate to fit)
                text = lines[line_idx]
                available = max_x - len(gutter) - 1
                stdscr.addnstr(screen_row, len(gutter), text[:available], available)

        # Draw help bar
        help_row = max_y - 1
        stdscr.attron(curses.color_pair(1))
        stdscr.addnstr(help_row, 0, HELP_TEXT.ljust(max_x)[:max_x - 1], max_x - 1)
        stdscr.attroff(curses.color_pair(1))

        # Position cursor
        gutter_width = 5
        screen_y = cursor_y - scroll_offset + 1
        screen_x = gutter_width + cursor_x
        if 0 < screen_y < max_y - 1 and screen_x < max_x:
            stdscr.move(screen_y, screen_x)

        stdscr.refresh()

        key = stdscr.getch()

        if key == 27:  # Esc
            break

        if key == 19:  # Ctrl+S
            saved = True
            break

        if key == curses.KEY_UP:
            if cursor_y > 0:
                cursor_y -= 1
                cursor_x = min(cursor_x, len(lines[cursor_y]))
                if cursor_y < scroll_offset:
                    scroll_offset = cursor_y

        elif key == curses.KEY_DOWN:
            if cursor_y < len(lines) - 1:
                cursor_y += 1
                cursor_x = min(cursor_x, len(lines[cursor_y]))
                if cursor_y >= scroll_offset + edit_height:
                    scroll_offset = cursor_y - edit_height + 1

        elif key == curses.KEY_LEFT:
            if cursor_x > 0:
                cursor_x -= 1
            elif cursor_y > 0:
                cursor_y -= 1
                cursor_x = len(lines[cursor_y])
                if cursor_y < scroll_offset:
                    scroll_offset = cursor_y

        elif key == curses.KEY_RIGHT:
            if cursor_x < len(lines[cursor_y]):
                cursor_x += 1
            elif cursor_y < len(lines) - 1:
                cursor_y += 1
                cursor_x = 0
                if cursor_y >= scroll_offset + edit_height:
                    scroll_offset = cursor_y - edit_height + 1

        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if cursor_x > 0:
                line = lines[cursor_y]
                lines[cursor_y] = line[:cursor_x - 1] + line[cursor_x:]
                cursor_x -= 1
            elif cursor_y > 0:
                # Merge with previous line
                cursor_x = len(lines[cursor_y - 1])
                lines[cursor_y - 1] += lines[cursor_y]
                lines.pop(cursor_y)
                cursor_y -= 1
                if cursor_y < scroll_offset:
                    scroll_offset = cursor_y

        elif key in (curses.KEY_DC, 330):  # Delete key
            line = lines[cursor_y]
            if cursor_x < len(line):
                lines[cursor_y] = line[:cursor_x] + line[cursor_x + 1:]
            elif cursor_y < len(lines) - 1:
                # Merge next line into current
                lines[cursor_y] += lines[cursor_y + 1]
                lines.pop(cursor_y + 1)

        elif key in (curses.KEY_ENTER, 10, 13):
            line = lines[cursor_y]
            lines[cursor_y] = line[:cursor_x]
            lines.insert(cursor_y + 1, line[cursor_x:])
            cursor_y += 1
            cursor_x = 0
            if cursor_y >= scroll_offset + edit_height:
                scroll_offset = cursor_y - edit_height + 1

        elif key == curses.KEY_HOME:
            cursor_x = 0

        elif key == curses.KEY_END:
            cursor_x = len(lines[cursor_y])

        elif 32 <= key <= 126:
            line = lines[cursor_y]
            lines[cursor_y] = line[:cursor_x] + chr(key) + line[cursor_x:]
            cursor_x += 1

    if not saved:
        return None

    # Filter out empty lines and strip whitespace
    return [line.strip() for line in lines if line.strip()]
