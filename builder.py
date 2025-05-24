import os
import subprocess
import shutil
import sys
import hashlib
import threading
import time
import struct # Added for struct operations
from common import build_project
# Import SDK definitions
from doors_sdk import (
    SDKKPackageHeader,
    SDKKModuleEntry,
    SDKKModuleType,
    SDKKModuleFlag,
    SDKK_FORMAT_VERSION
)

# --- Configuration (Defaults - will be overridden by GUI) ---
LINKER_SCRIPT = "linker.ld" # Default name for the linker script

# Define *expected* tool names (prefixed and unprefixed)
EXPECTED_TOOL_NAMES = {
    "x86_64": {
        "cc_prefixed": "x86_64-w64-mingw32-gcc",
        "ld_prefixed": "x86_64-w64-mingw32-ld",
        "objcopy_prefixed": "x86_64-w64-mingw32-objcopy",
        "cc_unprefixed": "gcc", # Fallback for systems where tools aren't prefixed
        "ld_unprefixed": "ld",
        "objcopy_unprefixed": "objcopy"
    },
    "i686": {
        "cc_prefixed": "i686-w64-mingw32-gcc",
        "ld_prefixed": "i686-w64-mingw32-ld",
        "objcopy_prefixed": "i686-w64-mingw32-objcopy",
        "cc_unprefixed": "gcc", # Fallback
        "ld_unprefixed": "ld",
        "objcopy_unprefixed": "objcopy"
    }
}

# Mapping for linker architecture flags
LINKER_ARCH_FLAGS = {
    "x86_64": "i386:x86-64",
    "i686": "i386",
}

# --- Default Linker Script Content ---
DEFAULT_LINKER_SCRIPT_CONTENT = """\
/* Default linker script for Doors SDKK */
/* Created automatically by the SDKK Builder IDE */

ENTRY(_start)

SECTIONS
{
    . = 0x100000; /* Link address */

    .text :
    {
        *(.text)
        *(.text.*)
    }

    .rodata :
    {
        *(.rodata)
        *(.rodata.*)
    }

    .data :
    {
        *(.data)
        *(.data.*)
    }

    .bss :
    {
        *(.bss)
        *(.bss.*)
        *(COMMON)
    }

    /DISCARD/ :
    {
        *(.eh_frame)
        *(.comment)
        *(.note.gnu.build-id)
        *(.rela.*)
        *(.dynsym)
        *(.dynstr)
        *(.dynamic)
        *(.got)
        *(.got.plt)
        *(.plt)
        *(.debug*)
        *(.stab*)
        *(.iplt)
        *(.igot)
    }
}
"""

# --- SDKK Package Structure Constants (Derived from doors_sdk.py) ---
# These are now dynamically derived from the SDKK structures
# SD_KIT_HEADER_SIZE = 512 # Removed, use SDKKPackageHeader.SIZE
# SD_KIT_ENTRY_SIZE = 256  # Removed, use SDKKModuleEntry.SIZE

# --- Helper Function for Running Commands ---
def _run_command(cmd: list[str], cwd: str = None, progress_callback=None) -> tuple[bool, str]:
    """Helper function to run a command and capture output."""
    cmd_str = " ".join(subprocess.list2cmdline(cmd).split())
    # Use a unique ID for each _run_command call instance for better tracking
    # Ensure id(cmd) is converted to string before slicing
    call_id = f"{threading.current_thread().name}_{str(id(cmd))[-4:]}" # Use last 4 digits

    def report(message):
        full_message = f"[{call_id}] {message}"
        # print(full_message) # Keep console print for debug
        if progress_callback:
            progress_callback(full_message) # Send to GUI status bar/log

    report(f"Executing: {cmd_str}")

    try:
        # Use capture_output=True, text=True
        # check=True will raise CalledProcessError on non-zero exit code
        # Added timeout to prevent infinite hangs, adjust as needed
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True, timeout=300) # 5 minute timeout
        report("Command completed successfully.")
        # Combine stdout and stderr for successful commands if needed, or just return stdout
        output = result.stdout.strip()
        if result.stderr.strip():
             output += "\nStderr:\n" + result.stderr.strip()
        return True, output

    except FileNotFoundError:
        error_message = f"Error: The executable '{cmd[0]}' was not found. Make sure the MinGW Bin Path is correct and contains the necessary tools."
        report(error_message)
        return False, error_message
    except subprocess.CalledProcessError as e:
        report(f"Command failed with return code {e.returncode}.")
        stdout_content = e.stdout.strip() if e.stdout else "EMPTY STDOUT"
        stderr_content = e.stderr.strip() if e.stderr else "EMPTY STDERR"
        error_output = f"Stdout:\n{stdout_content}\nStderr:\n{stderr_content}"
        report(error_output)
        return False, error_output
    except subprocess.TimeoutExpired:
        error_message = f"Error: Command timed out after 300 seconds."
        report(error_message)
        return False, error_message
    except Exception as e:
        error_message = f"An unexpected error occurred while running command: {e}"
        report(error_message)
        return False, error_message


# --- Helper to find tool paths ---
def _find_tool_paths(mingw_path: str, arch: str, progress_callback=None) -> tuple[bool, dict, str]:
    """Finds the paths for required MinGW tools."""
    def report(message):
        # print(f"TOOL_FIND: {message}") # Keep console print for debug
        if progress_callback:
            progress_callback(f"Tool Find: {message}")

    report(f"Searching for tools for architecture '{arch}' in '{mingw_path}'...")
    tool_paths = {}
    tools_needed = ["cc", "ld", "objcopy"]
    tool_names_for_arch = EXPECTED_TOOL_NAMES.get(arch)

    if not tool_names_for_arch:
         error_msg = f"Unsupported architecture '{arch}' specified."
         report(error_msg)
         return False, {}, error_msg

    is_windows = sys.platform.startswith('win')
    mingw_bin_path = os.path.normpath(mingw_path) # Normalize path

    if not os.path.isdir(mingw_bin_path):
         error_msg = f"MinGW Bin Path '{mingw_bin_path}' is not a valid directory."
         report(error_msg)
         return False, {}, error_msg

    for tool_key in tools_needed:
        prefixed_name = tool_names_for_arch[f"{tool_key}_prefixed"]
        unprefixed_name = tool_names_for_arch[f"{tool_key}_unprefixed"]

        found_path = None
        potential_names = [prefixed_name, unprefixed_name]
        if is_windows:
             potential_names.extend([f"{name}.exe" for name in potential_names])

        report(f"  Looking for '{tool_key}' (e.g., {', '.join(potential_names[:2])}...)")

        for name in potential_names:
            path_to_check = os.path.join(mingw_bin_path, name)
            if os.path.exists(path_to_check):
                found_path = path_to_check
                break # Found the tool

        if found_path:
            tool_paths[tool_key] = found_path
            report(f"  Found {tool_key}: {found_path}")
        else:
            error_msg = (
                f"Error: Required tool '{tool_key}' not found. Looked for: "
                f"{', '.join(potential_names)} in '{mingw_bin_path}'. "
                f"Make sure the MinGW Bin Path is correct and contains the necessary executables."
            )
            report(error_msg)
            return False, {}, error_msg

    report("All required tools found.")
    return True, tool_paths, ""


# --- Compile/Link/Objcopy Function (Produces raw binary) ---
def compile_to_raw_binary(source_file: str, output_binary_path: str, arch: str = "x86_64", entry: str = "_start",
                          mingw_path: str = "C:/msys64/mingw64/bin", progress_callback=None) -> tuple[bool, str]:
    """
    Compiles, links, and converts a source file to a raw binary using MinGW tools.
    This raw binary is intended to be *part* of the final SDKK package.
    """
    def report_progress(message):
        """Helper to send messages via callback and print."""
        # print(f"BUILD_COMPILE: {message}") # Keep console print for debug
        if progress_callback:
            progress_callback(f"Compile: {message}") # Send to GUI status bar/log

    report_progress(f"Starting compilation to raw binary for '{os.path.basename(source_file)}'...")

    # --- Check Source File ---
    if not os.path.exists(source_file):
        report_progress(f"Error: Source file not found at: {source_file}")
        return False, f"Error: Source file not found at: {source_file}"

    # --- Create Temp Directories ---
    output_dir = os.path.dirname(output_binary_path)
    temp_dir_base = os.path.join(output_dir, "temp_build_bin")
    temp_dir = None
    for i in range(100): # Try a few times to find a unique name
        temp_dir_candidate = f"{temp_dir_base}_{int(time.time())}_{i}"
        if not os.path.exists(temp_dir_candidate):
            temp_dir = temp_dir_candidate
            break
        time.sleep(0.01) # Small delay before retrying

    if temp_dir is None:
         error_msg = f"Error: Could not create a unique temporary directory base on '{temp_dir_base}'."
         report_progress(error_msg)
         return False, error_msg

    report_progress(f"Creating temporary build directory: {temp_dir}")
    try:
        os.makedirs(temp_dir, exist_ok=True)
        # Verify temp directories can be written to
        test_write_path = os.path.join(temp_dir, "write_test.tmp")
        with open(test_write_path, 'w') as f:
            f.write("Test")
        os.remove(test_write_path)
        report_progress(f"Successfully verified write access to {temp_dir}")
    except Exception as e:
        error_msg = f"Error: Cannot create or write to temporary directory: {temp_dir}, Error: {e}"
        report_progress(error_msg)
        return False, error_msg

    # --- Check/Create Linker Script ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    linker_script_path = os.path.join(script_dir, LINKER_SCRIPT)

    if not os.path.exists(linker_script_path):
        report_progress(f"Linker script '{LINKER_SCRIPT}' not found at '{linker_script_path}'. Attempting to create a default one.")
        try:
            with open(linker_script_path, "w") as f:
                f.write(DEFAULT_LINKER_SCRIPT_CONTENT)
            report_progress(f"Default linker script '{LINKER_SCRIPT}' created successfully.")
        except IOError as e:
            error_msg = f"Error creating default linker script '{linker_script_path}': {e}"
            report_progress(error_msg)
            # Clean up temp dir before returning
            if os.path.exists(temp_dir):
                try: shutil.rmtree(temp_dir)
                except OSError: pass
            return False, error_msg
    else:
        report_progress(f"Using linker script: {linker_script_path}")


    # --- Determine actual tool paths ---
    success, tool_paths, error_msg = _find_tool_paths(mingw_path, arch, report_progress)
    if not success:
        # Clean up temp dir before returning
        if os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except OSError: pass
        return False, error_msg

    cc = tool_paths["cc"]
    ld = tool_paths["ld"]
    objcopy = tool_paths["objcopy"]

    # Determine intermediate object file name and linked ELF name
    source_base_name = os.path.basename(source_file)
    obj_file = os.path.join(temp_dir, source_base_name.rsplit('.', 1)[0] + ".o")
    linked_elf_output = os.path.join(temp_dir, source_base_name.rsplit('.', 1)[0] + ".elf") # Use source base name for ELF too


    try:
        # 1. Compile Source File
        report_progress(f"Compiling '{source_base_name}'...")
        cmd_compile = [
            cc,
            "-m64" if arch == "x86_64" else "-m32",
            "-ffreestanding", # No standard library headers/functions assumed
            "-fno-pie",       # Position Independent Executable (PIE) is not needed/wanted
            "-nostdlib",      # Do not link the standard library
            "-Wall", "-Wextra", # Enable common warnings
            "-c",             # Compile only, do not link
            os.path.normpath(source_file), # Normalize source file path
            "-o",
            os.path.normpath(obj_file) # Normalize output object file path
        ]
        # Run compile command from the temp directory
        success, message = _run_command(cmd_compile, cwd=temp_dir, progress_callback=report_progress)
        if not success:
            return False, f"Compilation failed:\n{message}"
        report_progress("Compilation successful.")

        # 2. Link Object File
        report_progress(f"Linking '{os.path.basename(obj_file)}'...")
        linker_arch_flag = LINKER_ARCH_FLAGS.get(arch)
        if not linker_arch_flag:
             # Clean up temp dir before returning
             if os.path.exists(temp_dir):
                 try: shutil.rmtree(temp_dir)
                 except OSError: pass
             return False, f"Internal Error: No linker architecture flag defined for '{arch}'"

        cmd_link = [
            ld,
            "-T", os.path.normpath(linker_script_path), # Use the linker script (normalized)
            "-m", linker_arch_flag,   # Specify target architecture for linker
            "-e", entry,              # Set entry point symbol
            "-o", os.path.normpath(linked_elf_output),  # Output ELF file (normalized)
            os.path.normpath(obj_file)                  # Input object file (normalized)
        ]
        # Run link command from the temp directory
        success, message = _run_command(cmd_link, cwd=temp_dir, progress_callback=report_progress)
        if not success:
            return False, f"Linking failed:\n{message}"
        report_progress("Linking successful.")

        # 3. Convert ELF to Binary using Objcopy
        report_progress(f"Converting '{os.path.basename(linked_elf_output)}' to raw binary format...")
        cmd_objcopy = [
            objcopy,
            "-O", "binary",       # Output format is raw binary
            os.path.normpath(linked_elf_output),    # Input ELF file (normalized)
            os.path.normpath(output_binary_path)    # Output raw binary file (normalized)
        ]
        # Run objcopy command from the temp directory
        success, message = _run_command(cmd_objcopy, cwd=temp_dir, progress_callback=report_progress)
        if not success:
            return False, f"Objcopy failed:\n{message}"
        report_progress("Objcopy successful.")

        report_progress(f"Raw binary created: {os.path.basename(output_binary_path)}")
        return True, f"Raw binary creation successful: {output_binary_path}"

    except Exception as e:
        error_msg = f"An unexpected error occurred during compilation/linking: {e}"
        report_progress(error_msg)
        return False, error_msg
    finally:
        # --- Cleanup ---
        report_progress(f"Cleaning up temporary directory: {temp_dir}")
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                report_progress("Temporary directory cleaned up.")
            except OSError as e:
                report_progress(f"Warning: Failed to clean up temporary directory {temp_dir}: {e}")


# --- SDKK Package Building Function ---
def build_sdkk_package(output_sdkk_path: str, package_name: str, package_version: str,
                       package_description: str, files_to_package: list[tuple[str, str]],
                       progress_callback=None) -> tuple[bool, str]:
    """
    Builds the final .sdkk package file.
    files_to_package is a list of (host_path, internal_path) tuples.
    The first file in the list is assumed to be the main executable.
    """
    def report_progress(message):
        """Helper to send messages via callback and print."""
        # print(f"BUILD_PACKAGE: {message}") # Keep console print for debug
        if progress_callback:
            progress_callback(f"Package: {message}") # Send to GUI status bar/log

    report_progress(f"Starting SDKK package building for '{package_name}'...")

    if not package_name or not package_version:
        return False, "Package name and version are required."
    if not files_to_package:
         return False, "At least one file must be included in the package."

    # Validate host paths exist
    for host_path, _ in files_to_package:
        if not os.path.exists(host_path):
            return False, f"Input file not found: '{host_path}'"

    # Prepare file entries data and calculate data section size
    file_entries_data = [] # This will store dicts with all info needed for SDKKModuleEntry
    current_data_offset = 0
    data_section_size = 0

    # Sort files by internal path (important for consistent package structure)
    files_to_package.sort(key=lambda item: item[1])

    # Determine module types and flags based on position (first is executable)
    is_first_file = True
    for host_path, internal_path in files_to_package:
        try:
            file_size = os.path.getsize(host_path)

            module_type = SDKKModuleType.APPLICATION if is_first_file else SDKKModuleType.DATA
            module_flags = SDKKModuleFlag.EXECUTABLE if is_first_file else 0 # No other flags by default

            file_entries_data.append({
                "host_path": host_path,
                "internal_path": internal_path,
                "offset": current_data_offset,
                "size": file_size,
                "type": module_type,
                "flags": module_flags,
                "signature": b'\0' * 32 # Default to empty signature (32 bytes for 8x uint32_t)
            })
            current_data_offset += file_size
            data_section_size += file_size
            is_first_file = False # Only the first file gets app/exec flags
        except OSError as e:
            return False, f"Error getting size of file '{host_path}': {e}"

    num_files = len(file_entries_data)
    entries_table_size = num_files * SDKKModuleEntry.SIZE # Use SDKKModuleEntry.SIZE

    # Calculate offsets and padding
    header_offset = 0 # Always starts at 0
    entries_table_offset = SDKKPackageHeader.SIZE # Entries table starts immediately after header
    data_section_start_after_entries = entries_table_offset + entries_table_size

    # Data section must be aligned to 512 bytes
    alignment = 512
    data_section_offset = (data_section_start_after_entries + alignment - 1) & ~(alignment - 1)
    padding_after_entries = data_section_offset - data_section_start_after_entries

    report_progress(f"Package structure calculations:")
    report_progress(f"  Header Size: {SDKKPackageHeader.SIZE} bytes")
    report_progress(f"  Entries Table Size: {entries_table_size} bytes ({num_files} files * {SDKKModuleEntry.SIZE} bytes/entry)")
    report_progress(f"  Padding after entries: {padding_after_entries} bytes")
    report_progress(f"  Data Section Offset: {data_section_offset} bytes")
    report_progress(f"  Data Section Size: {data_section_size} bytes")
    report_progress(f"  Total Package Size (approx): {data_section_offset + data_section_size} bytes")

    # Ensure output directory exists
    output_dir = os.path.dirname(output_sdkk_path)
    if output_dir and not os.path.exists(output_dir):
        report_progress(f"Creating output directory: {output_dir}")
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            return False, f"Error creating output directory '{output_dir}': {e}"


    try:
        with open(output_sdkk_path, "wb") as f:
            # 1. Write dummy header (will be updated later)
            f.write(b'\0' * SDKKPackageHeader.SIZE)
            report_progress("Wrote dummy header placeholder.")

            # 2. Write file entries table
            report_progress("Writing file entries table...")
            if f.tell() != entries_table_offset:
                 report_progress(f"Warning: Current file position ({f.tell()}) does not match calculated entries offset ({entries_table_offset}). Seeking.")
                 f.seek(entries_table_offset)

            for entry_info in file_entries_data:
                # Ensure internal_path is max 63 bytes + null terminator = 64 bytes
                internal_path_bytes = entry_info["internal_path"].encode('utf-8')
                if len(internal_path_bytes) >= 64:
                     report_progress(f"Warning: Internal path '{entry_info['internal_path']}' is too long ({len(internal_path_bytes)} bytes), truncating.")
                     internal_path_bytes = internal_path_bytes[:63]

                module_entry = SDKKModuleEntry(
                    name=internal_path_bytes.ljust(64, b'\0'),
                    offset=entry_info["offset"],
                    size=entry_info["size"],
                    type=entry_info["type"].value, # Use .value for IntEnum
                    flags=entry_info["flags"].value, # Use .value for IntEnum
                    signature=entry_info["signature"],
                    padding=b'\0' * (SDKKModuleEntry.SIZE - (64 + 8 + 8 + 4 + 4 + 32)) # Calculate padding dynamically
                )
                f.write(module_entry.pack())
                report_progress(f"  - Wrote entry for '{entry_info['internal_path']}' (offset={entry_info['offset']}, size={entry_info['size']}, type={entry_info['type'].name}, flags={entry_info['flags']})")

            report_progress("Finished writing file entries table.")

            # 3. Write padding after entries table
            if padding_after_entries > 0:
                report_progress(f"Writing {padding_after_entries} bytes of padding.")
                f.write(b'\0' * padding_after_entries)

            # 4. Write data section and calculate hash
            report_progress("Writing data section and calculating hash...")
            sha256_hasher = hashlib.sha256()
            current_pos = f.tell()
            if current_pos != data_section_offset:
                 report_progress(f"Warning: Current file position ({current_pos}) does not match calculated data offset ({data_section_offset}). Seeking to correct position.")
                 f.seek(data_section_offset)

            for entry_info in file_entries_data:
                report_progress(f"  - Writing content for '{entry_info['internal_path']}' from '{entry_info['host_path']}'...")
                try:
                    with open(entry_info["host_path"], "rb") as infile:
                        bytes_written_for_file = 0
                        while True:
                            chunk = infile.read(4096) # Read in chunks
                            if not chunk:
                                break
                            f.write(chunk)
                            sha256_hasher.update(chunk)
                            bytes_written_for_file += len(chunk)
                        if bytes_written_for_file != entry_info["size"]:
                             report_progress(f"Warning: Bytes written for '{entry_info['internal_path']}' ({bytes_written_for_file}) does not match expected size ({entry_info['size']}).")
                except IOError as e:
                     # This is a critical error during packaging
                     raise IOError(f"Failed to read file '{entry_info['host_path']}' for packaging: {e}")


            data_sha256_hash = sha256_hasher.digest()
            report_progress(f"Calculated data SHA-256 hash: {data_sha256_hash.hex()}")
            report_progress("Finished writing data section.")

            # 5. Update SDKK header
            report_progress("Updating SDKK header...")
            f.seek(0) # Go back to the beginning of the file

            # Create a temporary header object for checksum calculation
            temp_header = SDKKPackageHeader(
                magic=b'SDKK',
                format_version=SDKK_FORMAT_VERSION, # Use the constant from doors_sdk
                package_name=package_name.encode('utf-8')[:63].ljust(64, b'\0'),
                package_version_str=package_version.encode('utf-8')[:15].ljust(16, b'\0'),
                package_description=package_description.encode('utf-8')[:255].ljust(256, b'\0'),
                entry_count=num_files,
                entries_table_offset=entries_table_offset,
                data_section_offset=data_section_offset,
                data_section_size=data_section_size,
                data_sha256_hash=data_sha256_hash,
                reserved=b'\0' * 108,
                header_checksum=0 # Placeholder for checksum calculation
            )
            # Pack everything *except* the final checksum field for checksum calculation
            # This requires packing the first part of the format string.
            header_content_for_checksum = struct.pack(
                SDKKPackageHeader.FORMAT[:-1], # Exclude the last 'I' for checksum
                temp_header.magic,
                temp_header.format_version,
                temp_header.package_name,
                temp_header.package_version_str,
                temp_header.package_description,
                temp_header.entry_count,
                temp_header.entries_table_offset,
                temp_header.data_section_offset,
                temp_header.data_section_size,
                temp_header.data_sha256_hash,
                temp_header.reserved
            )
            header_checksum_val = sum(header_content_for_checksum) & 0xFFFFFFFF

            # Create the final header object with the calculated checksum
            final_header = SDKKPackageHeader(
                magic=b'SDKK',
                format_version=SDKK_FORMAT_VERSION,
                package_name=package_name.encode('utf-8')[:63].ljust(64, b'\0'),
                package_version_str=package_version.encode('utf-8')[:15].ljust(16, b'\0'),
                package_description=package_description.encode('utf-8')[:255].ljust(256, b'\0'),
                entry_count=num_files,
                entries_table_offset=entries_table_offset,
                data_section_offset=data_section_offset,
                data_section_size=data_section_size,
                data_sha256_hash=data_sha256_hash,
                reserved=b'\0' * 108,
                header_checksum=header_checksum_val
            )

            final_header_data = final_header.pack()

            if len(final_header_data) != SDKKPackageHeader.SIZE:
                 error_msg = f"Internal Error: Calculated final header size ({len(final_header_data)}) does not match expected SDKKPackageHeader.SIZE ({SDKKPackageHeader.SIZE})."
                 report_progress(error_msg)
                 # Clean up the partially written file
                 if os.path.exists(output_sdkk_path):
                     try: os.remove(output_sdkk_path)
                     except OSError: pass
                 return False, error_msg

            f.seek(0) # Ensure we are at the start
            f.write(final_header_data)
            report_progress("SDKK header updated with metadata, offsets, hash, and checksum.")

        report_progress(f"SDKK package '{os.path.basename(output_sdkk_path)}' built successfully.")
        return True, f"SDKK package built successfully: {output_sdkk_path}"

    except IOError as e:
        error_msg = f"Error writing SDKK file '{output_sdkk_path}': {e}"
        report_progress(error_msg)
        # Clean up the partially written file
        if os.path.exists(output_sdkk_path):
            try: os.remove(output_sdkk_path)
            except OSError: pass
        return False, error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during SDKK packaging: {e}"
        report_progress(error_msg)
        # Clean up the partially written file
        if os.path.exists(output_sdkk_path):
            try: os.remove(output_sdkk_path)
            except OSError: pass
        return False, error_msg


# --- Main Build Orchestration Function (Used by GUI) ---
def build_project(source_file: str, output_sdkk_path: str, package_name: str,
                  package_version: str, package_description: str,
                  additional_files: list[tuple[str, str]],
                  arch: str = "x86_64", entry: str = "_start",
                  mingw_path: str = "C:/msys64/mingw64/bin", progress_callback=None) -> tuple[bool, str]:
    """
    Orchestrates the full build process: compile source to binary, then package into SDKK.
    """
    def report_progress(message):
        """Helper to send messages via callback and print."""
        # print(f"BUILD_ORCHESTRATION: {message}") # Keep console print for debug
        if progress_callback:
            progress_callback(f"Orchestration: {message}") # Send to GUI status bar/log


    report_progress(f"Starting full build process for package '{package_name}'...")

    # Create a temporary path for the intermediate binary within the build directory
    build_dir = os.path.dirname(output_sdkk_path)
    temp_binary_dir_base = os.path.join(build_dir, "temp_bin")
    temp_binary_dir = None
    for i in range(100): # Try a few times to find a unique name
        temp_binary_dir_candidate = f"{temp_binary_dir_base}_{int(time.time())}_{i}"
        if not os.path.exists(temp_binary_dir_candidate):
            temp_binary_dir = temp_binary_dir_candidate
            break
        time.sleep(0.01) # Small delay before retrying

    if temp_binary_dir is None:
         error_msg = f"Error: Could not create a unique temporary binary directory base on '{temp_binary_dir_base}'."
         report_progress(error_msg)
         return False, error_msg

    temp_binary_path = os.path.join(temp_binary_dir, "entry_binary.bin")

    report_progress(f"Temporary binary will be created at: {temp_binary_path}")

    # Ensure the temporary binary directory exists
    try:
        os.makedirs(temp_binary_dir, exist_ok=True)
    except OSError as e:
        error_msg = f"Error creating temporary binary directory '{temp_binary_dir}': {e}"
        report_progress(error_msg)
        return False, error_msg


    # --- Step 1: Compile Source to Raw Binary ---
    report_progress("Step 1/2: Compiling main source file to raw binary...")
    success, message = compile_to_raw_binary(source_file, temp_binary_path, arch, entry, mingw_path, progress_callback)

    if not success:
        report_progress("Compilation step failed.")
        # Cleanup temp binary dir on failure
        if os.path.exists(temp_binary_dir):
            try: shutil.rmtree(temp_binary_dir)
            except OSError: pass
        return False, f"Compilation failed:\n{message}"

    report_progress("Compilation step successful.")

    # --- Step 2: Build SDKK Package ---
    report_progress("Step 2/2: Building SDKK package...")

    # Add the compiled binary to the list of files to package
    # The internal path for the main binary is derived from the source file name
    entry_internal_path = os.path.basename(source_file).rsplit('.', 1)[0] + ".bin"
    entry_internal_path = entry_internal_path.replace("\\", "/") # Use forward slashes for internal paths

    files_to_package_for_sdkk = [(temp_binary_path, entry_internal_path)]

    # Add additional files, checking for duplicate internal paths
    existing_internal_paths = {entry_internal_path}
    for host_path, internal_path in additional_files:
        normalized_internal_path = internal_path.replace("\\", "/")
        if normalized_internal_path in existing_internal_paths:
            report_progress(f"Warning: Duplicate internal path '{normalized_internal_path}' specified for host file '{host_path}'. Skipping this file.")
            continue # Skip this file
        if not os.path.exists(host_path):
             report_progress(f"Warning: Additional file '{host_path}' not found. Skipping.")
             continue # Skip missing files
        files_to_package_for_sdkk.append((host_path, normalized_internal_path))
        existing_internal_paths.add(normalized_internal_path)

    # Check if the main binary was actually created
    if not os.path.exists(temp_binary_path):
         error_msg = f"Internal Error: Compiled binary not found at '{temp_binary_path}' after successful compilation report."
         report_progress(error_msg)
         # Cleanup temp binary dir on failure
         if os.path.exists(temp_binary_dir):
             try: shutil.rmtree(temp_binary_dir)
             except OSError: pass
         return False, error_msg

    success, message = build_sdkk_package(output_sdkk_path, package_name, package_version,
                                          package_description, files_to_package_for_sdkk,
                                          progress_callback)

    # --- Cleanup ---
    report_progress(f"Cleaning up temporary binary directory: {temp_binary_dir}")
    if os.path.exists(temp_binary_dir):
        try:
            shutil.rmtree(temp_binary_dir)
            report_progress("Temporary binary directory cleaned up.")
        except OSError as e:
            report_progress(f"Warning: Failed to clean up temporary binary directory {temp_binary_dir}: {e}")


    if success:
        report_progress("Full build process completed successfully.")
        return True, message
    else:
        report_progress("SDKK packaging step failed.")
        return False, f"SDKK packaging failed:\n{message}"

