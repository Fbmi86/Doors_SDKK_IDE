# syntax_highlighter.py
import re
import tkinter as tk

class CSyntaxHighlighter:
    """
    Provides basic C syntax highlighting for a Tkinter Text widget.
    Highlights keywords, strings, comments, and preprocessor directives.
    """
    def __init__(self, text_widget: tk.Text):
        """Initializes the highlighter for the given Text widget."""
        self.text = text_widget
        self.configure_tags()

        # Bind the highlight method to text modification events
        # The GUI class will trigger highlight via _on_editor_change
        # We keep a KeyRelease binding for responsiveness during typing,
        # but rely on the external trigger for full updates (like paste, load).
        # self.text.bind("<KeyRelease>", self.highlight) # Removed direct binding, relying on GUI class

        # Store the last text content to avoid unnecessary re-highlighting
        self._last_text = ""

    def configure_tags(self):
        """Configures the text tags for different syntax elements."""
        self.text.tag_configure("keyword", foreground="#FF6A00") # Orange
        self.text.tag_configure("string", foreground="#A5C25C")  # Green
        self.text.tag_configure("comment", foreground="#808080") # Gray
        self.text.tag_configure("preprocessor", foreground="#999999") # Light gray for #include etc.
        # Add more tags if needed, e.g., for numbers, function names, etc.
        # self.text.tag_configure("number", foreground="#00B0F0") # Blue
        # self.text.tag_configure("type", foreground="#00B0F0") # Blue for int, char, struct etc.


    def highlight(self, event=None):
        """
        Applies syntax highlighting to the entire text content.
        Optimized to only re-highlight if the text has changed.
        """
        # Get content including the potential extra newline from END index
        text_content = self.text.get("1.0", tk.END)
        # Remove the extra newline that text.get(..., END) adds for comparison
        if text_content.endswith('\n'):
            text_content_compare = text_content[:-1]
        else:
            text_content_compare = text_content

        # Avoid re-highlighting if text hasn't changed (optimization)
        if text_content_compare == self._last_text:
            return
        self._last_text = text_content_compare # Update last text *before* highlighting

        # Remove all existing tags first
        for tag in ["keyword", "string", "comment", "preprocessor"]: # Add other tags here
            self.text.tag_remove(tag, "1.0", tk.END)

        # Use re.finditer for more efficient searching of multiple matches
        # Pattern for keywords (more comprehensive list)
        keywords = r'\b(auto|break|case|char|const|continue|default|do|double|else|enum|extern|float|for|goto|if|inline|int|long|register|restrict|return|short|signed|sizeof|static|struct|switch|typedef|union|unsigned|void|volatile|while|_Alignas|_Alignof|_Atomic|_Bool|_Complex|_Generic|_Imaginary|_Noreturn|_Static_assert|_Thread_local)\b'
        # Pattern for strings (handles escaped quotes)
        strings = r'"(?:[^"\\]|\\.)*"'
        # Pattern for comments (single-line // and multi-line /* */)
        # Use non-greedy match for multi-line comments (.*?)
        # re.DOTALL allows . to match newlines
        comments = r'//.*|/\*.*?\*/'
        # Pattern for preprocessor directives (#include, #define, etc.)
        # re.MULTILINE allows ^ to match start of line
        preprocessor = r'^\s*#\s*\w+.*' # Matches lines starting with # followed by word

        # Combine patterns using |
        # Order matters: comments, strings, and preprocessor should be checked before keywords
        # to avoid highlighting keywords inside them.
        pattern = re.compile(f'({comments}|{strings}|{preprocessor}|{keywords})', re.DOTALL | re.MULTILINE)

        for match in pattern.finditer(text_content):
            start_index = match.start()
            end_index = match.end()
            tag = None

            # Determine which pattern matched
            match_text = match.group(0)

            # Check for comments first (both types)
            if match_text.startswith('//') or match_text.startswith('/*'):
                tag = "comment"
            # Check for strings
            elif match_text.startswith('"'):
                tag = "string"
            # Check for preprocessor directives (must be at start of line after optional whitespace)
            # Use match.group(0).strip() to check the start of the matched text after stripping whitespace
            elif match_text.strip().startswith('#'):
                 tag = "preprocessor"
            # Check for keywords (must be a full word match)
            # Use re.fullmatch to ensure the *entire* matched text is a keyword
            elif re.fullmatch(keywords, match_text):
                 tag = "keyword"

            if tag:
                # Convert character index to Text widget index (line.column)
                # Text widget indices are 1-based for line, 0-based for column
                start_tk_index = self.text.index(f"1.0 + {start_index}c")
                end_tk_index = self.text.index(f"1.0 + {end_index}c")
                self.text.tag_add(tag, start_tk_index, end_tk_index)
# syntax_highlighter.py (No changes needed from previous version)
# import re
# import tkinter as tk

# class CSyntaxHighlighter:
#     """
#     Provides basic C syntax highlighting for a Tkinter Text widget.
#     Highlights keywords, strings, comments, and preprocessor directives.
#     """
#     def __init__(self, text_widget: tk.Text):
#         """Initializes the highlighter for the given Text widget."""
#         self.text = text_widget
#         self.configure_tags()

#         # Bind the highlight method to text modification events
#         # The GUI class will trigger highlight via _on_editor_change
#         # We keep a KeyRelease binding for responsiveness during typing,
#         # but rely on the external trigger for full updates (like paste, load).
#         # self.text.bind("<KeyRelease>", self.highlight) # Removed direct binding, relying on GUI class

#         # Store the last text content to avoid unnecessary re-highlighting
#         self._last_text = ""

#     def configure_tags(self):
#         """Configures the text tags for different syntax elements."""
#         self.text.tag_configure("keyword", foreground="#FF6A00") # Orange
#         self.text.tag_configure("string", foreground="#A5C25C")  # Green
#         self.text.tag_configure("comment", foreground="#808080") # Gray
#         self.text.tag_configure("preprocessor", foreground="#999999") # Light gray for #include etc.
#         # Add more tags if needed, e.g., for numbers, function names, etc.
#         # self.text.tag_configure("number", foreground="#00B0F0") # Blue
#         # self.text.tag_configure("type", foreground="#00B0F0") # Blue for int, char, struct etc.


#     def highlight(self, event=None):
#         """
#         Applies syntax highlighting to the entire text content.
#         Optimized to only re-highlight if the text has changed.
#         """
#         # Get content including the potential extra newline from END index
#         text_content = self.text.get("1.0", tk.END)
#         # Remove the extra newline that text.get(..., END) adds for comparison
#         if text_content.endswith('\n'):
#             text_content_compare = text_content[:-1]
#         else:
#             text_content_compare = text_content

#         # Avoid re-highlighting if text hasn't changed (optimization)
#         if text_content_compare == self._last_text:
#             return
#         self._last_text = text_content_compare # Update last text *before* highlighting

#         # Remove all existing tags first
#         for tag in ["keyword", "string", "comment", "preprocessor"]: # Add other tags here
#             self.text.tag_remove(tag, "1.0", tk.END)

#         # Use re.finditer for more efficient searching of multiple matches
#         # Pattern for keywords (more comprehensive list)
#         keywords = r'\b(auto|break|case|char|const|continue|default|do|double|else|enum|extern|float|for|goto|if|inline|int|long|register|restrict|return|short|signed|sizeof|static|struct|switch|typedef|union|unsigned|void|volatile|while|_Alignas|_Alignof|_Atomic|_Bool|_Complex|_Generic|_Imaginary|_Noreturn|_Static_assert|_Thread_local)\b'
#         # Pattern for strings (handles escaped quotes)
#         strings = r'"(?:[^"\\]|\\.)*"'
#         # Pattern for comments (single-line // and multi-line /* */)
#         # Use non-greedy match for multi-line comments (.*?)
#         # re.DOTALL allows . to match newlines
#         comments = r'//.*|/\*.*?\*/'
#         # Pattern for preprocessor directives (#include, #define, etc.)
#         # re.MULTILINE allows ^ to match start of line
#         preprocessor = r'^\s*#\s*\w+.*' # Matches lines starting with # followed by word

#         # Combine patterns using |
#         # Order matters: comments, strings, and preprocessor should be checked before keywords
#         # to avoid highlighting keywords inside them.
#         pattern = re.compile(f'({comments}|{strings}|{preprocessor}|{keywords})', re.DOTALL | re.MULTILINE)

#         for match in pattern.finditer(text_content):
#             start_index = match.start()
#             end_index = match.end()
#             tag = None

#             # Determine which pattern matched
#             match_text = match.group(0)

#             # Check for comments first (both types)
#             if match_text.startswith('//') or match_text.startswith('/*'):
#                 tag = "comment"
#             # Check for strings
#             elif match_text.startswith('"'):
#                 tag = "string"
#             # Check for preprocessor directives (must be at start of line after optional whitespace)
#             # Use match.group(0).strip() to check the start of the matched text after stripping whitespace
#             elif match_text.strip().startswith('#'):
#                  tag = "preprocessor"
#             # Check for keywords (must be a full word match)
#             # Use re.fullmatch to ensure the *entire* matched text is a keyword
#             elif re.fullmatch(keywords, match_text):
#                  tag = "keyword"

#             if tag:
#                 # Convert character index to Text widget index (line.column)
#                 # Text widget indices are 1-based for line, 0-based for column
#                 start_tk_index = self.text.index(f"1.0 + {start_index}c")
#                 end_tk_index = self.text.index(f"1.0 + {end_index}c")
#                 self.text.tag_add(tag, start_tk_index, end_tk_index)
