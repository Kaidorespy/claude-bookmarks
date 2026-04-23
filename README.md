# Claude Bookmarks

![Status](https://img.shields.io/badge/status-100%25-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Mac%20%7C%20Linux-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Save and resume your Claude Code conversations.

![Claude Bookmarks Screenshot](screenshot.png)

## What is this?

A desktop app for managing Claude Code sessions. Browse your conversation history, bookmark the important ones, and quickly resume where you left off.

Built because scrolling through `~/.claude/projects/` looking for "that one conversation from October" is not a vibe.

## Features

**Session Browser**
- View all your Claude Code sessions in one place
- Smart filtering: Conversations vs Subagents vs Hidden
- Search by message content, project path, or model name
- Sort by date, message count, or file size
- Date range filter for archaeology mode

**Bookmarks**
- Save conversations with custom titles, descriptions, and tags
- Add emoji icons for visual organization
- Search and filter bookmarks by tag
- Edit or delete bookmarks anytime

**Session Preview**
- Preview last 10 messages before resuming
- Full transcript view for subagent sessions
- Color-coded messages (You / Claude / System)

**Resume Command Builder**
- Toggleable flags (--dangerously-skip-permissions, --permission-mode, --model)
- Model selector (Opus 4.5, Opus 4.6, Sonnet 4.5, Haiku 4.5)
- One-click copy to clipboard

**Customization**
- Theme colors (accent + Claude color)
- 6 color presets or enter any hex code
- Settings persist across sessions

## Installation

**Requirements:**
- Python 3.10+
- CustomTkinter

```bash
# Clone or download
git clone https://github.com/yourusername/claude-bookmarks.git
cd claude-bookmarks

# Install dependencies
pip install customtkinter

# Run
python main.py
```

## Usage

**Browse Sessions:**
1. Click "Browse All Sessions"
2. Use filters (Conversations / Subagents / Hidden)
3. Search, sort, or set date range to find what you need

**Bookmark a Conversation:**
1. Find the session you want
2. Click "Bookmark"
3. Add title, description, tags, and optional emoji
4. Click "Save Bookmark"

**Resume a Session:**
1. Open a bookmark or session preview
2. Toggle the flags you want
3. Select your model
4. Click "Copy to Clipboard"
5. Paste into terminal

**Customize Theme:**
1. Click the ⚙ gear icon
2. Pick accent color (your messages, buttons)
3. Pick Claude color (Claude's messages)
4. Save

## Files

The app stores data in `~/.claude-bookmarks/`:
- `bookmarks.json` - Your saved bookmarks
- `settings.json` - Theme and preferences
- `hidden_sessions.json` - Sessions you've hidden

## Subagent Detection

The app automatically distinguishes between real conversations and automated sessions (subagents, daemons, warmups) based on:
- Session ID prefix (`agent-*`)
- First message patterns (explore prompts, daemon wake-ups)
- Message count (50+ messages = probably a real conversation)
- Project directory patterns

## V2 Ideas

- [ ] Minimize to system tray
- [ ] Configurable subagent detection threshold
- [ ] Export/import bookmarks
- [ ] Keyboard shortcuts
- [ ] Session statistics dashboard
- [ ] Auto-redact usernames in screenshots

## License

MIT - Do whatever you want with it.

---

Built with Claude Code, obviously.
