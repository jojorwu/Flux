import argparse
import os
import subprocess
import sys
import shutil
from pathlib import Path

class FluxPatcher:
    def __init__(self):
        self.root_dir = self.find_root()
        self.workspace_dir = self.root_dir / ".flux-workspace"
        self.gradlew = self.root_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")

    def find_root(self):
        curr = Path(os.getcwd()).absolute()
        while curr != curr.parent:
            if (curr / "gradlew").exists() and (curr / "flux-server").exists():
                return curr
            curr = curr.parent
        return Path(os.getcwd()).absolute()

    def run_gradle(self, *args):
        cmd = [str(self.gradlew)] + list(args)
        print(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, cwd=self.root_dir)

    def init_workspace(self):
        print(f"Initializing workspace at {self.workspace_dir}...")

        # Ensure paper-server and paper-api are generated in root first
        self.run_gradle("applyAllPatches")

        if self.workspace_dir.exists():
            shutil.rmtree(self.workspace_dir)
        self.workspace_dir.mkdir(parents=True)

        def ignore_build(path, names):
            return ["build", ".gradle", "bin", "out"]

        # Copy generated projects to workspace for isolation
        for project in ["paper-server", "paper-api"]:
            src = self.root_dir / project
            dst = self.workspace_dir / project
            if src.exists():
                print(f"Copying {project} to workspace...")
                shutil.copytree(src, dst, ignore=ignore_build)
                # Initialize a temporary git repo in the workspace for diffing/patching
                subprocess.run(["git", "init"], cwd=dst)
                subprocess.run(["git", "add", "."], cwd=dst)
                subprocess.run(["git", "commit", "-m", "Initial state"], cwd=dst)

        print(f"Workspace initialized at {self.workspace_dir}")

    def apply_patch(self, patch_paths):
        for patch_path in patch_paths:
            patch_path = Path(patch_path).absolute()
            if not patch_path.exists():
                print(f"Patch not found: {patch_path}")
                continue

            print(f"Applying patch: {patch_path}")

            # Heuristic to find the right directory in workspace
            content = patch_path.read_text(errors="ignore")
            if "a/net/minecraft" in content or "a/com/mojang" in content:
                target_dir = self.workspace_dir / "paper-server"
            elif "flux-api" in patch_path.parts or "paper-api" in content:
                target_dir = self.workspace_dir / "paper-api"
            else:
                target_dir = self.workspace_dir / "paper-server"

            if not target_dir.exists():
                print(f"Target directory {target_dir} does not exist. Run 'init' first.")
                continue

            # Using git apply
            try:
                subprocess.run(["git", "apply", "--verbose", str(patch_path)], cwd=target_dir, check=True)
                print(f"Successfully applied {patch_path.name} to {target_dir.name} (in workspace)")
            except subprocess.CalledProcessError:
                print(f"Failed to apply {patch_path.name}")

    def show_diff(self):
        for project in ["paper-server", "paper-api"]:
            target_dir = self.workspace_dir / project
            if target_dir.exists():
                print(f"\n--- Changes in {project} ---")
                subprocess.run(["git", "diff", "HEAD"], cwd=target_dir)

    def export_patch(self, name):
        if not name.endswith(".patch"):
            name += ".patch"

        for project in ["paper-server", "paper-api"]:
            target_dir = self.workspace_dir / project
            if not target_dir.exists():
                continue

            # Check if there are changes (staged or unstaged)
            res = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=target_dir)
            if res.returncode != 0:
                output_path = self.root_dir / f"{project}-{name}"
                with open(output_path, "w") as f:
                    f.write(f"From: Flux Patcher <flux@patcher.local>\n")
                    f.write(f"Subject: [PATCH] {name.replace('.patch', '')}\n\n")
                    subprocess.run(["git", "diff", "HEAD"], cwd=target_dir, stdout=f)
                print(f"Exported {project} patch to {output_path}")

    def apply_to_main(self):
        """Syncs changes from workspace back to the main project for testing/running."""
        print("Syncing changes from workspace to main project...")
        for project in ["paper-server", "paper-api"]:
            ws_dir = self.workspace_dir / project
            main_dir = self.root_dir / project
            if ws_dir.exists() and main_dir.exists():
                # Export diff from workspace and apply to main
                patch_file = self.root_dir / f"tmp_{project}.patch"
                with open(patch_file, "w") as f:
                    subprocess.run(["git", "diff", "HEAD"], cwd=ws_dir, stdout=f)

                if os.path.getsize(patch_file) > 0:
                    try:
                        subprocess.run(["git", "apply", str(patch_file)], cwd=main_dir, check=True)
                        print(f"Synced {project} changes.")
                    except subprocess.CalledProcessError:
                        print(f"Failed to sync {project} changes. Conflict?")
                os.remove(patch_file)

    def run_test_server(self):
        # First sync changes to main because 'runServer' runs on the main project
        self.apply_to_main()
        print("Compiling and running server from main project...")
        self.run_gradle(":flux-server:runServer")

def main():
    parser = argparse.ArgumentParser(description="Flux Patcher Tool")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize workspace")

    apply_parser = subparsers.add_parser("apply", help="Apply patch(es)")
    apply_parser.add_argument("patches", nargs="+", help="Paths to patch files")

    subparsers.add_parser("diff", help="Show current changes")

    subparsers.add_parser("sync", help="Sync changes from workspace to main project")

    export_parser = subparsers.add_parser("export", help="Export changes as a patch")
    export_parser.add_argument("name", help="Name of the patch file")

    subparsers.add_parser("run", help="Run test server")

    args = parser.parse_args()
    patcher = FluxPatcher()

    if args.command == "init":
        patcher.init_workspace()
    elif args.command == "apply":
        patcher.apply_patch(args.patches)
    elif args.command == "diff":
        patcher.show_diff()
    elif args.command == "sync":
        patcher.apply_to_main()
    elif args.command == "export":
        patcher.export_patch(args.name)
    elif args.command == "run":
        patcher.run_test_server()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
