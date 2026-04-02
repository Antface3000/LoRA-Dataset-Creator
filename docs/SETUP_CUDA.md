# Setting Up CUDA for This Project

## Finding Your CUDA Installation

CUDA is typically installed in one of these locations on Windows:

1. **NVIDIA CUDA Toolkit (default)**:
   ```
   C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin
   C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.x\bin
   ```

2. **Custom installation path**:
   Check where you installed CUDA for your other project.

## Quick Check - Find CUDA Location

Run this in PowerShell to find CUDA:
```powershell
Get-ChildItem "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA" -Recurse -Filter "nvcc.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 DirectoryName
```

Or check common locations:
```powershell
Test-Path "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.0\bin\nvcc.exe"
Test-Path "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin\nvcc.exe"
```

## Method 1: Add to System PATH (Permanent)

1. **Open System Environment Variables**:
   - Press `Win + X` → System → Advanced system settings
   - Click "Environment Variables"
   - Under "System variables", find and select "Path"
   - Click "Edit"

2. **Add CUDA bin directory**:
   - Click "New"
   - Add: `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin`
   - (Replace `v12.x` with your actual version)
   - Click OK on all dialogs

3. **Restart** your terminal/IDE for changes to take effect

## Method 2: Add to PATH for This Session Only

Run this in PowerShell before starting the app:
```powershell
$env:PATH += ";C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin"
python main.py
```

## Method 3: Create a Startup Script

Create a file `run_with_cuda.bat` in the project root:

```batch
@echo off
REM Add CUDA to PATH for this session
set PATH=%PATH%;C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin

REM Run the application
python main.py
pause
```

Replace `v12.x` with your actual CUDA version.

## Method 4: Set in Python Code (Project-Specific)

We can modify the code to automatically add CUDA to PATH. Let me know if you want this approach.

## Verify CUDA is Found

After adding to PATH, verify:
```powershell
nvcc --version
nvidia-smi
```

Both commands should work if CUDA is properly configured.

## What You Need

The warnings mention these specific tools:
- `cuobjdump.exe` - CUDA object dump utility
- `nvdisasm.exe` - NVIDIA disassembler

Both should be in the CUDA bin directory alongside `nvcc.exe`.
