"""Main entry point for LoRA Dataset Manager."""

import sys
import traceback
import warnings
import os
from pathlib import Path

# Try to find and add CUDA to PATH if not already there
def setup_cuda_path():
    """Attempt to add CUDA bin directory to PATH if CUDA tools are missing."""
    # Check if CUDA tools are already in PATH
    import shutil
    if shutil.which("cuobjdump.exe") and shutil.which("nvdisasm.exe"):
        return  # Already available
    
    # Common CUDA installation paths on Windows
    cuda_paths = [
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.5/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.4/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.3/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.2/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.1/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.0/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v11.8/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v11.7/bin"),
    ]
    
    # Check for CUDA environment variable
    cuda_path_env = os.environ.get("CUDA_PATH")
    if cuda_path_env:
        cuda_bin = Path(cuda_path_env) / "bin"
        if cuda_bin.exists():
            cuda_paths.insert(0, cuda_bin)
    
    # Try to find CUDA bin directory
    for cuda_bin in cuda_paths:
        if cuda_bin.exists() and (cuda_bin / "cuobjdump.exe").exists():
            cuda_bin_str = str(cuda_bin)
            if cuda_bin_str not in os.environ["PATH"]:
                os.environ["PATH"] = cuda_bin_str + os.pathsep + os.environ["PATH"]
                print(f"Added CUDA to PATH: {cuda_bin_str}")
            return
    
    # If not found, print helpful message
    print("Note: CUDA tools not found. GPU acceleration may be limited.")
    print("See SETUP_CUDA.md for instructions on adding CUDA to PATH.")

# Setup CUDA path before importing other modules
setup_cuda_path()

# Suppress CUDA/Triton warnings (non-critical - app will use CPU if CUDA not available)
warnings.filterwarnings("ignore", category=UserWarning, module="triton")

# Logging: INFO for tagger/captioner/pipeline so user can see flow and errors
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

def main():
    """Main entry point with error handling."""
    try:
        from ui.app_main import App
        app = App()
        app.run()
    except Exception as e:
        # Print full error traceback
        print("=" * 60)
        print("ERROR: Application failed to start")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        
        # Try to show error in a message box if possible
        try:
            import tkinter.messagebox as messagebox
            messagebox.showerror(
                "Application Error",
                f"Failed to start application:\n\n{str(e)}\n\n"
                f"Check console for full traceback."
            )
        except:
            pass
        
        input("\nPress Enter to exit...")
        sys.exit(1)

if __name__ == "__main__":
    main()
