# Finding Ollama Models on Windows

## Default Ollama Model Location

Ollama typically stores models in:
```
C:\Users\<YourUsername>\.ollama\models\
```

Or you can find it by checking:
```
%USERPROFILE%\.ollama\models
```

## Finding Your Ollama Models

### Method 1: Check Default Location
1. Open File Explorer
2. Navigate to: `C:\Users\<YourUsername>\.ollama\models`
3. Look for folders named like:
   - `gemma2`
   - `gemma`
   - `gemma3`
   - Or other model names

### Method 2: Use Command Line
Open PowerShell and run:
```powershell
Get-ChildItem "$env:USERPROFILE\.ollama\models" -Directory
```

### Method 3: Check Ollama Info
Run in PowerShell:
```powershell
ollama list
```

This will show you all installed models. Then check:
```powershell
ollama show gemma2 --modelfile
```

## Configuring Custom Ollama Path

If your Ollama models are in a different location, edit `core/config.py`:

```python
# Set this to your actual Ollama models path
GEMMA3_OLLAMA_PATH = Path("C:/path/to/your/ollama/models/gemma3")
```

Or if you want to use a different Gemma model:
```python
GEMMA3_OLLAMA_PATH = Path("C:/path/to/your/ollama/models/gemma2")
```

## Note About Ollama Model Format

Ollama models are stored in a different format than HuggingFace models. They may need special handling. If the automatic detection doesn't work, you may need to:

1. Export the model from Ollama to HuggingFace format, OR
2. Use Ollama's API directly (which would require different code)

Let me know what you find and we can adjust the code accordingly!
