import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk, simpledialog
import os
import threading
import queue
import sys
import json
import platform # Added to potentially handle platform specifics
from common import build_project
# Import the improved modules
# Ensure build_project is imported from builder
from builder import build_project
from syntax_highlighter import CSyntaxHighlighter
from deploy_to_qemu import deploy_to_qemu
from dependency_viewer import DependencyViewer

# --- Configuration (Defaults - can be changed in GUI and saved in project) ---
DEFAULT_OUTPUT_EXTENSION = ".sdkk"
DEFAULT_SOURCE_EXTENSION = ".c"
DEFAULT_PROJECT_EXTENSION = ".sdkkproj"

# Suggest platform-specific default paths or relative paths
if platform.system() == "Windows":
    DEFAULT_MINGW_PATH = "C:/msys64/mingw64/bin" # Common MinGW-w64 path
    DEFAULT_KERNEL_ELF_PATH = "kernel.elf" # Assume relative to project or script
    DEFAULT_BUILD_DIR = "build" # Assume relative to project or script
elif platform.system() == "Linux":
    DEFAULT_MINGW_PATH = "/usr/bin" # Or /usr/local/bin, depends on distro/install
    DEFAULT_KERNEL_ELF_PATH = "kernel.elf"
    DEFAULT_BUILD_DIR = "build"
elif platform.system() == "Darwin": # macOS
    DEFAULT_MINGW_PATH = "/usr/local/bin" # Or wherever brew installs
    DEFAULT_KERNEL_ELF_PATH = "kernel.elf"
    DEFAULT_BUILD_DIR = "build"
else: # Generic fallback
    DEFAULT_MINGW_PATH = "/usr/bin"
    DEFAULT_KERNEL_ELF_PATH = "kernel.elf"
    DEFAULT_BUILD_DIR = "build"


DEFAULT_APP_SUBDIR = "SysDro/Applications" # Default subdirectory within build dir for apps

class SDKKBuilderGUI:
    """
    Main GUI class for the Doors SDKK Builder IDE.
    Manages the UI, file operations, build settings, and triggers build/deploy processes.
    Includes basic project management.
    """
    def __init__(self, root):
        """Initializes the main application window and UI components."""
        self.root = root
        self.root.title("Doors SDKK Builder")
        self.root.geometry("1000x700") # Increased window size

        self.current_file_path = None
        self.current_project_path = None
        self.content_modified = False
        self._after_id_editor_change = None # Initialize the after ID to None

        # Queue for thread-safe GUI updates
        self.message_queue = queue.Queue()
        self._process_queue() # Start processing queue messages

        # --- UI Layout ---
        main_frame = tk.Frame(root)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Control and Settings frames at the top
        control_frame = tk.Frame(main_frame)
        settings_frame = tk.LabelFrame(main_frame, text="Build & Deploy Settings")

        control_frame.pack(side="top", fill="x", pady=5)
        settings_frame.pack(side="top", fill="x", pady=5, padx=2)

        # Paned window for Editor/Dependencies and Package Details/Log
        self.paned_window_vertical = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        self.paned_window_vertical.pack(side="top", fill="both", expand=True)

        # Top pane: Editor and Dependencies (Horizontal Paned Window)
        top_pane = ttk.PanedWindow(self.paned_window_vertical, orient=tk.HORIZONTAL)
        self.paned_window_vertical.add(top_pane, weight=3) # Top pane gets more vertical space

        editor_frame = tk.Frame(top_pane)
        dependency_frame = tk.LabelFrame(top_pane, text="Dependencies") # Use LabelFrame for title
        top_pane.add(editor_frame, weight=3) # Editor gets more horizontal space
        top_pane.add(dependency_frame, weight=1)

        # Bottom pane: Package Details and Log (Horizontal Paned Window)
        bottom_pane = ttk.PanedWindow(self.paned_window_vertical, orient=tk.HORIZONTAL)
        self.paned_window_vertical.add(bottom_pane, weight=1) # Bottom pane gets less vertical space

        package_frame = tk.LabelFrame(bottom_pane, text="SDKK Package Details")
        log_frame = tk.LabelFrame(bottom_pane, text="Build/Deploy Log")
        bottom_pane.add(package_frame, weight=2) # Package details gets more horizontal space
        bottom_pane.add(log_frame, weight=1)


        # --- Populate the frames with widgets ---
        self._create_control_widgets(control_frame)
        self._create_settings_widgets(settings_frame)
        self._create_package_details_widgets(package_frame)
        self._create_log_widgets(log_frame) # New log area

        # Editor and Dependency Viewer are children of their respective panes
        self.editor = scrolledtext.ScrolledText(editor_frame, wrap="none", undo=True)
        self.editor.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.highlighter = CSyntaxHighlighter(self.editor)

        # DependencyViewer is now a child of dependency_frame
        self.dependency_viewer = DependencyViewer(dependency_frame)
        self.dependency_viewer.pack(fill=tk.BOTH, expand=True)


        # --- Status Bar ---
        self.status_bar = tk.Label(root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side="bottom", fill="x")

        # --- Menu Bar ---
        self._create_menubar()

        # --- Event Bindings ---
        # Bind <<Modified>> to the handler that sets the flag and schedules the update
        self.editor.bind("<<Modified>>", self._on_editor_modified)

        # Initial state
        self.update_status("Ready")
        self.update_title()
        # Perform initial highlighting and dependency check for the empty editor
        # This also resets the modified flag and clears the after ID
        self._on_editor_change()

        # Bind window closing event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)


    def _create_package_details_widgets(self, parent_frame):
        """Creates widgets for the SDKK Package Details section."""
        metadata_frame = tk.Frame(parent_frame)
        metadata_frame.pack(side="top", fill="x", padx=5, pady=5)

        tk.Label(metadata_frame, text="Package Name:").pack(side="left", padx=(0, 5))
        self.package_name_var = tk.StringVar(value="MyApplication")
        self.package_name_entry = tk.Entry(metadata_frame, width=30, textvariable=self.package_name_var)
        self.package_name_entry.pack(side="left", padx=(0, 15))

        tk.Label(metadata_frame, text="Version:").pack(side="left", padx=(0, 5))
        self.package_version_var = tk.StringVar(value="1.0")
        self.package_version_entry = tk.Entry(metadata_frame, width=10, textvariable=self.package_version_var)
        self.package_version_entry.pack(side="left", padx=(0, 15))

        tk.Label(metadata_frame, text="Description:").pack(side="left", padx=(0, 5))
        self.package_description_var = tk.StringVar(value="A sample Doors application")
        self.package_description_entry = tk.Entry(metadata_frame, width=50, textvariable=self.package_description_var)
        self.package_description_entry.pack(side="left", fill="x", expand=True)

        files_frame = tk.LabelFrame(parent_frame, text="Files to Include in Package (excluding main source)")
        files_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)

        # Treeview for additional files
        self.files_tree = ttk.Treeview(files_frame, columns=("Host Path", "Internal Path", "Size"), show="headings")
        self.files_tree.heading("Host Path", text="Host Path")
        self.files_tree.heading("Internal Path", text="Internal Path")
        self.files_tree.heading("Size", text="Size")
        self.files_tree.column("Host Path", width=250, anchor=tk.W)
        self.files_tree.column("Internal Path", width=150, anchor=tk.W)
        self.files_tree.column("Size", width=80, anchor=tk.E)
        self.files_tree.pack(side="left", fill="both", expand=True)

        files_scrollbar = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        self.files_tree.configure(yscrollcommand=files_scrollbar.set)
        files_scrollbar.pack(side="right", fill=tk.Y)

        file_buttons_frame = tk.Frame(files_frame)
        file_buttons_frame.pack(side="bottom", fill="x", pady=2)
        tk.Button(file_buttons_frame, text="Add File...", command=self.add_file_to_package).pack(side="left", padx=(0, 5))
        tk.Button(file_buttons_frame, text="Remove Selected", command=self.remove_selected_file).pack(side="left")


    def _create_control_widgets(self, parent_frame):
        """Creates widgets for the Control section (Entry Point, Arch, Build/Deploy)."""
        tk.Label(parent_frame, text="Entry Point:").pack(side="left", padx=(0, 5))
        self.entry_point_var = tk.StringVar(value="_start")
        self.entry_point_entry = tk.Entry(parent_frame, width=20, textvariable=self.entry_point_var)
        self.entry_point_entry.pack(side="left", padx=(0, 15))

        tk.Label(parent_frame, text="Architecture:").pack(side="left", padx=(0, 5))
        self.arch_var = tk.StringVar(value="x86_64")
        tk.Radiobutton(parent_frame, text="x86_64", variable=self.arch_var, value="x86_64").pack(side="left")
        tk.Radiobutton(parent_frame, text="i686", variable=self.arch_var, value="i686").pack(side="left", padx=(0, 15))

        tk.Button(parent_frame, text="Build SDKK", command=self.build).pack(side="left", padx=(20, 5)) # Added padding
        tk.Button(parent_frame, text="Deploy to QEMU", command=self.deploy).pack(side="left")


    def _create_settings_widgets(self, parent_frame):
        """Creates widgets for the Build & Deploy Settings section."""
        # Use a frame to contain all settings rows
        settings_inner_frame = tk.Frame(parent_frame)
        settings_inner_frame.pack(fill="x", padx=5, pady=2)

        # MinGW Path
        mingw_frame = tk.Frame(settings_inner_frame)
        mingw_frame.pack(fill="x", pady=2)
        tk.Label(mingw_frame, text="MinGW Bin Path:").pack(side="left", padx=(0, 5))
        self.mingw_path_var = tk.StringVar(value=DEFAULT_MINGW_PATH)
        self.mingw_path_entry = tk.Entry(mingw_frame, textvariable=self.mingw_path_var, width=60) # Increased width
        self.mingw_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(mingw_frame, text="Browse...", command=self.browse_mingw_path).pack(side="left")

        # Kernel ELF Path
        kernel_frame = tk.Frame(settings_inner_frame)
        kernel_frame.pack(fill="x", pady=2)
        tk.Label(kernel_frame, text="Kernel ELF Path:").pack(side="left", padx=(0, 5))
        self.kernel_elf_path_var = tk.StringVar(value=DEFAULT_KERNEL_ELF_PATH)
        self.kernel_elf_path_entry = tk.Entry(kernel_frame, textvariable=self.kernel_elf_path_var, width=60) # Increased width
        self.kernel_elf_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(kernel_frame, text="Browse...", command=self.browse_kernel_elf_path).pack(side="left")

        # Build Directory
        build_dir_frame = tk.Frame(settings_inner_frame)
        build_dir_frame.pack(fill="x", pady=2)
        tk.Label(build_dir_frame, text="Build Directory:").pack(side="left", padx=(0, 5))
        self.build_dir_var = tk.StringVar(value=DEFAULT_BUILD_DIR)
        self.build_dir_entry = tk.Entry(build_dir_frame, textvariable=self.build_dir_var, width=60) # Increased width
        self.build_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(build_dir_frame, text="Browse...", command=self.browse_build_dir).pack(side="left")

        # App Subdirectory
        app_subdir_frame = tk.Frame(settings_inner_frame)
        app_subdir_frame.pack(fill="x", pady=2)
        tk.Label(app_subdir_frame, text="App Subdirectory (in Build Dir):").pack(side="left", padx=(0, 5))
        self.app_subdir_var = tk.StringVar(value=DEFAULT_APP_SUBDIR)
        self.app_subdir_entry = tk.Entry(app_subdir_frame, textvariable=self.app_subdir_var, width=60) # Increased width
        self.app_subdir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))


    def _create_log_widgets(self, parent_frame):
        """Creates the scrolled text area for build/deploy logs."""
        self.log_text = scrolledtext.ScrolledText(parent_frame, wrap="word", state="disabled", height=10)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        # Configure tags for different message types (optional)
        self.log_text.tag_configure("info", foreground="black")
        self.log_text.tag_configure("warning", foreground="orange")
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("debug", foreground="gray")


    def _create_menubar(self):
        """Creates the application menu bar."""
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="New Project", command=self.new_project)
        filemenu.add_command(label="Open Project...", command=self.open_project)
        filemenu.add_command(label="Save Project", command=self.save_project)
        filemenu.add_command(label="Save Project As...", command=self.save_project_as)
        filemenu.add_separator()
        filemenu.add_command(label="New Source File", command=self.new_file) # Added New File
        filemenu.add_command(label="Open Source File...", command=self.open_file)
        filemenu.add_command(label="Save Source File", command=self.save_file)
        filemenu.add_command(label="Save Source File As...", command=self.save_file_as)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.on_closing)
        menubar.add_cascade(label="File", menu=filemenu)

        buildmenu = tk.Menu(menubar, tearoff=0)
        buildmenu.add_command(label="Build SDKK", command=self.build)
        buildmenu.add_command(label="Deploy to QEMU", command=self.deploy)
        menubar.add_cascade(label="Build", menu=buildmenu)

        self.root.config(menu=menubar)


    def _on_editor_modified(self, event=None):
        """
        Handler for editor <<Modified>> event.
        Sets the modified flag and schedules a delayed update for highlighting/dependencies.
        """
        # The modified flag is set by the Text widget itself when content changes.
        # We just need to react to it.
        self.content_modified = True
        self.update_title()
        # Cancel any previously scheduled _on_editor_change call
        if self._after_id_editor_change is not None:
             self.root.after_cancel(self._after_id_editor_change)
        # Schedule a new call to _on_editor_change after a short delay (e.g., 500ms)
        # This groups rapid typing events into a single update.
        self._after_id_editor_change = self.root.after(500, self._on_editor_change)


    def _on_editor_change(self, event=None):
        """
        Performs highlighting and dependency updates.
        Called after a delay from _on_editor_modified or manually after loading/saving.
        Resets the modified flag after processing.
        """
        # Ensure the modified flag is reset *before* getting text to avoid re-triggering <<Modified>>
        # This is the crucial change: edit_reset() is here, not in _on_editor_modified
        self.editor.edit_reset()
        self.content_modified = False # Explicitly set flag to False after reset
        self.update_title() # Update title to remove '*'

        # Perform the actual updates
        text_content = self.editor.get("1.0", tk.END)
        self.highlighter.highlight()
        self.dependency_viewer.update_dependencies(text_content)

        # Clear the stored after ID since the scheduled call has now run
        self._after_id_editor_change = None


    def update_status(self, message: str):
        """Updates the text in the status bar. Thread-safe."""
        # Put message in queue to be processed by the main thread
        self.message_queue.put(("status", message))

    def log_message(self, message: str, tag: str = "info"):
        """Appends a message to the log area. Thread-safe."""
        # Put message in queue to be processed by the main thread
        self.message_queue.put(("log", message, tag))

    def _process_queue(self):
        """Processes messages from the queue in the main thread."""
        while not self.message_queue.empty():
            try:
                msg_type, *args = self.message_queue.get_nowait()
                if msg_type == "status":
                    message = args[0]
                    self.status_bar.config(text=message)
                elif msg_type == "log":
                    message, tag = args
                    self.log_text.config(state="normal")
                    self.log_text.insert(tk.END, message + "\n", tag)
                    self.log_text.see(tk.END) # Auto-scroll to the end
                    self.log_text.config(state="disabled")
            except queue.Empty:
                pass # Should not happen with get_nowait() and while loop
            except Exception as e:
                print(f"Error processing message queue: {e}")
        # Schedule the next check
        self.root.after(100, self._process_queue)


    def update_title(self):
        """Updates the window title based on the current file/project and modification status."""
        project_name = os.path.basename(self.current_project_path) if self.current_project_path else "Untitled Project"
        file_name = os.path.basename(self.current_file_path) if self.current_file_path else "No Source File"
        modified_indicator = "*" if self.content_modified else ""
        self.root.title(f"{file_name}{modified_indicator} [{project_name}] - Doors SDKK Builder")

    def _check_unsaved_changes(self) -> bool:
        """
        Checks if there are unsaved changes in the editor and prompts the user.
        Returns True if it's safe to proceed (changes discarded or saved), False otherwise.
        """
        # Check the modified flag set by _on_editor_modified
        if self.content_modified:
            response = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes in the current source file. Do you want to save them before proceeding?"
            )
            if response is True: # Yes, save
                # If a project is open, saving the project should save the source file
                # If no project, just save the source file
                save_success = self.save_project() if self.current_project_path else self.save_file()
                return save_success # Proceed only if save was successful
            elif response is False: # No, discard
                return True # Proceed without saving
            else: # Cancel
                return False # Do not proceed
        return True # No unsaved changes, safe to proceed

    def on_closing(self):
        """Handles the window closing event, checking for unsaved changes."""
        if self._check_unsaved_changes():
            self.root.destroy()

    # --- Project Management ---

    def new_project(self):
        """Clears the current project and editor, resetting UI."""
        if self._check_unsaved_changes():
            # Reset all project-related state
            self.current_project_path = None
            self.current_file_path = None
            self.content_modified = False

            # Clear UI fields
            self.editor.delete("1.0", tk.END)
            self.package_name_var.set("MyApplication")
            self.package_version_var.set("1.0")
            self.package_description_var.set("A sample Doors application")
            self.entry_point_var.set("_start")
            self.arch_var.set("x86_64")
            # Keep current settings or reset to defaults? Let's reset to defaults for a truly new project
            self.mingw_path_var.set(DEFAULT_MINGW_PATH)
            self.kernel_elf_path_var.set(DEFAULT_KERNEL_ELF_PATH)
            self.build_dir_var.set(DEFAULT_BUILD_DIR)
            self.app_subdir_var.set(DEFAULT_APP_SUBDIR)

            # Clear files tree
            for item in self.files_tree.get_children():
                self.files_tree.delete(item)

            self.update_title()
            self.update_status("New project created.")
            self.log_text.config(state="normal")
            self.log_text.delete("1.0", tk.END)
            self.log_text.config(state="disabled")
            # Update highlighting/dependencies and reset modified flag for empty editor
            self._on_editor_change()


    def open_project(self):
        """Opens an existing project file and loads its settings and source file."""
        if not self._check_unsaved_changes():
            return

        path = filedialog.askopenfilename(
            title="Open Project File",
            defaultextension=DEFAULT_PROJECT_EXTENSION,
            filetypes=[("SDKK Project Files", f"*{DEFAULT_PROJECT_EXTENSION}"), ("All Files", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                project_data = json.load(f)

            self.current_project_path = path

            # Load package metadata
            meta = project_data.get("package_metadata", {})
            self.package_name_var.set(meta.get("name", "MyApplication"))
            self.package_version_var.set(meta.get("version", "1.0"))
            self.package_description_var.set(meta.get("description", "A sample Doors application"))

            # Load build settings
            build_settings = project_data.get("build_settings", {})
            self.entry_point_var.set(build_settings.get("entry_point", "_start"))
            self.arch_var.set(build_settings.get("architecture", "x86_64"))
            self.mingw_path_var.set(build_settings.get("mingw_path", DEFAULT_MINGW_PATH))
            self.build_dir_var.set(build_settings.get("build_directory", DEFAULT_BUILD_DIR))

            # Load deploy settings
            deploy_settings = project_data.get("deploy_settings", {})
            self.kernel_elf_path_var.set(deploy_settings.get("kernel_elf_path", DEFAULT_KERNEL_ELF_PATH))
            self.app_subdir_var.set(deploy_settings.get("app_subdirectory", DEFAULT_APP_SUBDIR))

            # Load additional files
            for item in self.files_tree.get_children():
                self.files_tree.delete(item)
            for file_info in project_data.get("additional_files", []):
                 host_path = file_info.get("host_path")
                 internal_path = file_info.get("internal_path")
                 if host_path and internal_path:
                     try:
                         file_size = os.path.getsize(host_path)
                         self.files_tree.insert("", tk.END, values=(host_path, internal_path, file_size))
                     except OSError:
                         self.files_tree.insert("", tk.END, values=(host_path, internal_path, "Missing!"))
                         self.update_status(f"Warning: File '{os.path.basename(host_path)}' not found.")

            # Load main source file
            main_source_file_path = project_data.get("main_source_file")
            if main_source_file_path and os.path.exists(main_source_file_path):
                try:
                    with open(main_source_file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        self.editor.delete("1.0", tk.END)
                        self.editor.insert("1.0", content)
                        self.current_file_path = main_source_file_path
                        self.update_status(f"Opened project and source file: {os.path.basename(main_source_file_path)}")
                except Exception as e:
                    messagebox.showwarning("Error Loading Source File", f"Could not load main source file '{main_source_file_path}' specified in project:\n{e}")
                    self.editor.delete("1.0", tk.END)
                    self.current_file_path = None
                    self.update_status(f"Opened project, but failed to load source file.")
            elif main_source_file_path:
                 messagebox.showwarning("Source File Missing", f"Main source file '{main_source_file_path}' specified in project was not found.")
                 self.editor.delete("1.0", tk.END)
                 self.current_file_path = None
                 self.update_status(f"Opened project, but main source file is missing.")
            else:
                 self.editor.delete("1.0", tk.END)
                 self.current_file_path = None
                 self.update_status(f"Opened project. No main source file specified.")

            # Update highlighting/dependencies and reset modified flag
            self._on_editor_change()


        except Exception as e:
            messagebox.showerror("Error Opening Project", f"Could not open project file:\n{e}")
            self.update_status(f"Error opening project file.")


    def save_project(self) -> bool:
        """Saves the current project settings and source file. Returns True on success."""
        if not self.current_project_path:
            return self.save_project_as()

        # If editor has content but no file path, force Save As for the source file first
        editor_content = self.editor.get("1.0", tk.END).strip()
        if editor_content and not self.current_file_path:
             messagebox.showwarning("Cannot Save Project", "Please save the main source file first or specify its path.")
             if not self.save_file_as():
                  self.update_status("Project save cancelled (source file not saved).")
                  return False
        # If editor is empty and no file path, just save the project settings
        elif not editor_content and not self.current_file_path:
             pass # OK to save project without a main source file
        # If editor has content and a file path, save the source file if modified
        elif self.current_file_path and self.content_modified:
            if not self._save_content_to_file(self.current_file_path):
                 self.update_status("Project save cancelled (failed to save source file).")
                 return False

        # Collect all project data from UI
        project_data = {
            "project_name": os.path.basename(self.current_project_path).rsplit('.', 1)[0] if self.current_project_path else "Untitled",
            "main_source_file": self.current_file_path, # Save the path, not content
            "package_metadata": {
                "name": self.package_name_var.get().strip(),
                "version": self.package_version_var.get().strip(),
                "description": self.package_description_var.get().strip()
            },
            "build_settings": {
                "architecture": self.arch_var.get(),
                "entry_point": self.entry_point_var.get().strip(),
                "mingw_path": self.mingw_path_var.get().strip(),
                "build_directory": self.build_dir_var.get().strip()
            },
            "deploy_settings": {
                "kernel_elf_path": self.kernel_elf_path_var.get().strip(),
                "app_subdirectory": self.app_subdir_var.get().strip()
            },
            "additional_files": []
        }

        for item_id in self.files_tree.get_children():
            host_path, internal_path, _ = self.files_tree.item(item_id, 'values')
            project_data["additional_files"].append({
                "host_path": host_path,
                "internal_path": internal_path
            })

        try:
            with open(self.current_project_path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=4)

            self.update_title()
            self.update_status(f"Project saved: {os.path.basename(self.current_project_path)}")
            return True

        except Exception as e:
            messagebox.showerror("Error Saving Project", f"Could not save project file:\n{e}")
            self.update_status(f"Error saving project file: {os.path.basename(self.current_project_path)}")
            return False


    def save_project_as(self) -> bool:
        """Saves the current project settings and source file to a new project file path. Returns True on success."""
        path = filedialog.asksaveasfilename(
            title="Save Project File As",
            defaultextension=DEFAULT_PROJECT_EXTENSION,
            filetypes=[("SDKK Project Files", f"*{DEFAULT_PROJECT_EXTENSION}"), ("All Files", "*.*")]
        )
        if path:
            self.current_project_path = path
            return self.save_project() # Now save using the new path
        return False


    def new_file(self):
        """Creates a new source file in the editor. Prompts to save current editor content if modified."""
        if self._check_unsaved_changes():
            self.editor.delete("1.0", tk.END)
            self.current_file_path = None
            self.content_modified = False
            self.update_title()
            self.update_status("Editor cleared for new source file.")
            # Update highlighting/dependencies and reset modified flag for empty editor
            self._on_editor_change()


    def open_file(self):
        """Opens a source file into the editor. Prompts to save current editor content if modified."""
        if not self._check_unsaved_changes():
            return

        path = filedialog.askopenfilename(
            title="Open Source File",
            defaultextension=DEFAULT_SOURCE_EXTENSION,
            filetypes=[("C Source Files", f"*{DEFAULT_SOURCE_EXTENSION}"), ("All Files", "*.*")]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self.editor.delete("1.0", tk.END)
                    self.editor.insert("1.0", content)
                    self.current_file_path = path
                    self.update_status(f"Opened source file: {os.path.basename(path)}")
                    # Update highlighting/dependencies and reset modified flag
                    self._on_editor_change()

            except Exception as e:
                messagebox.showerror("Error Opening File", f"Could not open file:\n{e}")
                self.update_status(f"Error opening file: {os.path.basename(path)}")

    def save_file(self) -> bool:
        """Saves the current editor content to the current source file path. Returns True on success."""
        if self.current_file_path:
            return self._save_content_to_file(self.current_file_path)
        else:
            return self.save_file_as()

    def save_file_as(self) -> bool:
        """Saves the current editor content to a new source file path. Returns True on success."""
        path = filedialog.asksaveasfilename(
            title="Save Source File As",
            defaultextension=DEFAULT_SOURCE_EXTENSION,
            filetypes=[("C Source Files", f"*{DEFAULT_SOURCE_EXTENSION}"), ("All Files", "*.*")]
        )
        if path:
            self.current_file_path = path
            self.update_title()
            return self._save_content_to_file(self.current_file_path)
        return False

    def _save_content_to_file(self, path: str) -> bool:
        """Helper function to save content to a given path. Returns True on success."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                content = self.editor.get("1.0", tk.END)
                # Remove the extra newline that text.get(..., END) adds
                if content.endswith('\n'):
                    content = content[:-1]
                f.write(content)
            self.update_status(f"Saved: {os.path.basename(path)}")
            # Update highlighting/dependencies and reset modified flag after saving
            self._on_editor_change()
            return True
        except Exception as e:
            messagebox.showerror("Error Saving File", f"Could not save file:\n{e}")
            self.update_status(f"Error saving file: {os.path.basename(path)}")
            return False

    # --- Package File Management ---
    def add_file_to_package(self):
        """Opens a dialog to select a file to add to the package list."""
        path = filedialog.askopenfilename(title="Select File to Add to Package")
        if path:
            initial_internal_path = os.path.basename(path)
            # Prompt user for internal path
            internal_path = simpledialog.askstring("Internal Path", f"Enter internal path for '{os.path.basename(path)}':", initialvalue=initial_internal_path)

            if internal_path is not None: # User didn't cancel
                internal_path = internal_path.strip().replace("\\", "/") # Normalize slashes and strip whitespace

                if not internal_path:
                     messagebox.showwarning("Invalid Internal Path", "Internal path cannot be empty.")
                     return

                # Check for duplicate internal paths
                for item_id in self.files_tree.get_children():
                    item_values = self.files_tree.item(item_id, 'values')
                    if item_values[1] == internal_path:
                        messagebox.showwarning("Duplicate Internal Path", f"An item with internal path '{internal_path}' already exists.")
                        return

                try:
                    file_size = os.path.getsize(path)
                    self.files_tree.insert("", tk.END, values=(path, internal_path, file_size))
                    self.update_status(f"Added '{os.path.basename(path)}' to package files.")
                except OSError as e:
                    messagebox.showerror("Error Adding File", f"Could not get size of file '{path}': {e}")
                    self.update_status(f"Error adding file: {os.path.basename(path)}")


    def remove_selected_file(self):
        """Removes the selected file(s) from the package list."""
        selected_items = self.files_tree.selection()
        if not selected_items:
            messagebox.showinfo("No Selection", "Please select file(s) to remove.")
            return

        if messagebox.askyesno("Remove Files", f"Are you sure you want to remove {len(selected_items)} selected file(s)?"):
            for item_id in selected_items:
                item_values = self.files_tree.item(item_id, 'values')
                file_name = os.path.basename(item_values[0])
                self.files_tree.delete(item_id)
                self.update_status(f"Removed '{file_name}' from package files.")


    # --- Browse Button Handlers ---
    def browse_mingw_path(self):
        """Opens a dialog to select the MinGW bin directory."""
        initial_dir = self.mingw_path_var.get() if os.path.isdir(self.mingw_path_var.get()) else "."
        directory = filedialog.askdirectory(title="Select MinGW Bin Directory", initialdir=initial_dir)
        if directory:
            self.mingw_path_var.set(os.path.normpath(directory))

    def browse_kernel_elf_path(self):
        """Opens a dialog to select the Kernel ELF file."""
        initial_dir = os.path.dirname(self.kernel_elf_path_var.get()) if os.path.exists(self.kernel_elf_path_var.get()) else "."
        path = filedialog.askopenfilename(
            title="Select Kernel ELF File",
            filetypes=[("ELF Files", "*.elf"), ("All Files", "*.*")],
            initialdir=initial_dir
        )
        if path:
            self.kernel_elf_path_var.set(os.path.normpath(path))

    def browse_build_dir(self):
        """Opens a dialog to select the Build Directory."""
        initial_dir = self.build_dir_var.get() if os.path.isdir(self.build_dir_var.get()) else "."
        directory = filedialog.askdirectory(title="Select Build Directory", initialdir=initial_dir)
        if directory:
            self.build_dir_var.set(os.path.normpath(directory))


    def build(self):
        """Saves the current source file (if part of a project) and then triggers the full build process in a thread."""
        print("DEBUG: SDKKBuilderGUI.build() called") # Debug print

        # Clear previous log
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        self.log_message("--- Build Started ---")

        editor_content = self.editor.get("1.0", tk.END).strip()

        # --- Validation ---
        if not editor_content and not self.current_file_path:
             messagebox.showinfo("No Source Code", "The editor is empty and no source file is open. Nothing to build.")
             self.update_status("Build cancelled (no source code).")
             self.log_message("Build cancelled: No source code.", "warning")
             return

        # If editor has content but no file path, force Save As for the source file first
        if editor_content and not self.current_file_path:
             messagebox.showinfo("Save Source File", "Please save the main source file before building.")
             if not self.save_file_as():
                  self.update_status("Build cancelled (source file not saved).")
                  self.log_message("Build cancelled: Source file not saved.", "warning")
                  return
        # If editor has content and a file path, save the source file if modified
        elif self.current_file_path and self.content_modified:
             if not self._save_content_to_file(self.current_file_path):
                  self.update_status("Build cancelled (failed to save source file).")
                  self.log_message("Build cancelled: Failed to save source file.", "error")
                  return

        # Now we are sure self.current_file_path is set and saved if needed

        package_name = self.package_name_var.get().strip()
        package_version = self.package_version_var.get().strip()
        package_description = self.package_description_var.get().strip()

        if not package_name:
             messagebox.showerror("Build Error", "Package Name is required.")
             self.update_status("Build failed (missing package name).")
             self.log_message("Build failed: Package Name is required.", "error")
             return
        if not package_version:
             messagebox.showerror("Build Error", "Package Version is required.")
             self.update_status("Build failed (missing package version).")
             self.log_message("Build failed: Package Version is required.", "error")
             return

        build_dir = self.build_dir_var.get().strip()
        if not build_dir:
             messagebox.showerror("Build Error", "Build Directory is not set.")
             self.update_status("Build failed (Build Directory not set).")
             self.log_message("Build failed: Build Directory not set.", "error")
             return
        try:
            os.makedirs(build_dir, exist_ok=True)
            self.log_message(f"Ensured build directory exists: {build_dir}")
        except OSError as e:
            messagebox.showerror("Build Error", f"Could not create build directory '{build_dir}':\n{e}")
            self.update_status(f"Build failed (cannot create build directory).")
            self.log_message(f"Build failed: Cannot create build directory '{build_dir}': {e}", "error")
            return

        output_sdkk_path = os.path.join(build_dir, f"{package_name}{DEFAULT_OUTPUT_EXTENSION}")

        arch = self.arch_var.get()
        entry = self.entry_point_var.get().strip()
        mingw_path = self.mingw_path_var.get().strip()

        if not mingw_path or not os.path.isdir(mingw_path):
             messagebox.showerror("Build Error", "MinGW Bin Path is not set or is not a valid directory.")
             self.update_status("Build failed (MinGW path invalid).")
             self.log_message("Build failed: MinGW Bin Path is invalid.", "error")
             return
        # current_file_path is guaranteed to exist and be saved at this point
        if not entry:
             messagebox.showerror("Build Error", "Entry Point is not set.")
             self.update_status("Build failed (Entry Point not set).")
             self.log_message("Build failed: Entry Point is not set.", "error")
             return

        # Collect additional files list from the Treeview
        additional_files_list = []
        for item_id in self.files_tree.get_children():
            host_path, internal_path, size_str = self.files_tree.item(item_id, 'values')
            # Check if host file exists before adding to the list for the builder
            if not os.path.exists(host_path):
                 self.log_message(f"Warning: Additional file '{os.path.basename(host_path)}' not found. Skipping.", "warning")
                 continue # Skip this file
            additional_files_list.append((host_path, internal_path))


        self.update_status(f"Starting full build for package '{package_name}'...")
        self.log_message(f"Starting full build for package '{package_name}'...")

        # Run build in a separate thread
        def run_build_in_thread():
            print("DEBUG: run_build_in_thread() started") # Debug print
            # Pass the log_message method as the progress_callback
            success, log = build_project(
                source_file=self.current_file_path,
                output_sdkk_path=output_sdkk_path,
                package_name=package_name,
                package_version=package_version,
                package_description=package_description,
                additional_files=additional_files_list,
                arch=arch,
                entry=entry,
                mingw_path=mingw_path,
                progress_callback=self.log_message # Use log_message for detailed output
            )
            # Use root.after to call the result handler in the main GUI thread
            self.root.after(0, self._handle_build_result, success, log, output_sdkk_path)

        threading.Thread(target=run_build_in_thread, daemon=True).start()


    def _handle_build_result(self, success: bool, log: str, output_sdkk_path: str):
        """Handles the result of the build process in the main GUI thread."""
        self.log_message("--- Build Finished ---")
        if success:
            self.update_status(f"Build successful: {os.path.basename(output_sdkk_path)}")
            self.log_message(f"Build successful: {os.path.basename(output_sdkk_path)}", "info")
            # Optionally show a success message box
            # messagebox.showinfo("Build Successful", log)
        else:
            self.update_status(f"Build failed.")
            self.log_message(f"Build failed.", "error")
            # The detailed log is already in the log area, but show a summary in a message box
            messagebox.showerror("Build Failed", "See log area for details.")


    def deploy(self):
        """Triggers the deployment process in a thread."""
        print("DEBUG: SDKKBuilderGUI.deploy() called") # Debug print

        # Clear previous log
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        self.log_message("--- Deploy Started ---")

        package_name = self.package_name_var.get().strip()
        build_dir = self.build_dir_var.get().strip()
        app_subdir = self.app_subdir_var.get().strip()
        kernel_elf_path = self.kernel_elf_path_var.get().strip()

        # --- Validation ---
        if not package_name:
             messagebox.showinfo("Deployment Info Missing", "Package Name is required.")
             self.update_status("Deployment cancelled (missing package name).")
             self.log_message("Deploy cancelled: Package Name is required.", "warning")
             return
        if not build_dir:
             messagebox.showinfo("Deployment Info Missing", "Build Directory is required.")
             self.update_status("Deployment cancelled (missing build directory).")
             self.log_message("Deploy cancelled: Build Directory is required.", "warning")
             return
        if not app_subdir:
             messagebox.showinfo("Deployment Info Missing", "App Subdirectory is required.")
             self.update_status("Deployment cancelled (missing app subdirectory).")
             self.log_message("Deploy cancelled: App Subdirectory is required.", "warning")
             return
        if not kernel_elf_path:
             messagebox.showinfo("Deployment Info Missing", "Kernel ELF Path is required.")
             self.update_status("Deployment cancelled (missing kernel ELF path).")
             self.log_message("Deploy cancelled: Kernel ELF Path is required.", "warning")
             return

        sdkk_file = os.path.join(build_dir, f"{package_name}{DEFAULT_OUTPUT_EXTENSION}")

        if not os.path.exists(sdkk_file):
             messagebox.showinfo("Build First", f"Output SDKK file '{os.path.basename(sdkk_file)}' not found.\nPlease build the project successfully first.")
             self.update_status("Deployment cancelled (output file not found).")
             self.log_message(f"Deploy cancelled: Output SDKK file '{os.path.basename(sdkk_file)}' not found. Build first.", "warning")
             return
        if not os.path.exists(kernel_elf_path):
             messagebox.showerror("Deploy Error", f"Kernel ELF Path not found: '{kernel_elf_path}'")
             self.update_status("Deployment cancelled (Kernel ELF path invalid).")
             self.log_message(f"Deploy cancelled: Kernel ELF Path not found: '{kernel_elf_path}'", "error")
             return
        if not os.path.isdir(build_dir):
             messagebox.showerror("Deploy Error", f"Build Directory not found or is not a directory: '{build_dir}'")
             self.update_status("Deployment cancelled (Build Directory invalid).")
             self.log_message(f"Deploy cancelled: Build Directory not found or is not a directory: '{build_dir}'", "error")
             return

        self.update_status(f"Starting deployment for '{os.path.basename(sdkk_file)}'...")
        self.log_message(f"Starting deployment for '{os.path.basename(sdkk_file)}'...")

        # Run deploy in a separate thread
        def run_deploy_in_thread():
            print("DEBUG: run_deploy_in_thread() started") # Debug print
            # Pass the log_message method as the progress_callback
            success, log = deploy_to_qemu(sdkk_file=sdkk_file,
                                          kernel_elf=kernel_elf_path,
                                          build_dir=build_dir,
                                          app_subdir=app_subdir,
                                          progress_callback=self.log_message) # Use log_message for detailed output
            # Use root.after to call the result handler in the main GUI thread
            self.root.after(0, self._handle_deploy_result, success, log)

        threading.Thread(target=run_deploy_in_thread, daemon=True).start()

    def _handle_deploy_result(self, success: bool, log: str):
        """Handles the result of the deployment process in the main GUI thread."""
        self.log_message("--- Deploy Finished ---")
        if success:
            self.update_status("Deployment successful. QEMU launched.")
            self.log_message("Deployment successful. QEMU launched.", "info")
            messagebox.showinfo("Deploy Success", log) # Show the PID message
        else:
            self.update_status("Deployment failed.")
            self.log_message("Deployment failed.", "error")
            messagebox.showerror("Deploy Failed", log) # Show the error message


# --- Main Entry Point ---
def main():
    """Main entry point for the SDKK Builder application."""
    root = tk.Tk()
    app = SDKKBuilderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
