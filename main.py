"""Claude Bookmarks - Save and resume Claude Code sessions."""

import sys
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
import customtkinter as ctk

# === Config ===
CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
BOOKMARKS_FILE = Path.home() / ".claude-bookmarks" / "bookmarks.json"
HIDDEN_FILE = Path.home() / ".claude-bookmarks" / "hidden_sessions.json"
SETTINGS_FILE = Path.home() / ".claude-bookmarks" / "settings.json"
SESSION_CACHE_FILE = Path.home() / ".claude-bookmarks" / "session_cache.json"
BOOKMARKS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Default settings
DEFAULT_SETTINGS = {
    "accent_color": "#00d4ff",  # Cyan
    "claude_color": "#c084fc",  # Soft purple
}

# Color presets
COLOR_PRESETS = {
    "Cyan": "#00d4ff",
    "Lavender": "#c084fc",
    "Magenta": "#d946ef",
    "Green": "#2ed573",
    "Orange": "#ffa502",
    "Gold": "#fbbf24",
}


def load_settings() -> dict:
    """Load user settings."""
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            # Merge with defaults for any missing keys
            return {**DEFAULT_SETTINGS, **settings}
        except (json.JSONDecodeError, OSError):
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict):
    """Save user settings."""
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")

# === Theme (matching Convergence) ===
COLORS = {
    "bg": "#0a0a0a",
    "surface": "#141414",
    "surface_hover": "#1f1f1f",
    "accent": "#00d4ff",
    "accent_hover": "#00a8cc",
    "accent_dim": "#007a99",
    "text": "#fafafa",
    "text_dim": "#888888",
    "border": "#2a2a2a",
    "warning": "#ffa502",
    "danger": "#ff4757",
    "success": "#2ed573",
}

# Default flags for resume command
DEFAULT_FLAGS = {
    "dangerously_skip_permissions": False,
    "permission_mode": None,
    "model": None,
}

# Flag descriptions for tooltips
FLAG_TOOLTIPS = {
    "dangerously_skip_permissions": "Skip all permission prompts (use with caution)",
    "permission_mode": "Set permission mode (bypassPermissions = no prompts)",
    "model": "Force a specific model version",
}


class Tooltip:
    """Simple tooltip implementation for CustomTkinter widgets."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
        # Without this, switching views while hovering leaves the tooltip
        # floating on screen forever (overrideredirect windows have no close button)
        widget.bind("<Destroy>", self._hide)

    def _show(self, event=None):
        if self.tooltip_window:
            return
        if not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tooltip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(fg_color=COLORS["surface_hover"])

        label = ctk.CTkLabel(
            tw,
            text=self.text,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text"],
            fg_color=COLORS["surface_hover"],
            corner_radius=6,
            padx=10,
            pady=5
        )
        label.pack()

    def _hide(self, event=None):
        if self.tooltip_window:
            try:
                self.tooltip_window.destroy()
            except Exception:
                pass
            self.tooltip_window = None


def load_bookmarks() -> list[dict]:
    """Load saved bookmarks."""
    if BOOKMARKS_FILE.exists():
        try:
            return json.loads(BOOKMARKS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Failed to load bookmarks: {e}")
            return []
    return []


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


# Common emojis for bookmarks
BOOKMARK_EMOJIS = [
    "📌", "⭐", "🔥", "💡", "🚀", "🎯", "💎", "🔮",
    "🧠", "💬", "🛠️", "📝", "🎨", "🔧", "⚡", "🌟",
]


def save_bookmarks(bookmarks: list[dict]):
    """Save bookmarks to file."""
    BOOKMARKS_FILE.write_text(json.dumps(bookmarks, indent=2), encoding="utf-8")


def load_hidden() -> set[str]:
    """Load hidden session IDs."""
    if HIDDEN_FILE.exists():
        try:
            return set(json.loads(HIDDEN_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Failed to load hidden sessions: {e}")
            return set()
    return set()


def save_hidden(hidden: set[str]):
    """Save hidden session IDs."""
    HIDDEN_FILE.write_text(json.dumps(list(hidden), indent=2), encoding="utf-8")


def clean_message_content(content) -> str:
    """Clean internal markers from message content for display."""
    # Recursively extract text from complex structures
    def extract_text(obj) -> str:
        if obj is None:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            if obj.get("type") == "text":
                return obj.get("text", "")
            # Try common content keys
            for key in ["text", "content", "value"]:
                if key in obj:
                    return extract_text(obj[key])
            return ""
        if isinstance(obj, list):
            return " ".join(extract_text(item) for item in obj)
        return str(obj)

    content = extract_text(content)

    # Remove <synthetic> tags and their content
    content = re.sub(r'<synthetic>.*?</synthetic>', '', content, flags=re.DOTALL)
    # Remove other common internal tags
    content = re.sub(r'<[a-z_-]+>.*?</[a-z_-]+>', '', content, flags=re.DOTALL)
    # Clean up extra whitespace
    content = re.sub(r'\s+', ' ', content).strip()
    return content


def decode_project_dir_name(name: str) -> str:
    """Lossy fallback for sessions with no cwd field: the encoding replaced both
    path separators and real hyphens with '-', so hyphenated folder names mangle."""
    m = re.match(r"^([A-Za-z])--(.*)$", name)
    if m:
        return f"{m.group(1)}:\\" + m.group(2).replace("-", "\\")
    return name.replace("-", "/")


def _load_session_cache() -> dict:
    if SESSION_CACHE_FILE.exists():
        try:
            return json.loads(SESSION_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_session_cache(cache: dict):
    try:
        SESSION_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def get_all_sessions() -> list[dict]:
    """Scan all sessions from .claude directory."""
    sessions = []

    if not PROJECTS_DIR.exists():
        return sessions

    cache = _load_session_cache()
    fresh_cache = {}

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        fallback_name = decode_project_dir_name(project_dir.name)

        for session_file in project_dir.glob("*.jsonl"):
            session_id = session_file.stem

            # Get basic info from file
            try:
                stat = session_file.stat()
                modified = datetime.fromtimestamp(stat.st_mtime)
                size = stat.st_size

                # Skip files smaller than ~100 bytes (basically empty sessions)
                if size < 100:
                    continue

                # Reuse cached parse if the file hasn't changed
                cache_key = str(session_file)
                cached = cache.get(cache_key)
                if cached and cached.get("mtime") == stat.st_mtime and cached.get("size") == size:
                    entry = dict(cached["session"])
                    entry["modified"] = datetime.fromtimestamp(entry["modified"])
                    sessions.append(entry)
                    fresh_cache[cache_key] = cached
                    continue

                # Try to get first and last messages
                first_msg = None
                last_msg = None
                model = None
                cwd = None
                message_count = 0

                with open(session_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line)

                            if cwd is None and data.get("cwd"):
                                cwd = data.get("cwd")

                            if data.get("type") == "user":
                                message_count += 1
                                if first_msg is None:
                                    first_msg = data.get("message", {}).get("content", "")
                                last_msg = data.get("message", {}).get("content", "")
                            elif data.get("type") == "assistant":
                                msg = data.get("message", {})
                                if msg.get("model"):
                                    model = msg.get("model")
                        except json.JSONDecodeError:
                            continue

                # Real project path from the session itself; the encoded folder
                # name is a lossy fallback
                project_name = cwd or fallback_name

                # Detect if this looks like a subagent/daemon session
                is_subagent = False
                first_lower = (first_msg or "").lower().strip()

                # ESCAPE HATCH: Lots of messages = real conversation, even with weird first message
                # Subagents rarely exceed 50 messages (configurable in future settings)
                is_long_conversation = message_count >= 50

                # 0. Session ID starts with "agent-" = definitely a subagent
                if session_id.startswith("agent-"):
                    is_subagent = True
                # 1. Zero user messages = not a real conversation
                elif message_count == 0:
                    is_subagent = True
                # 2. Warmup sessions (Claude Code internal)
                elif first_lower == "warmup":
                    is_subagent = True
                # 3. Workshop/daemon directory patterns (always subagent, regardless of length)
                elif "workshop" in project_name.lower() or "daemon" in project_name.lower():
                    is_subagent = True
                # Skip remaining checks if it's a long conversation
                elif is_long_conversation:
                    is_subagent = False
                # 4. Explore agent pattern - starts with "explore" + path
                elif first_lower.startswith("explore ") and (":\\" in first_msg or ":/" in first_msg or "c:\\" in first_lower):
                    is_subagent = True
                # 5. Task agent prompt patterns
                elif first_lower.startswith("i need to understand") and len(first_msg) > 100:
                    is_subagent = True
                # 6. Daemon wake-up pattern
                elif "you are waking up" in first_lower:
                    is_subagent = True
                # 7. Witness/observer prompts (short sessions only)
                elif first_lower.startswith("witness prompt:") or first_lower.startswith("you are being asked to witness"):
                    is_subagent = True
                # 8. Very long first message with MULTIPLE agent-like patterns
                elif len(first_msg) > 500 and sum(1 for kw in ["thoroughly", "comprehensive", "i need to understand", "explore the", "investigate the", "analyze the"] if kw in first_lower) >= 2:
                    is_subagent = True

                # Detect if session hit context limits (check for "Prompt is too long" error)
                context_collapsed = False
                hit_context_limit = message_count >= 50 or size > 5_000_000  # 50+ msgs or 5MB+

                # Check end of file for context collapse signature
                try:
                    with open(session_file, "rb") as f:
                        f.seek(max(0, size - 3000))  # Read last 3KB
                        tail = f.read().decode("utf-8", errors="ignore")
                        if '"Prompt is too long"' in tail and '"error":"invalid_request"' in tail:
                            context_collapsed = True
                except OSError:
                    pass

                entry = {
                    "session_id": session_id,
                    "project": project_name,
                    "project_dir": str(project_dir),
                    "file_path": str(session_file),
                    "modified": modified,
                    "size": size,
                    "cwd": cwd,
                    "first_message": clean_message_content(first_msg)[:200] if first_msg else "",
                    "last_message": clean_message_content(last_msg)[:200] if last_msg else "",
                    "model": model,
                    "message_count": message_count,
                    "is_subagent": is_subagent,
                    "hit_context_limit": hit_context_limit,
                    "context_collapsed": context_collapsed,
                }
                sessions.append(entry)

                cache_entry = dict(entry)
                cache_entry["modified"] = stat.st_mtime
                fresh_cache[cache_key] = {
                    "mtime": stat.st_mtime,
                    "size": size,
                    "session": cache_entry,
                }
            except Exception:
                continue

    # Prunes entries for deleted files as a side effect
    _save_session_cache(fresh_cache)

    # Sort by modified date, newest first
    sessions.sort(key=lambda x: x["modified"], reverse=True)
    return sessions


def get_session_messages(session_file: str, limit: int = 10) -> list[dict]:
    """Get the last N messages from a session."""
    messages = []

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("type") in ("user", "assistant"):
                        role = data.get("type")
                        content = ""

                        if role == "user":
                            content = data.get("message", {}).get("content", "")
                        else:
                            msg_content = data.get("message", {}).get("content", [])
                            for block in msg_content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    content += block.get("text", "")
                                elif isinstance(block, str):
                                    content += block

                        # Clean internal markers
                        content = clean_message_content(content)

                        if content:
                            messages.append({
                                "role": role,
                                "content": content[:500],  # Truncate for preview
                                "timestamp": data.get("timestamp", ""),
                            })
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        print(f"Failed to read session messages: {e}")

    return messages[-limit:]  # Last N messages


def find_session_file(session_id: str) -> Optional[str]:
    """Locate the JSONL file for a session ID."""
    if not PROJECTS_DIR.exists():
        return None
    for project_dir in PROJECTS_DIR.iterdir():
        potential = project_dir / f"{session_id}.jsonl"
        if potential.exists():
            return str(potential)
    return None


def get_session_cwd(session_file: str) -> Optional[str]:
    """Read the session's working directory from its first few entries."""
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > 20:
                    break
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("cwd"):
                    return data["cwd"]
    except OSError:
        pass
    return None


def build_resume_command(session_id: str, flags: dict, project_path: Optional[str] = None) -> str:
    """Build the claude resume command with flags."""
    cmd = "claude"

    if flags.get("dangerously_skip_permissions"):
        cmd += " --dangerously-skip-permissions"

    if flags.get("permission_mode"):
        cmd += f" --permission-mode {flags['permission_mode']}"

    if flags.get("model"):
        cmd += f" --model {flags['model']}"

    cmd += f" --resume {session_id}"

    if project_path:
        # --resume only finds the session when run from its project directory.
        # ';' chains in PowerShell/bash/zsh (not cmd.exe, where it half-works)
        cmd = f'cd "{project_path}" ; {cmd}'

    return cmd


class BookmarksApp(ctk.CTk):
    """Main application."""

    def __init__(self, quick_add_session: str = None):
        super().__init__()

        self.title("Claude Bookmarks")
        self.geometry("950x750")
        self.configure(fg_color=COLORS["bg"])

        self.bookmarks = load_bookmarks()
        self.hidden = load_hidden()
        self.sessions = []
        self.filtered_sessions = []
        self.current_session = None
        self.flags = DEFAULT_FLAGS.copy()
        self.load_more_btn = None
        self.sessions_page = 0
        self.sessions_per_page = 20
        self._came_from_sessions = False
        self.current_filter = "all"  # "all", "subagents", "hidden"
        self.search_text = ""
        self.sort_by = "date_desc"  # "date_desc", "date_asc", "messages", "size"
        self.date_from = None  # datetime or None
        self.date_to = None  # datetime or None
        self.bookmark_sort_by = "date_desc"  # "date_desc", "date_asc", "alpha", "emoji"
        self.bookmark_search_text = ""
        self.settings = load_settings()

        # Apply theme colors from settings
        self._apply_theme()

        self._setup_ui()

        # If launched with a session to bookmark, show add dialog
        if quick_add_session:
            self.after(100, lambda: self._quick_add(quick_add_session))

    def _apply_theme(self):
        """Apply theme colors from settings to COLORS dict."""
        accent = self.settings.get("accent_color", "#00d4ff")
        COLORS["accent"] = accent
        # Derive hover color (slightly darker)
        COLORS["accent_hover"] = self._darken_color(accent, 0.8)
        COLORS["accent_dim"] = self._darken_color(accent, 0.5)

    def _darken_color(self, hex_color: str, factor: float) -> str:
        """Darken a hex color by a factor (0-1)."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        r = int(int(hex_color[0:2], 16) * factor)
        g = int(int(hex_color[2:4], 16) * factor)
        b = int(int(hex_color[4:6], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _setup_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        self._title_label = ctk.CTkLabel(
            header, text="Claude Bookmarks",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["accent"]
        )
        self._title_label.pack(side="left")

        ctk.CTkLabel(
            header, text="Save and resume conversations",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_dim"]
        ).pack(side="left", padx=20)

        # Settings button
        ctk.CTkButton(
            header, text="⚙",
            width=36,
            font=ctk.CTkFont(size=16),
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            command=self._show_settings
        ).pack(side="right")

        # Main content
        self.content = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=12)
        self.content.pack(fill="both", expand=True, padx=20, pady=10)

        self._show_bookmarks()

    def _show_bookmarks(self):
        """Show saved bookmarks."""
        for w in self.content.winfo_children():
            w.destroy()

        # Header with buttons
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            header,
            text=f"Bookmarks ({len(self.bookmarks)})",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        ctk.CTkButton(
            header, text="Browse All Sessions",
            fg_color=COLORS["surface_hover"],
            hover_color=COLORS["border"],
            command=self._show_all_sessions
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            header, text="+ Add Bookmark",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#000000",
            command=self._show_add_bookmark
        ).pack(side="right", padx=5)

        # Search and sort for bookmarks
        if self.bookmarks:
            search_sort_frame = ctk.CTkFrame(self.content, fg_color="transparent")
            search_sort_frame.pack(fill="x", padx=20, pady=(0, 10))

            # Search box
            self.bookmark_search_entry = ctk.CTkEntry(
                search_sort_frame,
                placeholder_text="Search bookmarks...",
                width=180
            )
            self.bookmark_search_entry.pack(side="left")
            self.bookmark_search_entry.bind("<KeyRelease>", self._on_bookmark_search)

            search_hint = ctk.CTkLabel(
                search_sort_frame,
                text="?",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=COLORS["accent_dim"],
                width=20
            )
            search_hint.pack(side="left", padx=(5, 0))
            Tooltip(search_hint, "Searches: title, description, tags")

            # All tags display
            all_tags = set()
            for b in self.bookmarks:
                all_tags.update(b.get("tags", []))
            if all_tags:
                ctk.CTkLabel(
                    search_sort_frame,
                    text="Tags:",
                    font=ctk.CTkFont(size=11),
                    text_color=COLORS["text_dim"]
                ).pack(side="left", padx=(15, 5))
                for tag in sorted(all_tags)[:5]:  # Show first 5 tags
                    tag_btn = ctk.CTkButton(
                        search_sort_frame,
                        text=f"#{tag}",
                        width=len(tag) * 8 + 20,
                        height=24,
                        font=ctk.CTkFont(size=10),
                        fg_color=COLORS["surface_hover"],
                        hover_color=COLORS["border"],
                        command=lambda t=tag: self._filter_by_tag(t)
                    )
                    tag_btn.pack(side="left", padx=2)

            # Sort dropdown
            bookmark_sort_display = {
                "date_desc": "Newest first",
                "date_asc": "Oldest first",
                "alpha": "A-Z",
                "emoji": "By icon",
            }

            ctk.CTkLabel(
                search_sort_frame,
                text="Sort:",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_dim"]
            ).pack(side="left", padx=(15, 5))

            self.bookmark_sort_menu = ctk.CTkOptionMenu(
                search_sort_frame,
                values=["Newest first", "Oldest first", "A-Z", "By icon"],
                width=120,
                fg_color=COLORS["surface_hover"],
                button_color=COLORS["surface_hover"],
                button_hover_color=COLORS["border"],
                command=self._on_bookmark_sort_change
            )
            self.bookmark_sort_menu.set(bookmark_sort_display.get(self.bookmark_sort_by, "Newest first"))
            self.bookmark_sort_menu.pack(side="left", padx=5)

        if not self.bookmarks:
            ctk.CTkLabel(
                self.content,
                text="No bookmarks yet.\n\nBookmark a session to quickly resume it later.",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["text_dim"],
                justify="center"
            ).pack(pady=50)
            return

        # Bookmarks list
        self._bookmark_scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        self._bookmark_scroll.pack(fill="both", expand=True, padx=20, pady=10)

        # Pre-fill search if we have a filter
        if hasattr(self, 'bookmark_search_entry') and self.bookmark_search_text:
            self.bookmark_search_entry.delete(0, "end")
            self.bookmark_search_entry.insert(0, self.bookmark_search_text)

        # Sort and filter bookmarks
        sorted_bookmarks = self._get_sorted_bookmarks()
        for bookmark in sorted_bookmarks:
            self._create_bookmark_card(self._bookmark_scroll, bookmark)

    def _create_bookmark_card(self, parent, bookmark: dict):
        """Create a card for a bookmark."""
        card = ctk.CTkFrame(parent, fg_color=COLORS["surface_hover"], corner_radius=10)
        card.pack(fill="x", pady=5)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        # Date and tags
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x")

        date_str = bookmark.get("created", "Unknown date")
        ctk.CTkLabel(
            top_row,
            text=date_str,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"]
        ).pack(side="left")

        tags = bookmark.get("tags", [])
        if tags:
            tags_str = " ".join(f"#{t}" for t in tags)
            ctk.CTkLabel(
                top_row,
                text=tags_str,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["accent_dim"]
            ).pack(side="left", padx=10)

        # Title with optional emoji
        title_frame = ctk.CTkFrame(inner, fg_color="transparent")
        title_frame.pack(anchor="w", fill="x")

        emoji = bookmark.get("emoji", "")
        title_text = f"{emoji} {bookmark.get('title', 'Untitled')}" if emoji else bookmark.get("title", "Untitled")
        ctk.CTkLabel(
            title_frame,
            text=title_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        # Description
        desc = bookmark.get("description", "")
        if desc:
            ctk.CTkLabel(
                inner,
                text=desc[:150] + "..." if len(desc) > 150 else desc,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_dim"],
                wraplength=500,
                justify="left"
            ).pack(anchor="w", pady=(5, 0))

        # Action buttons
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))

        def copy_cmd():
            session_file = find_session_file(bookmark["session_id"])
            cwd = get_session_cwd(session_file) if session_file else None
            cmd = build_resume_command(bookmark["session_id"], self.flags, cwd)
            self.clipboard_clear()
            self.clipboard_append(cmd)
            copy_btn.configure(text="Copied!")
            self.after(1500, lambda: copy_btn.configure(text="Copy Command"))

        copy_btn = ctk.CTkButton(
            btn_frame, text="Copy Command",
            width=120,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#000000",
            command=copy_cmd
        )
        copy_btn.pack(side="left", padx=(0, 10))

        def show_preview_from_bookmarks(b):
            self._came_from_sessions = False
            self._show_preview(b)

        ctk.CTkButton(
            btn_frame, text="Preview",
            width=80,
            fg_color=COLORS["surface"],
            hover_color=COLORS["border"],
            command=lambda b=bookmark: show_preview_from_bookmarks(b)
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Delete",
            width=70,
            fg_color="transparent",
            hover_color=COLORS["danger"],
            text_color=COLORS["text_dim"],
            command=lambda b=bookmark: self._delete_bookmark(b)
        ).pack(side="right")

        ctk.CTkButton(
            btn_frame, text="Edit",
            width=60,
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["text_dim"],
            command=lambda b=bookmark: self._show_edit_bookmark(b)
        ).pack(side="right", padx=(0, 5))

    def _show_all_sessions(self):
        """Show all sessions for browsing."""
        for w in self.content.winfo_children():
            w.destroy()

        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            header,
            text="All Sessions",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        ctk.CTkButton(
            header, text="← Bookmarks",
            fg_color=COLORS["surface_hover"],
            hover_color=COLORS["border"],
            command=self._show_bookmarks
        ).pack(side="right")

        # Loading indicator
        loading = ctk.CTkLabel(
            self.content,
            text="Scanning sessions...",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_dim"]
        )
        loading.pack(pady=50)

        self.update()

        # Load sessions
        self.sessions = get_all_sessions()
        loading.destroy()

        if not self.sessions:
            ctk.CTkLabel(
                self.content,
                text="No sessions found.",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["text_dim"]
            ).pack(pady=50)
            return

        self.sessions_count_label = ctk.CTkLabel(
            header,
            text=f"({len(self.sessions)} sessions)",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_dim"]
        )
        self.sessions_count_label.pack(side="left", padx=10)

        # Filter buttons
        filter_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        filter_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            filter_frame,
            text="Filter:",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_dim"]
        ).pack(side="left", padx=(0, 10))

        def set_filter(f):
            self.current_filter = f
            self._apply_filter()

        self.filter_all_btn = ctk.CTkButton(
            filter_frame, text="All",
            width=50, height=28,
            fg_color=COLORS["accent"] if self.current_filter == "all" else COLORS["surface_hover"],
            text_color="#000000" if self.current_filter == "all" else COLORS["text"],
            command=lambda: set_filter("all")
        )
        self.filter_all_btn.pack(side="left", padx=2)

        self.filter_convos_btn = ctk.CTkButton(
            filter_frame, text="Conversations",
            width=100, height=28,
            fg_color=COLORS["accent"] if self.current_filter == "conversations" else COLORS["surface_hover"],
            text_color="#000000" if self.current_filter == "conversations" else COLORS["text"],
            command=lambda: set_filter("conversations")
        )
        self.filter_convos_btn.pack(side="left", padx=2)

        self.filter_subagent_btn = ctk.CTkButton(
            filter_frame, text="Subagents",
            width=80, height=28,
            fg_color=COLORS["accent"] if self.current_filter == "subagents" else COLORS["surface_hover"],
            text_color="#000000" if self.current_filter == "subagents" else COLORS["text"],
            command=lambda: set_filter("subagents")
        )
        self.filter_subagent_btn.pack(side="left", padx=2)

        self.filter_hidden_btn = ctk.CTkButton(
            filter_frame, text=f"Hidden ({len(self.hidden)})",
            width=90, height=28,
            fg_color=COLORS["accent"] if self.current_filter == "hidden" else COLORS["surface_hover"],
            text_color="#000000" if self.current_filter == "hidden" else COLORS["text"],
            command=lambda: set_filter("hidden")
        )
        self.filter_hidden_btn.pack(side="left", padx=2)

        # Search, sort, and date range row (combined)
        search_sort_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        search_sort_frame.pack(fill="x", padx=20, pady=(0, 10))

        # Search box
        self.search_entry = ctk.CTkEntry(
            search_sort_frame,
            placeholder_text="Search",
            width=160
        )
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", self._on_search)

        search_hint = ctk.CTkLabel(
            search_sort_frame,
            text="?",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["accent_dim"],
            width=20
        )
        search_hint.pack(side="left", padx=(5, 0))
        Tooltip(search_hint, "Searches: first/last message, project path, model name (opus/sonnet/haiku)")

        # Sort dropdown
        ctk.CTkLabel(
            search_sort_frame,
            text="Sort:",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_dim"]
        ).pack(side="left", padx=(15, 5))

        # Map internal sort values to display names
        sort_display = {
            "date_desc": "Date (newest)",
            "date_asc": "Date (oldest)",
            "messages_desc": "Messages (most)",
            "messages_asc": "Messages (least)",
            "size_desc": "Size (largest)",
            "size_asc": "Size (smallest)",
        }

        self.sort_menu = ctk.CTkOptionMenu(
            search_sort_frame,
            values=["Date (newest)", "Date (oldest)", "Messages (most)", "Messages (least)", "Size (largest)", "Size (smallest)"],
            width=130,
            fg_color=COLORS["surface_hover"],
            button_color=COLORS["surface_hover"],
            button_hover_color=COLORS["border"],
            command=self._on_sort_change
        )
        self.sort_menu.set(sort_display.get(self.sort_by, "Date (newest)"))
        self.sort_menu.pack(side="left")

        # Date range (same row)
        self.date_from_entry = ctk.CTkEntry(
            search_sort_frame,
            placeholder_text="From (YYYY-MM-DD)",
            width=120
        )
        self.date_from_entry.pack(side="left", padx=(15, 0))
        if self.date_from:
            self.date_from_entry.insert(0, self.date_from.strftime("%Y-%m-%d"))

        ctk.CTkLabel(
            search_sort_frame,
            text="to",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"]
        ).pack(side="left", padx=5)

        self.date_to_entry = ctk.CTkEntry(
            search_sort_frame,
            placeholder_text="To (YYYY-MM-DD)",
            width=120
        )
        self.date_to_entry.pack(side="left")
        if self.date_to:
            self.date_to_entry.insert(0, self.date_to.strftime("%Y-%m-%d"))

        ctk.CTkButton(
            search_sort_frame,
            text="Apply",
            width=50,
            height=28,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#000000",
            command=self._apply_date_filter
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            search_sort_frame,
            text="Clear",
            width=45,
            height=28,
            fg_color=COLORS["surface_hover"],
            hover_color=COLORS["border"],
            command=self._clear_date_filter
        ).pack(side="left", padx=(5, 0))

        # Sessions list
        self.sessions_scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        self.sessions_scroll.pack(fill="both", expand=True, padx=20, pady=10)

        # Apply initial filter and paginate
        self._apply_filter()

    def _apply_filter(self):
        """Apply current filter and reset pagination."""
        # Filter sessions based on current filter
        if self.current_filter == "all":
            self.filtered_sessions = [s for s in self.sessions if s["session_id"] not in self.hidden]
        elif self.current_filter == "conversations":
            self.filtered_sessions = [s for s in self.sessions if not s.get("is_subagent") and s["session_id"] not in self.hidden]
        elif self.current_filter == "subagents":
            self.filtered_sessions = [s for s in self.sessions if s.get("is_subagent") and s["session_id"] not in self.hidden]
        elif self.current_filter == "hidden":
            self.filtered_sessions = [s for s in self.sessions if s["session_id"] in self.hidden]

        # Update button colors and text colors
        self.filter_all_btn.configure(
            fg_color=COLORS["accent"] if self.current_filter == "all" else COLORS["surface_hover"],
            text_color="#000000" if self.current_filter == "all" else COLORS["text"]
        )
        self.filter_convos_btn.configure(
            fg_color=COLORS["accent"] if self.current_filter == "conversations" else COLORS["surface_hover"],
            text_color="#000000" if self.current_filter == "conversations" else COLORS["text"]
        )
        self.filter_subagent_btn.configure(
            fg_color=COLORS["accent"] if self.current_filter == "subagents" else COLORS["surface_hover"],
            text_color="#000000" if self.current_filter == "subagents" else COLORS["text"]
        )
        self.filter_hidden_btn.configure(
            fg_color=COLORS["accent"] if self.current_filter == "hidden" else COLORS["surface_hover"],
            text_color="#000000" if self.current_filter == "hidden" else COLORS["text"],
            text=f"Hidden ({len(self.hidden)})"
        )

        # Update count
        self.sessions_count_label.configure(text=f"({len(self.filtered_sessions)} sessions)")

        # Apply search filter
        if self.search_text:
            search_lower = self.search_text.lower()
            self.filtered_sessions = [
                s for s in self.filtered_sessions
                if search_lower in s.get("first_message", "").lower()
                or search_lower in s.get("last_message", "").lower()
                or search_lower in s.get("project", "").lower()
                or search_lower in s.get("session_id", "").lower()
                or search_lower in (s.get("model") or "").lower()
            ]

        # Apply date range filter
        if self.date_from:
            self.filtered_sessions = [s for s in self.filtered_sessions if s["modified"] >= self.date_from]
        if self.date_to:
            self.filtered_sessions = [s for s in self.filtered_sessions if s["modified"] <= self.date_to]

        # Apply sort
        if self.sort_by == "date_desc":
            self.filtered_sessions.sort(key=lambda x: x["modified"], reverse=True)
        elif self.sort_by == "date_asc":
            self.filtered_sessions.sort(key=lambda x: x["modified"])
        elif self.sort_by == "messages_desc":
            self.filtered_sessions.sort(key=lambda x: x.get("message_count", 0), reverse=True)
        elif self.sort_by == "messages_asc":
            self.filtered_sessions.sort(key=lambda x: x.get("message_count", 0))
        elif self.sort_by == "size_desc":
            self.filtered_sessions.sort(key=lambda x: x.get("size", 0), reverse=True)
        elif self.sort_by == "size_asc":
            self.filtered_sessions.sort(key=lambda x: x.get("size", 0))

        # Clear scroll and reset pagination
        for w in self.sessions_scroll.winfo_children():
            w.destroy()

        self.sessions_page = 0
        self._load_more_sessions()

    def _on_search(self, event=None):
        """Handle search input with debounce."""
        # Cancel previous pending search
        if hasattr(self, '_search_timer') and self._search_timer:
            self.after_cancel(self._search_timer)

        # Schedule search after 300ms of no typing
        self._search_timer = self.after(300, self._do_search)

    def _do_search(self):
        """Actually perform the search."""
        # The debounce timer can fire after a view switch destroyed the entry
        if not (hasattr(self, 'search_entry') and self.search_entry.winfo_exists()):
            return
        self.search_text = self.search_entry.get().strip()
        self._apply_filter()

    def _parse_date(self, date_str: str):
        """Parse date from various formats."""
        if not date_str:
            return None
        date_str = date_str.strip()

        # Try multiple formats
        formats = [
            "%Y-%m-%d",      # 2025-10-03
            "%m/%d/%Y",      # 10/03/2025
            "%m/%d/%y",      # 10/03/25
            "%b %d %Y",      # Oct 03 2025
            "%b %d, %Y",     # Oct 03, 2025
            "%B %d %Y",      # October 03 2025
            "%B %d, %Y",     # October 03, 2025
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _apply_date_filter(self):
        """Apply date range filter."""
        from_str = self.date_from_entry.get().strip()
        to_str = self.date_to_entry.get().strip()

        self.date_from = self._parse_date(from_str)
        self.date_to = self._parse_date(to_str)
        if self.date_to:
            self.date_to = self.date_to.replace(hour=23, minute=59, second=59)

        self._apply_filter()

    def _clear_date_filter(self):
        """Clear date range filter."""
        self.date_from = None
        self.date_to = None
        self.date_from_entry.delete(0, "end")
        self.date_to_entry.delete(0, "end")
        self._apply_filter()

    def _on_sort_change(self, choice: str):
        """Handle sort selection."""
        sort_map = {
            "Date (newest)": "date_desc",
            "Date (oldest)": "date_asc",
            "Messages (most)": "messages_desc",
            "Messages (least)": "messages_asc",
            "Size (largest)": "size_desc",
            "Size (smallest)": "size_asc",
        }
        self.sort_by = sort_map.get(choice, "date_desc")
        self._apply_filter()

    def _on_bookmark_sort_change(self, choice: str):
        """Handle bookmark sort selection."""
        sort_map = {
            "Newest first": "date_desc",
            "Oldest first": "date_asc",
            "A-Z": "alpha",
            "By icon": "emoji",
        }
        self.bookmark_sort_by = sort_map.get(choice, "date_desc")
        self._show_bookmarks()

    def _on_bookmark_search(self, event=None):
        """Handle bookmark search input with debounce."""
        # Cancel previous pending search
        if hasattr(self, '_bookmark_search_timer') and self._bookmark_search_timer:
            self.after_cancel(self._bookmark_search_timer)

        # Schedule search after 300ms of no typing
        self._bookmark_search_timer = self.after(300, self._do_bookmark_search)

    def _do_bookmark_search(self):
        """Actually perform the bookmark search."""
        if hasattr(self, 'bookmark_search_entry') and self.bookmark_search_entry.winfo_exists():
            self.bookmark_search_text = self.bookmark_search_entry.get().strip().lower()
            self._refresh_bookmark_list()

    def _filter_by_tag(self, tag: str):
        """Filter bookmarks by clicking a tag."""
        self.bookmark_search_text = f"#{tag}"
        self._show_bookmarks()

    def _refresh_bookmark_list(self):
        """Refresh just the bookmark list (for search)."""
        # Find and clear the scroll frame
        if hasattr(self, '_bookmark_scroll') and self._bookmark_scroll.winfo_exists():
            for w in self._bookmark_scroll.winfo_children():
                w.destroy()
            sorted_bookmarks = self._get_sorted_bookmarks()
            for bookmark in sorted_bookmarks:
                self._create_bookmark_card(self._bookmark_scroll, bookmark)

    def _get_sorted_bookmarks(self) -> list[dict]:
        """Get bookmarks sorted and filtered by current settings."""
        bookmarks = self.bookmarks.copy()

        # Apply search filter
        if self.bookmark_search_text:
            search = self.bookmark_search_text.lower()
            if search.startswith("#"):
                # Tag search
                tag_search = search[1:]
                bookmarks = [b for b in bookmarks if tag_search in [t.lower() for t in b.get("tags", [])]]
            else:
                # General search
                bookmarks = [
                    b for b in bookmarks
                    if search in b.get("title", "").lower()
                    or search in b.get("description", "").lower()
                    or any(search in t.lower() for t in b.get("tags", []))
                ]

        # Apply sort
        if self.bookmark_sort_by == "date_desc":
            bookmarks.sort(key=lambda x: x.get("created", ""), reverse=True)
        elif self.bookmark_sort_by == "date_asc":
            bookmarks.sort(key=lambda x: x.get("created", ""))
        elif self.bookmark_sort_by == "alpha":
            bookmarks.sort(key=lambda x: x.get("title", "").lower())
        elif self.bookmark_sort_by == "emoji":
            # Sort by emoji (empties last), then by title
            bookmarks.sort(key=lambda x: (x.get("emoji") == "", x.get("emoji", "zzz"), x.get("title", "").lower()))
        return bookmarks

    def _load_more_sessions(self):
        """Load the next page of sessions."""
        start = self.sessions_page * self.sessions_per_page
        end = start + self.sessions_per_page
        page_sessions = self.filtered_sessions[start:end]

        # Remove existing "Load More" button if present
        if hasattr(self, 'load_more_btn') and self.load_more_btn:
            self.load_more_btn.destroy()

        # Add session cards
        for session in page_sessions:
            self._create_session_card(self.sessions_scroll, session)

        self.sessions_page += 1

        # Add "Load More" button if there are more sessions
        remaining = len(self.filtered_sessions) - (self.sessions_page * self.sessions_per_page)
        if remaining > 0:
            self.load_more_btn = ctk.CTkButton(
                self.sessions_scroll,
                text=f"Load More ({remaining} remaining)",
                fg_color=COLORS["surface_hover"],
                hover_color=COLORS["border"],
                command=self._load_more_sessions
            )
            self.load_more_btn.pack(pady=15)
        else:
            self.load_more_btn = None

    def _create_session_card(self, parent, session: dict):
        """Create a card for a session."""
        # Check if already bookmarked
        is_bookmarked = any(b["session_id"] == session["session_id"] for b in self.bookmarks)

        # Subtle color difference: subagents are slightly dimmer
        is_subagent = session.get("is_subagent", False)
        card_color = COLORS["surface"] if is_subagent else COLORS["surface_hover"]

        card = ctk.CTkFrame(parent, fg_color=card_color, corner_radius=10)
        card.pack(fill="x", pady=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=10)

        # Top row: date and model
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x")

        date_str = session["modified"].strftime("%Y-%m-%d %H:%M")
        ctk.CTkLabel(
            top_row,
            text=date_str,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"]
        ).pack(side="left")

        if session.get("model"):
            model_name = session["model"]
            # Filter out internal/synthetic model markers
            if model_name and not model_name.startswith("<") and not model_name.endswith(">"):
                model_short = model_name.split("-")[1] if "-" in model_name else model_name
                ctk.CTkLabel(
                    top_row,
                    text=model_short,
                    font=ctk.CTkFont(size=10),
                    text_color=COLORS["accent_dim"]
                ).pack(side="left", padx=10)

        if session.get("context_collapsed"):
            collapsed_label = ctk.CTkLabel(
                top_row,
                text="☠ collapsed",
                font=ctk.CTkFont(size=10),
                text_color=COLORS["danger"]
            )
            collapsed_label.pack(side="right", padx=5)
            Tooltip(collapsed_label, "Context limit exceeded - session may have issues")
        elif session.get("hit_context_limit"):
            long_label = ctk.CTkLabel(
                top_row,
                text="⚠ long",
                font=ctk.CTkFont(size=10),
                text_color=COLORS["warning"]
            )
            long_label.pack(side="right", padx=5)
            Tooltip(long_label, "50+ messages or 5MB+ - approaching context limits")

        if session.get("is_subagent"):
            subagent_label = ctk.CTkLabel(
                top_row,
                text="⚙ subagent",
                font=ctk.CTkFont(size=10),
                text_color=COLORS["text_dim"]
            )
            subagent_label.pack(side="right", padx=5)
            Tooltip(subagent_label, "Automated session (daemon, worker, or subagent)")

        if is_bookmarked:
            ctk.CTkLabel(
                top_row,
                text="★ bookmarked",
                font=ctk.CTkFont(size=10),
                text_color=COLORS["success"]
            ).pack(side="right")

        # First message preview
        preview = session.get("first_message", "")[:100]
        if preview:
            ctk.CTkLabel(
                inner,
                text=preview + "..." if len(session.get("first_message", "")) > 100 else preview,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text"],
                wraplength=500,
                justify="left"
            ).pack(anchor="w")

        # Stats
        msg_count = session.get('message_count', 0)
        size_str = format_size(session.get('size', 0))
        stats = f"{msg_count} messages · {size_str}"
        ctk.CTkLabel(
            inner,
            text=stats,
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_dim"]
        ).pack(anchor="w")

        # Action buttons
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 0))

        # Only show Bookmark for conversations, not subagents
        if not is_bookmarked and not is_subagent:
            ctk.CTkButton(
                btn_frame, text="Bookmark",
                width=90,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                text_color="#000000",
                command=lambda s=session: self._show_add_bookmark(s)
            ).pack(side="left", padx=(0, 10))

        def show_preview_from_sessions(s):
            self._came_from_sessions = True
            self._show_preview(s)

        # For subagents, show "View" instead of "Preview" (full transcript)
        preview_text = "View" if is_subagent else "Preview"
        ctk.CTkButton(
            btn_frame, text=preview_text,
            width=70,
            fg_color=COLORS["surface"],
            hover_color=COLORS["border"],
            command=lambda s=session: show_preview_from_sessions(s)
        ).pack(side="left")

        # Hide/Unhide button
        is_hidden = session["session_id"] in self.hidden

        def toggle_hidden(s, card_ref):
            if s["session_id"] in self.hidden:
                self.hidden.remove(s["session_id"])
            else:
                self.hidden.add(s["session_id"])
            save_hidden(self.hidden)
            # Refresh the view
            self._apply_filter()

        hide_btn = ctk.CTkButton(
            btn_frame,
            text="Unhide" if is_hidden else "Hide",
            width=60,
            fg_color="transparent",
            hover_color=COLORS["surface"],
            text_color=COLORS["text_dim"],
            command=lambda s=session, c=card: toggle_hidden(s, c)
        )
        hide_btn.pack(side="right")

    def _show_add_bookmark(self, session: dict = None):
        """Show dialog to add a bookmark."""
        for w in self.content.winfo_children():
            w.destroy()

        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            header,
            text="Add Bookmark",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        ctk.CTkButton(
            header, text="Cancel",
            fg_color=COLORS["surface_hover"],
            command=self._show_bookmarks
        ).pack(side="right")

        # Form
        form = ctk.CTkFrame(self.content, fg_color="transparent")
        form.pack(fill="x", padx=40, pady=20)

        # Session ID
        ctk.CTkLabel(form, text="Session ID:", text_color=COLORS["text"]).pack(anchor="w")
        self.session_entry = ctk.CTkEntry(form, width=400)
        self.session_entry.pack(anchor="w", pady=(5, 15))
        if session:
            self.session_entry.insert(0, session["session_id"])

        # Title
        ctk.CTkLabel(form, text="Title:", text_color=COLORS["text"]).pack(anchor="w")
        self.title_entry = ctk.CTkEntry(form, width=400)
        self.title_entry.pack(anchor="w", pady=(5, 15))

        # Description
        ctk.CTkLabel(form, text="Description:", text_color=COLORS["text"]).pack(anchor="w")
        self.desc_entry = ctk.CTkTextbox(form, width=400, height=100)
        self.desc_entry.pack(anchor="w", pady=(5, 15))

        # Emoji picker
        ctk.CTkLabel(form, text="Icon (optional):", text_color=COLORS["text"]).pack(anchor="w")
        emoji_frame = ctk.CTkFrame(form, fg_color="transparent")
        emoji_frame.pack(anchor="w", pady=(5, 15))

        self.selected_emoji = ctk.StringVar(value="")
        self._emoji_buttons = []

        for emoji in BOOKMARK_EMOJIS:
            btn = ctk.CTkButton(
                emoji_frame,
                text=emoji,
                width=44,
                height=44,
                font=ctk.CTkFont(size=20),
                fg_color=COLORS["surface_hover"],
                hover_color=COLORS["border"],
                command=lambda e=emoji: self._select_emoji(e)
            )
            btn.pack(side="left", padx=2)
            self._emoji_buttons.append((btn, emoji))

        self.emoji_clear_btn = ctk.CTkButton(
            emoji_frame,
            text="✕",
            width=44,
            height=44,
            fg_color=COLORS["surface"],
            hover_color=COLORS["danger"],
            text_color=COLORS["text_dim"],
            command=lambda: self._select_emoji("")
        )
        self.emoji_clear_btn.pack(side="left", padx=(10, 0))

        self.emoji_preview = ctk.CTkLabel(
            emoji_frame,
            text="",
            font=ctk.CTkFont(size=20),
            text_color=COLORS["accent"]
        )
        self.emoji_preview.pack(side="left", padx=15)

        # Tags
        ctk.CTkLabel(form, text="Tags (comma-separated):", text_color=COLORS["text"]).pack(anchor="w")
        self.tags_entry = ctk.CTkEntry(form, width=400)
        self.tags_entry.pack(anchor="w", pady=(5, 15))

        # Save button
        ctk.CTkButton(
            form,
            text="Save Bookmark",
            fg_color=COLORS["success"],
            hover_color="#28a060",
            font=ctk.CTkFont(weight="bold"),
            command=self._save_bookmark
        ).pack(anchor="w", pady=20)

    def _select_emoji(self, emoji: str):
        """Select an emoji for the bookmark."""
        self.selected_emoji.set(emoji)
        self.emoji_preview.configure(text=f"Selected: {emoji}" if emoji else "")
        # Update button highlights
        if hasattr(self, '_emoji_buttons'):
            for btn, btn_emoji in self._emoji_buttons:
                if btn_emoji == emoji:
                    btn.configure(fg_color=COLORS["accent"])
                else:
                    btn.configure(fg_color=COLORS["surface_hover"])

    def _save_bookmark(self):
        """Save the new bookmark."""
        session_id = self.session_entry.get().strip()
        if not session_id:
            return

        bookmark = {
            "session_id": session_id,
            "title": self.title_entry.get().strip() or "Untitled",
            "description": self.desc_entry.get("1.0", "end").strip(),
            "emoji": self.selected_emoji.get(),
            "tags": [t.strip() for t in self.tags_entry.get().split(",") if t.strip()],
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        # Re-bookmarking a session updates it in place instead of duplicating
        # (delete removes every bookmark with a matching session_id)
        for i, b in enumerate(self.bookmarks):
            if b["session_id"] == session_id:
                bookmark["created"] = b.get("created", bookmark["created"])
                self.bookmarks[i] = bookmark
                break
        else:
            self.bookmarks.insert(0, bookmark)
        save_bookmarks(self.bookmarks)
        self._show_bookmarks()

    def _show_edit_bookmark(self, bookmark: dict):
        """Show dialog to edit an existing bookmark."""
        for w in self.content.winfo_children():
            w.destroy()

        self._editing_bookmark = bookmark

        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            header,
            text="Edit Bookmark",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        ctk.CTkButton(
            header, text="Cancel",
            fg_color=COLORS["surface_hover"],
            command=self._show_bookmarks
        ).pack(side="right")

        # Form
        form = ctk.CTkFrame(self.content, fg_color="transparent")
        form.pack(fill="x", padx=40, pady=20)

        # Session ID (read-only display)
        ctk.CTkLabel(form, text="Session ID:", text_color=COLORS["text"]).pack(anchor="w")
        ctk.CTkLabel(
            form,
            text=bookmark["session_id"],
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"]
        ).pack(anchor="w", pady=(5, 15))

        # Title
        ctk.CTkLabel(form, text="Title:", text_color=COLORS["text"]).pack(anchor="w")
        self.title_entry = ctk.CTkEntry(form, width=400)
        self.title_entry.insert(0, bookmark.get("title", ""))
        self.title_entry.pack(anchor="w", pady=(5, 15))

        # Description
        ctk.CTkLabel(form, text="Description:", text_color=COLORS["text"]).pack(anchor="w")
        self.desc_entry = ctk.CTkTextbox(form, width=400, height=100)
        self.desc_entry.insert("1.0", bookmark.get("description", ""))
        self.desc_entry.pack(anchor="w", pady=(5, 15))

        # Emoji picker
        ctk.CTkLabel(form, text="Icon (optional):", text_color=COLORS["text"]).pack(anchor="w")
        emoji_frame = ctk.CTkFrame(form, fg_color="transparent")
        emoji_frame.pack(anchor="w", pady=(5, 15))

        self.selected_emoji = ctk.StringVar(value=bookmark.get("emoji", ""))
        self._emoji_buttons = []

        for emoji in BOOKMARK_EMOJIS:
            btn = ctk.CTkButton(
                emoji_frame,
                text=emoji,
                width=44,
                height=44,
                font=ctk.CTkFont(size=20),
                fg_color=COLORS["accent"] if emoji == bookmark.get("emoji") else COLORS["surface_hover"],
                hover_color=COLORS["border"],
                command=lambda e=emoji: self._select_emoji(e)
            )
            btn.pack(side="left", padx=2)
            self._emoji_buttons.append((btn, emoji))

        self.emoji_clear_btn = ctk.CTkButton(
            emoji_frame,
            text="✕",
            width=44,
            height=44,
            fg_color=COLORS["surface"],
            hover_color=COLORS["danger"],
            text_color=COLORS["text_dim"],
            command=lambda: self._select_emoji("")
        )
        self.emoji_clear_btn.pack(side="left", padx=(10, 0))

        current_emoji = bookmark.get("emoji", "")
        self.emoji_preview = ctk.CTkLabel(
            emoji_frame,
            text=f"Selected: {current_emoji}" if current_emoji else "",
            font=ctk.CTkFont(size=20),
            text_color=COLORS["accent"]
        )
        self.emoji_preview.pack(side="left", padx=15)

        # Tags
        ctk.CTkLabel(form, text="Tags (comma-separated):", text_color=COLORS["text"]).pack(anchor="w")
        self.tags_entry = ctk.CTkEntry(form, width=400)
        self.tags_entry.insert(0, ", ".join(bookmark.get("tags", [])))
        self.tags_entry.pack(anchor="w", pady=(5, 15))

        # Save button
        ctk.CTkButton(
            form,
            text="Save Changes",
            fg_color=COLORS["success"],
            hover_color="#28a060",
            font=ctk.CTkFont(weight="bold"),
            command=self._update_bookmark
        ).pack(anchor="w", pady=20)

    def _update_bookmark(self):
        """Update an existing bookmark."""
        if not hasattr(self, '_editing_bookmark'):
            return

        old_bookmark = self._editing_bookmark
        session_id = old_bookmark["session_id"]

        # Find and update the bookmark
        for i, b in enumerate(self.bookmarks):
            if b["session_id"] == session_id:
                self.bookmarks[i] = {
                    "session_id": session_id,
                    "title": self.title_entry.get().strip() or "Untitled",
                    "description": self.desc_entry.get("1.0", "end").strip(),
                    "emoji": self.selected_emoji.get(),
                    "tags": [t.strip() for t in self.tags_entry.get().split(",") if t.strip()],
                    "created": old_bookmark.get("created", datetime.now().strftime("%Y-%m-%d %H:%M")),
                }
                break

        save_bookmarks(self.bookmarks)
        self._show_bookmarks()

    def _show_preview(self, item: dict):
        """Show preview of a session/bookmark."""
        for w in self.content.winfo_children():
            w.destroy()

        session_id = item.get("session_id")

        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)

        title = item.get("title", "Session Preview")
        ctk.CTkLabel(
            header,
            text=title,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        # Determine where to go back to
        back_target = self._show_all_sessions if hasattr(self, '_came_from_sessions') and self._came_from_sessions else self._show_bookmarks

        ctk.CTkButton(
            header, text="← Back",
            fg_color=COLORS["surface_hover"],
            command=back_target
        ).pack(side="right")

        # Bookmark button (only for conversations, not subagents)
        is_subagent = item.get("is_subagent", False)
        is_bookmarked = any(b["session_id"] == session_id for b in self.bookmarks)
        if not is_subagent and not is_bookmarked:
            ctk.CTkButton(
                header, text="+ Bookmark",
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                text_color="#000000",
                command=lambda: self._show_add_bookmark(item)
            ).pack(side="right", padx=(0, 10))
        elif is_bookmarked:
            ctk.CTkLabel(
                header,
                text="★ Bookmarked",
                font=ctk.CTkFont(size=11),
                text_color=COLORS["success"]
            ).pack(side="right", padx=(0, 10))

        # Session ID
        ctk.CTkLabel(
            self.content,
            text=f"Session: {session_id}",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"]
        ).pack(padx=20, anchor="w")

        # Find session file
        file_path = item.get("file_path")
        if not file_path:
            file_path = find_session_file(session_id)

        # Real project directory, needed for the resume command
        session_cwd = item.get("cwd")
        if not session_cwd and file_path:
            session_cwd = get_session_cwd(file_path)

        if file_path and Path(file_path).exists():
            # For subagents, show full transcript; for conversations, show last 10
            is_subagent = item.get("is_subagent", False)
            message_limit = 200 if is_subagent else 10  # 200 is effectively "all" for subagents

            messages = get_session_messages(file_path, limit=message_limit)

            scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=20, pady=10)

            header_text = "Full transcript:" if is_subagent else "Last 10 messages:"
            ctk.CTkLabel(
                scroll,
                text=header_text,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["text"]
            ).pack(anchor="w", pady=(0, 10))

            for msg in messages:
                role = msg["role"]
                content_preview = msg["content"][:100].lower() if msg["content"] else ""

                # Detect tool/system outputs masquerading as user messages
                is_system_output = False
                if role == "user":
                    system_patterns = [
                        "has been updated successfully",
                        "has been created successfully",
                        "success: the process",
                        "error: ",
                        "warning: ",
                        "the file c:\\",
                        "the file /",
                        "traceback (most recent",
                        "no matches found",
                        "command not found",
                    ]
                    if any(pattern in content_preview for pattern in system_patterns):
                        is_system_output = True

                if is_system_output:
                    color = COLORS["text_dim"]
                    prefix = "System: "
                elif role == "user":
                    color = self.settings.get("accent_color", COLORS["accent"])
                    prefix = "You: "
                else:
                    color = self.settings.get("claude_color", "#c084fc")
                    prefix = "Claude: "

                # Handle content being a list or string
                content = msg["content"]
                if isinstance(content, list):
                    content = " ".join(str(c) for c in content if c)
                content = str(content)[:500]  # Truncate

                msg_frame = ctk.CTkFrame(scroll, fg_color=COLORS["surface_hover"], corner_radius=8)
                msg_frame.pack(fill="x", pady=3)

                ctk.CTkLabel(
                    msg_frame,
                    text=prefix + content,
                    font=ctk.CTkFont(size=11),
                    text_color=color,
                    wraplength=550,
                    justify="left"
                ).pack(padx=10, pady=8, anchor="w")

            # For subagents, add copy transcript button at the bottom of scroll area
            if is_subagent:
                def copy_transcript():
                    transcript_lines = []
                    for msg in messages:
                        role = "You" if msg["role"] == "user" else "Claude"
                        content = msg["content"]
                        if isinstance(content, list):
                            content = " ".join(str(c) for c in content if c)
                        transcript_lines.append(f"{role}: {content}")
                    full_transcript = "\n\n".join(transcript_lines)
                    self.clipboard_clear()
                    self.clipboard_append(full_transcript)
                    copy_transcript_btn.configure(text="Copied!")
                    self.after(1500, lambda: copy_transcript_btn.configure(text="Copy Transcript"))

                copy_transcript_btn = ctk.CTkButton(
                    scroll,
                    text="Copy Transcript",
                    fg_color=COLORS["accent"],
                    hover_color=COLORS["accent_hover"],
                    text_color="#000000",
                    command=copy_transcript
                )
                copy_transcript_btn.pack(pady=15)

        else:
            ctk.CTkLabel(
                self.content,
                text="Session file not found.",
                text_color=COLORS["text_dim"]
            ).pack(pady=20)

        # Command builder with flag toggles (only for conversations, not subagents)
        if not is_subagent:
            cmd_frame = ctk.CTkFrame(self.content, fg_color=COLORS["surface_hover"], corner_radius=10)
            cmd_frame.pack(fill="x", padx=20, pady=20)

            ctk.CTkLabel(
                cmd_frame,
                text="Resume Command:",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["text"]
            ).pack(padx=15, pady=(15, 5), anchor="w")

            # Command display (will be updated by toggles)
            cmd_label = ctk.CTkLabel(
                cmd_frame,
                text="",
                font=ctk.CTkFont(size=11, family="Consolas"),
                text_color=COLORS["accent"],
                wraplength=550
            )
            cmd_label.pack(padx=15, pady=5, anchor="w")

            # Flag toggles
            toggles_frame = ctk.CTkFrame(cmd_frame, fg_color="transparent")
            toggles_frame.pack(padx=15, pady=(5, 10), anchor="w", fill="x")

            ctk.CTkLabel(
                toggles_frame,
                text="Options:",
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_dim"]
            ).pack(anchor="w", pady=(0, 5))

            # Toggle variables
            skip_perms_var = ctk.BooleanVar(value=self.flags.get("dangerously_skip_permissions", False))
            bypass_var = ctk.BooleanVar(value=bool(self.flags.get("permission_mode")))

            # Model options - aliases resolve to the latest version, so this
            # list doesn't go stale with every model release
            model_options = {
                "None (use default)": None,
                "Opus (latest)": "opus",
                "Sonnet (latest)": "sonnet",
                "Haiku (latest)": "haiku",
            }
            current_model = self.flags.get("model")
            current_model_display = next((k for k, v in model_options.items() if v == current_model), "None (use default)")

            def update_command(*args):
                # Update flags based on toggles
                self.flags["dangerously_skip_permissions"] = skip_perms_var.get()
                self.flags["permission_mode"] = "bypassPermissions" if bypass_var.get() else None
                self.flags["model"] = model_options.get(model_menu.get())
                # Update command display
                cmd = build_resume_command(session_id, self.flags, session_cwd)
                cmd_label.configure(text=cmd)

            ctk.CTkCheckBox(
                toggles_frame,
                text="--dangerously-skip-permissions",
                variable=skip_perms_var,
                command=update_command,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_dim"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"]
            ).pack(anchor="w", pady=2)
            Tooltip(toggles_frame.winfo_children()[-1], "Skip all permission prompts (use with caution)")

            ctk.CTkCheckBox(
                toggles_frame,
                text="--permission-mode bypassPermissions",
                variable=bypass_var,
                command=update_command,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_dim"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"]
            ).pack(anchor="w", pady=2)
            Tooltip(toggles_frame.winfo_children()[-1], "Set permission mode to bypass all prompts")

            # Model selector row
            model_row = ctk.CTkFrame(toggles_frame, fg_color="transparent")
            model_row.pack(anchor="w", pady=5)

            ctk.CTkLabel(
                model_row,
                text="--model",
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_dim"]
            ).pack(side="left")

            model_menu = ctk.CTkOptionMenu(
                model_row,
                values=list(model_options.keys()),
                width=140,
                fg_color=COLORS["surface"],
                button_color=COLORS["surface"],
                button_hover_color=COLORS["border"],
                command=update_command
            )
            model_menu.set(current_model_display)
            model_menu.pack(side="left", padx=10)

            # Initialize command display
            update_command()

            def copy_cmd():
                cmd = build_resume_command(session_id, self.flags, session_cwd)
                self.clipboard_clear()
                self.clipboard_append(cmd)
                copy_btn.configure(text="Copied!")
                self.after(1500, lambda: copy_btn.configure(text="Copy to Clipboard"))

            copy_btn = ctk.CTkButton(
                cmd_frame,
                text="Copy to Clipboard",
                fg_color=COLORS["accent"],
                text_color="#000000",
                command=copy_cmd
            )
            copy_btn.pack(padx=15, pady=(5, 15), anchor="w")

    def _show_settings(self):
        """Show settings page."""
        for w in self.content.winfo_children():
            w.destroy()

        # Header
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            header,
            text="Settings",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        ctk.CTkButton(
            header, text="← Back",
            fg_color=COLORS["surface_hover"],
            command=self._show_bookmarks
        ).pack(side="right")

        # Settings form
        form = ctk.CTkFrame(self.content, fg_color="transparent")
        form.pack(fill="x", padx=40, pady=20)

        # Accent color (You/UI elements)
        ctk.CTkLabel(
            form,
            text="Accent Color (Your messages, buttons):",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"]
        ).pack(anchor="w", pady=(0, 5))

        accent_frame = ctk.CTkFrame(form, fg_color="transparent")
        accent_frame.pack(anchor="w", pady=(0, 15))

        self._accent_var = ctk.StringVar(value=self.settings.get("accent_color", "#00d4ff"))

        # Preset buttons
        for name, color in COLOR_PRESETS.items():
            btn = ctk.CTkButton(
                accent_frame,
                text="",
                width=36,
                height=36,
                fg_color=color,
                hover_color=color,
                corner_radius=18,
                command=lambda c=color: self._set_accent_color(c)
            )
            btn.pack(side="left", padx=3)
            Tooltip(btn, name)

        # Hex input
        ctk.CTkLabel(accent_frame, text="or", text_color=COLORS["text_dim"]).pack(side="left", padx=10)
        self._accent_entry = ctk.CTkEntry(accent_frame, width=80, placeholder_text="#hex")
        self._accent_entry.insert(0, self._accent_var.get())
        self._accent_entry.pack(side="left")
        self._accent_entry.bind("<Return>", lambda e: self._set_accent_color(self._accent_entry.get()))

        # Preview
        self._accent_preview = ctk.CTkLabel(
            accent_frame,
            text="  Preview  ",
            font=ctk.CTkFont(size=11),
            fg_color=self._accent_var.get(),
            text_color="#000000",
            corner_radius=6
        )
        self._accent_preview.pack(side="left", padx=15)

        # Claude color
        ctk.CTkLabel(
            form,
            text="Claude Color (Claude's messages):",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"]
        ).pack(anchor="w", pady=(20, 5))

        claude_frame = ctk.CTkFrame(form, fg_color="transparent")
        claude_frame.pack(anchor="w", pady=(0, 15))

        self._claude_var = ctk.StringVar(value=self.settings.get("claude_color", "#e879f9"))

        # Preset buttons
        for name, color in COLOR_PRESETS.items():
            btn = ctk.CTkButton(
                claude_frame,
                text="",
                width=36,
                height=36,
                fg_color=color,
                hover_color=color,
                corner_radius=18,
                command=lambda c=color: self._set_claude_color(c)
            )
            btn.pack(side="left", padx=3)
            Tooltip(btn, name)

        # Hex input
        ctk.CTkLabel(claude_frame, text="or", text_color=COLORS["text_dim"]).pack(side="left", padx=10)
        self._claude_entry = ctk.CTkEntry(claude_frame, width=80, placeholder_text="#hex")
        self._claude_entry.insert(0, self._claude_var.get())
        self._claude_entry.pack(side="left")
        self._claude_entry.bind("<Return>", lambda e: self._set_claude_color(self._claude_entry.get()))

        # Preview
        self._claude_preview = ctk.CTkLabel(
            claude_frame,
            text="  Preview  ",
            font=ctk.CTkFont(size=11),
            fg_color=self._claude_var.get(),
            text_color="#000000",
            corner_radius=6
        )
        self._claude_preview.pack(side="left", padx=15)

        # Save button
        ctk.CTkButton(
            form,
            text="Save Settings",
            fg_color=COLORS["success"],
            hover_color="#28a060",
            font=ctk.CTkFont(weight="bold"),
            command=self._save_settings
        ).pack(anchor="w", pady=30)

        # Note
        ctk.CTkLabel(
            form,
            text="Note: Color changes apply to new views. Restart app for full effect.",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_dim"]
        ).pack(anchor="w")

    def _set_accent_color(self, color: str):
        """Update accent color preview."""
        if color.startswith("#") and len(color) in (4, 7):
            self._accent_var.set(color)
            self._accent_entry.delete(0, "end")
            self._accent_entry.insert(0, color)
            self._accent_preview.configure(fg_color=color)

    def _set_claude_color(self, color: str):
        """Update Claude color preview."""
        if color.startswith("#") and len(color) in (4, 7):
            self._claude_var.set(color)
            self._claude_entry.delete(0, "end")
            self._claude_entry.insert(0, color)
            self._claude_preview.configure(fg_color=color)

    def _save_settings(self):
        """Save settings to file."""
        self.settings["accent_color"] = self._accent_var.get()
        self.settings["claude_color"] = self._claude_var.get()
        save_settings(self.settings)
        # Apply theme colors
        self._apply_theme()
        # Update title color
        self._title_label.configure(text_color=COLORS["accent"])
        self._show_bookmarks()

    def _delete_bookmark(self, bookmark: dict):
        """Delete a bookmark."""
        self.bookmarks = [b for b in self.bookmarks if b["session_id"] != bookmark["session_id"]]
        save_bookmarks(self.bookmarks)
        self._show_bookmarks()

    def _quick_add(self, session_id: str):
        """Quick add current session."""
        session = {"session_id": session_id}
        self._show_add_bookmark(session)


def main():
    ctk.set_appearance_mode("dark")

    # Check for quick-add argument
    quick_add = None
    if len(sys.argv) > 1 and sys.argv[1] == "--add":
        if len(sys.argv) > 2:
            quick_add = sys.argv[2]

    app = BookmarksApp(quick_add_session=quick_add)
    app.mainloop()


if __name__ == "__main__":
    main()
