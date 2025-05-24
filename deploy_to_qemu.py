import subprocess
import os
import shutil
import sys
import shlex # Added for safer command splitting if needed, though list is better

# --- Configuration (Defaults - will be overridden by GUI) ---
# DEFAULT_KERNEL_ELF and DEFAULT_BUILD_DIR are now parameters
# This should match where the Doors Package Manager expects SDKK files
# DEFAULT_APP_SUBDIR is now a parameter from the GUI

# Define QEMU command based on platform (executable name)
if sys.platform.startswith('win'):
    QEMU_EXECUTABLE = 'qemu-system-x86_64.exe'
elif sys.platform.startswith('linux'):
    QEMU_EXECUTABLE = 'qemu-system-x86_64'
elif sys.platform.startswith('darwin'): # macOS
     QEMU_EXECUTABLE = 'qemu-system-x86_64'
else:
    QEMU_EXECUTABLE = 'qemu-system-x86_64' # Default guess

# Define base QEMU command arguments (kernel and hda paths will be filled by function args)
# Use placeholders that are unlikely to conflict with actual paths
BASE_QEMU_ARGS = [
    QEMU_EXECUTABLE,
    '-kernel', '__KERNEL_ELF_PLACEHOLDER__', # Placeholder for kernel path
    '-hda', '__HDA_PATH_PLACEHOLDER__',     # Placeholder for build dir (as hda)
    '-m', '256M', # Example: Allocate 256MB RAM
    '-serial', 'stdio' # Example: Redirect serial output to console (useful for debugging)
    # Add other common QEMU options here if needed, e.g., -cpu host, -smp 2
    # '-cpu', 'qemu64', # Or 'host' if supported and desired
    # '-smp', 'cores=1,threads=1,sockets=1', # Example: 1 CPU core
    # '-no-reboot', # Prevent QEMU from rebooting on shutdown
    # '-display', 'gtk', # Or 'sdl', 'none' etc. depending on needs and platform
]

# --- Helper Function for Running Commands (reused/adapted) ---
def _run_deploy_command(cmd: list[str], cwd: str = None, progress_callback=None) -> tuple[bool, str]:
    """Helper function to run a command and capture output."""
    cmd_str = " ".join(subprocess.list2cmdline(cmd).split())
    if progress_callback:
        progress_callback(f"Executing: {cmd_str}")
    # print(f"Executing: {cmd_str}") # Keep console print for debug

    try:
        # Use Popen to run QEMU in the background (non-blocking for GUI)
        # shell=False is default and safer
        # We don't capture stdout/stderr here as QEMU might open its own window or redirect to stdio
        # We also don't use check=True because we don't want the GUI thread to block waiting for QEMU to exit
        # We redirect stdout/stderr to DEVNULL or a file if we don't want it cluttering the console
        # For now, let's let it go to console via stdio serial, but Popen doesn't capture it here.
        # If serial is not stdio, you might want to capture or redirect.
        process = subprocess.Popen(cmd, cwd=cwd)
        # We don't wait for the process, just report that it started.
        return True, f"QEMU process started with PID {process.pid}. Check QEMU window or console for output."

    except FileNotFoundError:
        error_message = f"Error: QEMU executable '{cmd[0]}' not found. Make sure QEMU is installed and in your system's PATH."
        if progress_callback:
            progress_callback(error_message)
        # print(error_message) # Keep console print for debug
        return False, error_message
    except Exception as e:
        error_message = f"An unexpected error occurred while trying to run QEMU: {e}"
        if progress_callback:
            progress_callback(error_message)
        # print(error_message) # Keep console print for debug
        return False, error_message

# --- Main Deploy Function ---
def deploy_to_qemu(sdkk_file: str, kernel_elf: str, build_dir: str, app_subdir: str,
                    qemu_extra_args: list[str] = None, progress_callback=None) -> tuple[bool, str]:
    """
    Copies the SDKK file to the build directory and runs QEMU.

    Args:
        sdkk_file: Path to the built .sdkk application file.
        kernel_elf: Path to the kernel ELF file.
        build_dir: The main build directory for QEMU's disk image (exposed via fat:rw).
        app_subdir: The subdirectory within build_dir where applications should be copied.
                    This should match the expected install location in Doors.
        qemu_extra_args: Optional list of *additional* arguments for the QEMU command.
        progress_callback: A function (str) -> None to report progress messages.

    Returns:
        A tuple: (success: bool, message: str).
    """
    def report_progress(message):
        """Helper to send messages via callback and print."""
        # print(f"DEPLOY: {message}") # Keep console print for debug
        if progress_callback:
            progress_callback(f"Deploy: {message}") # Send to GUI status bar/log

    report_progress(f"Starting deployment process for '{os.path.basename(sdkk_file)}'...")

    # Validate input paths
    if not os.path.exists(sdkk_file):
        report_progress(f"Error: SDKK file not found: '{sdkk_file}'")
        return False, f"Error: SDKK file not found: '{sdkk_file}'"

    if not os.path.exists(kernel_elf):
        report_progress(f"Error: Kernel ELF not found: '{kernel_elf}'")
        return False, f"Error: Kernel ELF not found: '{kernel_elf}'"

    if not os.path.isdir(build_dir):
        report_progress(f"Error: Build directory not found or is not a directory: '{build_dir}'")
        return False, f"Error: Build directory not found or is not a directory: '{build_dir}'"

    # Construct the full QEMU command list
    actual_qemu_cmd = BASE_QEMU_ARGS[:] # Start with a copy of base args

    # Find and replace kernel and hda placeholders
    try:
        # Find index of '-kernel' and replace the *next* element
        kernel_idx = actual_qemu_cmd.index('-kernel')
        if kernel_idx + 1 < len(actual_qemu_cmd):
            actual_qemu_cmd[kernel_idx + 1] = os.path.normpath(kernel_elf) # Use normalized path
        else:
             error_msg = "Internal Error: Malformed BASE_QEMU_ARGS (missing kernel path placeholder after -kernel)"
             report_progress(error_msg)
             return False, error_msg

        # Find index of '-hda' and replace the *next* element
        hda_idx = actual_qemu_cmd.index('-hda')
        if hda_idx + 1 < len(actual_qemu_cmd):
            # Use fat:rw: to expose the build directory as a disk image
            # Ensure build_dir path is normalized and correctly formatted for QEMU fat:
            # QEMU fat: expects a host path. os.path.normpath is usually sufficient.
            qemu_hda_path = f'fat:rw:{os.path.normpath(build_dir)}'
            actual_qemu_cmd[hda_idx + 1] = qemu_hda_path
        else:
             error_msg = "Internal Error: Malformed BASE_QEMU_ARGS (missing hda path placeholder after -hda)"
             report_progress(error_msg)
             return False, error_msg

    except ValueError as e:
         error_msg = f"Internal Error: Missing expected argument placeholder in BASE_QEMU_ARGS: {e}"
         report_progress(error_msg)
         return False, error_msg

    # Add any extra arguments provided by the GUI (currently none, but for future use)
    if qemu_extra_args:
        report_progress(f"Adding extra QEMU arguments: {qemu_extra_args}")
        actual_qemu_cmd.extend(qemu_extra_args)


    # Ensure the application destination directory exists within the build directory
    # This is the directory that will appear as a directory on the FAT drive in QEMU
    app_dest_dir_on_host = os.path.join(build_dir, app_subdir)
    report_progress(f"Ensuring application directory exists on host (for QEMU FAT): '{app_dest_dir_on_host}'")
    try:
        os.makedirs(app_dest_dir_on_host, exist_ok=True)
        report_progress("Directory exists or created.")
    except OSError as e:
        error_msg = f"Error creating application directory '{app_dest_dir_on_host}': {e}"
        report_progress(error_msg)
        return False, error_msg

    # Copy .sdkk to the application directory within the build directory
    app_dest_path_on_host = os.path.join(app_dest_dir_on_host, os.path.basename(sdkk_file))
    report_progress(f"Copying '{os.path.basename(sdkk_file)}' to '{app_dest_path_on_host}'...")
    try:
        shutil.copy2(sdkk_file, app_dest_path_on_host) # Use copy2 to preserve metadata if needed
        report_progress("File copied successfully.")
    except shutil.Error as e:
        error_msg = f"Error copying SDKK file: {e}"
        report_progress(error_message)
        return False, error_msg
    except Exception as e:
         error_msg = f"An unexpected error occurred during file copy: {e}"
         report_progress(error_message)
         return False, error_msg

    # Run QEMU using subprocess.Popen with list of arguments
    report_progress("Launching QEMU...")
    success, message = _run_deploy_command(actual_qemu_cmd, progress_callback=report_progress)

    if success:
        report_progress("QEMU launched successfully.")
        return True, f"Successfully launched QEMU.\n{message}"
    else:
        report_progress("Failed to launch QEMU.")
        return False, f"Failed to launch QEMU:\n{message}"

