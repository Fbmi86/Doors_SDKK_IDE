import re
import tkinter as tk
from tkinter import ttk # Use ttk for scrollbar

class DependencyViewer(tk.Frame): # Inherit from tk.Frame
    """
    A simple widget to display dependencies found in the source code.
    Currently lists #include directives and DRO_MODULE macros.
    """
    def __init__(self, master=None):
        """Initializes the DependencyViewer frame and its widgets."""
        super().__init__(master) # Call parent constructor

        tk.Label(self, text="Dependencies").pack(pady=(0, 2))

        # Use a Frame to hold the Listbox and Scrollbar
        list_frame = tk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.scrollbar = ttk.Scrollbar(list_frame) # Use ttk Scrollbar
        self.listbox = tk.Listbox(list_frame, width=60, height=10, yscrollcommand=self.scrollbar.set)
        self.scrollbar.config(command=self.listbox.yview)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def update_dependencies(self, source_code: str):
        """
        Parses source code to find include directives and DRO_MODULEs,
        and updates the listbox. Handles basic comments.

        Args:
            source_code: The string content of the source file.
        """
        self.listbox.delete(0, tk.END)

        if not source_code:
             self.listbox.insert(tk.END, "No source code to parse.")
             return

        # Process line by line to handle comments more easily
        lines = source_code.splitlines()
        in_multiline_comment = False
        found_dependencies = False

        for line in lines:
            line = line.strip()

            # Basic multi-line comment handling
            # This is not perfect but handles common cases
            if '/*' in line and '*/' not in line:
                in_multiline_comment = True
                continue
            if '*/' in line and in_multiline_comment:
                in_multiline_comment = False
                continue
            if in_multiline_comment:
                continue

            # Ignore single-line comments //
            line_without_comment = line.split('//', 1)[0].strip()

            if not line_without_comment:
                continue # Skip empty or comment-only lines

            # Find #include "..." or #include <...>
            include_match = re.search(r'#include\s+["<]([^">]+)[">]', line_without_comment)
            if include_match:
                self.listbox.insert(tk.END, f"Header: {include_match.group(1)}")
                found_dependencies = True
                continue

            # Find DRO_MODULE "..."
            # This assumes a specific macro format. Adjust if needed.
            dro_module_match = re.search(r'DRO_MODULE\s*\(\s*"([^"]+)"\s*\)', line_without_comment)
            if dro_module_match:
                self.listbox.insert(tk.END, f"Module: {dro_module_match.group(1)}")
                found_dependencies = True
                continue

        # Add a message if no dependencies found
        if not found_dependencies:
             self.listbox.insert(tk.END, "No dependencies found.")

