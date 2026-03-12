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
Apply a patch file from any location, or use interactive selection from project patches.
```bash
python3 tools/flux-patcher/patcher.py apply /path/to/my.patch
# Or interactive selection
python3 tools/flux-patcher/patcher.py apply
```

### 3. List Patches
List all available patches in the project directories.
```bash
python3 tools/flux-patcher/patcher.py list
```

### 4. Workspace Status
Check which projects in the workspace have modifications.
```bash
python3 tools/flux-patcher/patcher.py status
```

### 5. Snapshots
Save and restore workspace states using Git branches.
```bash
python3 tools/flux-patcher/patcher.py snapshot my-feature
# ... make changes ...
python3 tools/flux-patcher/patcher.py restore my-feature
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
