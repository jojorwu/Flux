# Flux Patcher

A mini-library and CLI tool to manage Minecraft patches for the Flux project.

## Requirements
- Python 3.x
- Git
- Java 21+ (for Minecraft/Gradle)

## Installation
Currently, this is a standalone script. You can run it directly using Python.

```bash
python3 tools/flux-patcher/patcher.py --help
```

## Usage

### 1. Initialize Workspace
Sets up the environment by applying existing patches and creating an isolated copy in `.flux-workspace/`.
```bash
python3 tools/flux-patcher/patcher.py init
```

### 2. Apply Custom Patch
Apply a patch file from any location.
```bash
python3 tools/flux-patcher/patcher.py apply /path/to/my.patch
```

### 3. View Changes
See what's modified in the local workspace.
```bash
python3 tools/flux-patcher/patcher.py diff
```

### 4. Export Patch
Save your local changes into a new patch file.
```bash
python3 tools/flux-patcher/patcher.py export my-new-feature
```

### 5. Run Server
Test your changes by launching the server.
```bash
python3 tools/flux-patcher/patcher.py run
```
