import argparse
import os
import subprocess
import sys
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Union

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("flux-patcher")

class FluxPatcher:
    """A tool to manage Minecraft patches for the Flux project."""

    def __init__(self):
        """Initializes the FluxPatcher with root and workspace directories."""
        self.root_dir = self.find_root()
        self.workspace_dir = self.root_dir / ".flux-workspace"
        self.gradlew = self.root_dir / ("gradlew.bat" if os.name == "nt" else "gradlew")

    def find_root(self) -> Path:
        """Finds the root directory of the project by looking for gradlew and flux-server."""
        curr = Path(os.getcwd()).absolute()
        while curr != curr.parent:
            if (curr / "gradlew").exists() and (curr / "flux-server").exists():
                return curr
            curr = curr.parent
        return Path(os.getcwd()).absolute()

    def run_gradle(self, *args: str) -> Union[subprocess.CompletedProcess, subprocess.CalledProcessError]:
        """Runs a Gradle task using the project's Gradle wrapper."""
        cmd = [str(self.gradlew)] + list(args)
        logger.info(f"Running Gradle: {' '.join(cmd)}")
        try:
            return subprocess.run(cmd, cwd=self.root_dir, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Gradle command failed with exit code {e.returncode}")
            return e

    def init_workspace(self, skip_gradle: bool = False) -> None:
        """Initializes the workspace by applying patches and copying projects."""
        logger.info(f"Initializing workspace at {self.workspace_dir}...")

        if not skip_gradle:
            # Ensure flux-server and flux-api are generated in root first
            res = self.run_gradle("applyAllPatches")
            if isinstance(res, subprocess.CalledProcessError):
                logger.error("Failed to apply patches to root project. Aborting workspace init.")
                return

        if self.workspace_dir.exists():
            logger.info("Cleaning existing workspace...")
            shutil.rmtree(self.workspace_dir)
        self.workspace_dir.mkdir(parents=True)

        def ignore_build(path, names):
            return ["build", ".gradle", "bin", "out", ".git"]

        # Copy generated projects to workspace for isolation
        for project in ["flux-server", "flux-api"]:
            src = self.root_dir / project
            dst = self.workspace_dir / project
            if src.exists():
                logger.info(f"Copying {project} to workspace...")
                shutil.copytree(src, dst, ignore=ignore_build)
                # Initialize a temporary git repo in the workspace for diffing/patching
                try:
                    subprocess.run(["git", "init", "-b", "main"], cwd=dst, check=True, capture_output=True)

                    # Check if there are any files to add
                    if any(dst.iterdir()):
                        subprocess.run(["git", "config", "user.email", "flux@patcher.local"], cwd=dst, check=True)
                        subprocess.run(["git", "config", "user.name", "Flux Patcher"], cwd=dst, check=True)
                        subprocess.run(["git", "add", "-A", "."], cwd=dst, check=True, capture_output=True)
                        # Use -n to skip any hooks that might fail in this minimal env
                        subprocess.run(["git", "commit", "-n", "-m", "Initial state"], cwd=dst, check=True, capture_output=True)
                    else:
                        logger.warning(f"Project directory {project} in workspace is empty.")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to initialize git in {project}: {e.stderr.decode().strip()}")
            else:
                logger.warning(f"Project directory {project} not found in root. Skipping.")

        logger.info(f"Workspace initialized at {self.workspace_dir}")

    def apply_patch(self, patch_paths: List[str], dry_run: bool = False) -> None:
        """Applies one or more patch files to the workspace."""
        for patch_path in patch_paths:
            patch_path = Path(patch_path).absolute()
            if not patch_path.exists():
                logger.error(f"Patch not found: {patch_path}")
                continue

            logger.info(f"{'Dry-running' if dry_run else 'Applying'} patch: {patch_path}")

            # Heuristic to find the right directory in workspace
            try:
                content = patch_path.read_text(errors="ignore")
            except Exception as e:
                logger.error(f"Failed to read patch file {patch_path}: {e}")
                continue

            if any(x in content for x in ["a/net/minecraft", "a/com/mojang", "a/org/bukkit/craftbukkit", "a/org/spigotmc", "a/src/main/java/ca/spottedleaf/moonrise"]):
                target_dir = self.workspace_dir / "flux-server"
            elif "flux-api" in patch_path.parts or "paper-api" in content or "a/org/bukkit" in content:
                target_dir = self.workspace_dir / "flux-api"
            else:
                target_dir = self.workspace_dir / "flux-server"

            if not target_dir.exists():
                logger.error(f"Target directory {target_dir} does not exist. Run 'init' first.")
                continue

            # Using git apply
            cmd = ["git", "apply", "--verbose"]
            if dry_run:
                cmd.append("--check")
            cmd.append(str(patch_path))

            try:
                subprocess.run(cmd, cwd=target_dir, check=True)
                logger.info(f"Successfully {'checked' if dry_run else 'applied'} {patch_path.name} to {target_dir.name} (in workspace)")
            except subprocess.CalledProcessError:
                logger.error(f"Failed to {'check' if dry_run else 'apply'} {patch_path.name} to {target_dir.name}")

    def show_diff(self) -> None:
        """Shows the Git diff of all projects in the workspace."""
        for project in ["flux-server", "flux-api"]:
            target_dir = self.workspace_dir / project
            if target_dir.exists():
                print(f"\n--- Changes in {project} ---")
                subprocess.run(["git", "diff", "HEAD"], cwd=target_dir)
            else:
                logger.debug(f"Project {project} not in workspace.")

    def export_patch(self, name: str) -> None:
        """Exports local changes from the workspace into patch files."""
        if not name.endswith(".patch"):
            name += ".patch"

        found_changes = False
        for project in ["flux-server", "flux-api"]:
            target_dir = self.workspace_dir / project
            if not target_dir.exists():
                continue

            # Check if there are changes (staged or unstaged)
            res = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=target_dir)
            if res.returncode != 0:
                output_path = self.root_dir / f"{project}-{name}"
                try:
                    with open(output_path, "w") as f:
                        subprocess.run(["git", "diff", "HEAD"], cwd=target_dir, stdout=f, check=True)
                        f.write(f"\nFrom: Flux Patcher <flux@patcher.local>\n")
                        f.write(f"Subject: [PATCH] {name.replace('.patch', '')}\n")
                    logger.info(f"Exported {project} patch to {output_path}")
                    found_changes = True
                except Exception as e:
                    logger.error(f"Failed to export patch for {project}: {e}")

        if not found_changes:
            logger.info("No changes found in workspace to export.")

    def apply_to_main(self) -> None:
        """Syncs changes from workspace back to the main project for testing/running."""
        logger.info("Syncing changes from workspace to main project...")
        for project in ["flux-server", "flux-api"]:
            ws_dir = self.workspace_dir / project
            main_dir = self.root_dir / project
            if ws_dir.exists() and main_dir.exists():
                # Export diff from workspace and apply to main
                patch_file = self.root_dir / f"tmp_{project}.patch"
                try:
                    with open(patch_file, "w") as f:
                        subprocess.run(["git", "diff", "HEAD"], cwd=ws_dir, stdout=f, check=True)

                    if os.path.exists(patch_file) and os.path.getsize(patch_file) > 0:
                        subprocess.run(["git", "apply", str(patch_file)], cwd=main_dir, check=True)
                        logger.info(f"Synced {project} changes.")
                    else:
                        logger.info(f"No changes in {project} to sync.")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to sync {project} changes: {e}")
                finally:
                    if os.path.exists(patch_file):
                        os.remove(patch_file)

    def run_test_server(self) -> None:
        """Compiles and runs the server from the main project."""
        # First sync changes to main because 'runServer' runs on the main project
        self.apply_to_main()
        logger.info("Compiling and running server from main project...")
        self.run_gradle(":flux-server:runServer")

    def run_tests(self) -> None:
        """Syncs changes and runs Gradle tests for modified projects."""
        self.apply_to_main()

        logger.info("Running Gradle tests...")
        for project in ["flux-server", "flux-api"]:
            ws_dir = self.workspace_dir / project
            if not ws_dir.exists():
                continue

            res = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=ws_dir)
            if res.returncode != 0:
                logger.info(f"Running tests for {project}...")
                self.run_gradle(f":{project}:test")
            else:
                logger.info(f"No changes in {project}, skipping tests.")

    def rebuild_patches(self) -> None:
        """Syncs changes and triggers Gradle rebuild tasks for patches."""
        # First sync changes to main
        self.apply_to_main()

        logger.info("Rebuilding patches via Gradle...")
        # Check which projects have changes to determine which rebuild tasks to run
        for project in ["flux-server", "flux-api"]:
            ws_dir = self.workspace_dir / project
            if not ws_dir.exists():
                continue

            res = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=ws_dir)
            if res.returncode != 0:
                if project == "flux-server":
                    tasks = ["rebuildPaperServerPatches", "rebuildServerPatches", "rebuildMinecraftPatches"]
                else:
                    tasks = ["rebuildPaperApiPatches"]

                logger.info(f"Rebuilding {project} patches...")
                self.run_gradle(*tasks)
            else:
                logger.info(f"No changes in {project}, skipping rebuild.")

    def reset_workspace(self) -> None:
        """Discards all local changes in the workspace using Git reset and clean."""
        logger.info("Resetting workspace projects...")
        for project in ["flux-server", "flux-api"]:
            ws_dir = self.workspace_dir / project
            if ws_dir.exists():
                logger.info(f"Resetting {project}...")
                subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=ws_dir, check=True, capture_output=True)
                subprocess.run(["git", "clean", "-fd"], cwd=ws_dir, check=True, capture_output=True)
                logger.info(f"{project} reset.")

    def show_status(self) -> None:
        """Shows the initialization and modification status of workspace projects."""
        logger.info(f"Workspace root: {self.workspace_dir}")
        for project in ["flux-server", "flux-api"]:
            ws_dir = self.workspace_dir / project
            if ws_dir.exists():
                res = subprocess.run(["git", "status", "--short"], cwd=ws_dir, capture_output=True, text=True)
                changes = res.stdout.strip()
                if changes:
                    logger.info(f"Project {project}: Modified\n{changes}")
                else:
                    logger.info(f"Project {project}: Clean")
            else:
                logger.info(f"Project {project}: Not initialized")

    def list_patches(self) -> List[Path]:
        """Lists all available patches in the project directories."""
        patch_dirs = [
            self.root_dir / "flux-api" / "paper-patches",
            self.root_dir / "flux-server" / "minecraft-patches",
            self.root_dir / "flux-server" / "paper-patches"
        ]

        all_patches = []
        for pdir in patch_dirs:
            if pdir.exists():
                patches = sorted(list(pdir.glob("**/*.patch")))
                all_patches.extend(patches)

        if not all_patches:
            logger.info("No patches found in standard directories.")
            return []

        logger.info(f"Found {len(all_patches)} patches:")
        for idx, patch in enumerate(all_patches, 1):
            subject = "No subject"
            try:
                with open(patch, "r", errors="ignore") as f:
                    for line in f:
                        if line.startswith("Subject: [PATCH] "):
                            subject = line.replace("Subject: [PATCH] ", "").strip()
                            break
            except Exception:
                pass
            print(f"{idx:3}. {patch.relative_to(self.root_dir)} - {subject}")

        return all_patches

    def snapshot(self, name: str) -> None:
        """Creates a snapshot of the current workspace state using Git branches."""
        logger.info(f"Creating snapshot '{name}'...")
        for project in ["flux-server", "flux-api"]:
            ws_dir = self.workspace_dir / project
            if ws_dir.exists():
                # Delete branch if it exists to allow overwriting snapshots
                subprocess.run(["git", "branch", "-D", f"snapshot-{name}"], cwd=ws_dir, capture_output=True)
                res = subprocess.run(["git", "checkout", "-b", f"snapshot-{name}"], cwd=ws_dir, capture_output=True)
                if res.returncode == 0:
                    logger.info(f"Snapshot created for {project}")
                else:
                    logger.error(f"Failed to create snapshot for {project}: {res.stderr.decode().strip()}")

    def list_snapshots(self) -> None:
        """Lists all available snapshots in the workspace."""
        logger.info("Available snapshots:")
        snapshots = set()
        for project in ["flux-server", "flux-api"]:
            ws_dir = self.workspace_dir / project
            if ws_dir.exists():
                res = subprocess.run(["git", "branch", "--list", "snapshot-*"], cwd=ws_dir, capture_output=True, text=True)
                for line in res.stdout.splitlines():
                    name = line.strip().replace("* ", "").replace("snapshot-", "")
                    snapshots.add(name)

        if snapshots:
            for name in sorted(list(snapshots)):
                print(f" - {name}")
        else:
            logger.info("No snapshots found.")

    def clean_workspace(self) -> None:
        """Removes the entire workspace directory."""
        if self.workspace_dir.exists():
            logger.info(f"Removing workspace at {self.workspace_dir}...")
            shutil.rmtree(self.workspace_dir)
            logger.info("Workspace cleaned.")
        else:
            logger.info("No workspace found to clean.")

    def restore(self, name: str) -> None:
        """Restores the workspace state from a named snapshot."""
        logger.info(f"Restoring snapshot '{name}'...")
        for project in ["flux-server", "flux-api"]:
            ws_dir = self.workspace_dir / project
            if ws_dir.exists():
                res = subprocess.run(["git", "checkout", f"snapshot-{name}"], cwd=ws_dir, capture_output=True)
                if res.returncode == 0:
                    logger.info(f"Restored {project} to snapshot-{name}")
                else:
                    logger.error(f"Failed to restore {project} to snapshot-{name}: {res.stderr.decode().strip()}")

    def doctor(self) -> None:
        """Checks for missing or incorrect environment dependencies."""
        logger.info("Checking environment dependencies...")

        # Check Python
        logger.info(f"Python: {sys.version.split()[0]} - OK")

        # Check Git
        try:
            res = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
            logger.info(f"Git: {res.stdout.strip()} - OK")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("Git: Not found! Please install Git.")

        # Check Java
        try:
            res = subprocess.run(["java", "-version"], capture_output=True, text=True, stderr=subprocess.STDOUT)
            if "version \"21" in res.stdout or " 21." in res.stdout:
                logger.info(f"Java: 21 - OK")
            else:
                logger.warning(f"Java: Found but might not be version 21. Output: {res.stdout.splitlines()[0] if res.stdout else 'Unknown'}")
        except FileNotFoundError:
            logger.error("Java: Not found! Please install Java 21.")

        # Check Gradle executable
        if self.gradlew.exists():
            logger.info(f"Gradle wrapper: Found at {self.gradlew} - OK")
        else:
            logger.warning(f"Gradle wrapper: Not found at {self.gradlew}")

def main():
    parser = argparse.ArgumentParser(description="Flux Patcher Tool")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize workspace")
    init_parser.add_argument("--skip-gradle", action="store_true", help="Skip running Gradle applyAllPatches")

    apply_parser = subparsers.add_parser("apply", help="Apply patch(es)")
    apply_parser.add_argument("patches", nargs="*", help="Paths to patch files (interactive if empty)")
    apply_parser.add_argument("--dry-run", action="store_true", help="Don't apply, only check if it can be applied")

    subparsers.add_parser("diff", help="Show current changes")

    subparsers.add_parser("sync", help="Sync changes from workspace to main project")

    subparsers.add_parser("status", help="Show workspace status")

    subparsers.add_parser("list", help="List available patches in the project")

    snap_parser = subparsers.add_parser("snapshot", help="Create a workspace snapshot")
    snap_parser.add_argument("name", help="Name of the snapshot")

    restore_parser = subparsers.add_parser("restore", help="Restore a workspace snapshot")
    restore_parser.add_argument("name", help="Name of the snapshot to restore")

    subparsers.add_parser("snapshots", help="List all available snapshots")

    export_parser = subparsers.add_parser("export", help="Export changes as a patch")
    export_parser.add_argument("name", help="Name of the patch file")

    subparsers.add_parser("run", help="Run test server")

    subparsers.add_parser("test", help="Run Gradle tests for modified projects")

    subparsers.add_parser("rebuild", help="Sync changes and rebuild patches via Gradle")

    subparsers.add_parser("reset", help="Discard all changes in the workspace")

    subparsers.add_parser("clean", help="Remove workspace directory")

    subparsers.add_parser("doctor", help="Check environment dependencies")

    args = parser.parse_args()
    patcher = FluxPatcher()

    if args.command == "init":
        patcher.init_workspace(skip_gradle=args.skip_gradle)
    elif args.command == "apply":
        if not args.patches:
            patches = patcher.list_patches()
            if patches:
                try:
                    val = input("Select patch numbers to apply (comma separated, e.g. 1,3,5): ")
                    indices = [int(i.strip()) - 1 for i in val.split(",")]
                    selected = [str(patches[i]) for i in indices if 0 <= i < len(patches)]
                    patcher.apply_patch(selected, dry_run=args.dry_run)
                except ValueError:
                    logger.error("Invalid input.")
        else:
            patcher.apply_patch(args.patches, dry_run=args.dry_run)
    elif args.command == "diff":
        patcher.show_diff()
    elif args.command == "sync":
        patcher.apply_to_main()
    elif args.command == "status":
        patcher.show_status()
    elif args.command == "list":
        patcher.list_patches()
    elif args.command == "snapshot":
        patcher.snapshot(args.name)
    elif args.command == "restore":
        patcher.restore(args.name)
    elif args.command == "snapshots":
        patcher.list_snapshots()
    elif args.command == "export":
        patcher.export_patch(args.name)
    elif args.command == "run":
        patcher.run_test_server()
    elif args.command == "test":
        patcher.run_tests()
    elif args.command == "rebuild":
        patcher.rebuild_patches()
    elif args.command == "reset":
        patcher.reset_workspace()
    elif args.command == "clean":
        patcher.clean_workspace()
    elif args.command == "doctor":
        patcher.doctor()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
