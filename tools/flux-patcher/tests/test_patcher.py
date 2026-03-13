import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
from pathlib import Path
import sys

# Add the tool directory to sys.path to import FluxPatcher
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from patcher import FluxPatcher

class TestFluxPatcher(unittest.TestCase):
    def setUp(self):
        with patch('patcher.FluxPatcher.find_root', return_value=Path('/mock/root')):
            self.patcher = FluxPatcher()
        self.patcher.workspace_dir = Path('/mock/root/.flux-workspace')

    @patch('subprocess.run')
    def test_run_gradle(self, mock_run):
        self.patcher.run_gradle('testTask')
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn('gradlew', args[0])
        self.assertIn('testTask', args)

    @patch('shutil.rmtree')
    @patch('shutil.copytree')
    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.iterdir', return_value=[Path('file')])
    @patch('subprocess.run')
    def test_init_workspace(self, mock_run, mock_exists, mock_mkdir, mock_iterdir, mock_copy, mock_rmtree):
        # Mock run_gradle to return success
        with patch('patcher.FluxPatcher.run_gradle', return_value=MagicMock(returncode=0)):
            self.patcher.init_workspace()

        self.assertTrue(mock_rmtree.called)
        self.assertTrue(mock_mkdir.called)
        self.assertEqual(mock_copy.call_count, 2) # flux-server and flux-api

    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.read_text', return_value='diff --git a/net/minecraft/Server.java')
    @patch('subprocess.run')
    def test_apply_patch_server(self, mock_run, mock_read, mock_exists):
        self.patcher.apply_patch(['/mock/test.patch'])
        mock_run.assert_called()
        # Check if it tried to apply to flux-server
        cwd = mock_run.call_args[1].get('cwd')
        self.assertEqual(cwd, self.patcher.workspace_dir / 'flux-server')

    @patch('pathlib.Path.glob', return_value=[Path('/mock/root/patch1.patch')])
    @patch('pathlib.Path.exists', return_value=True)
    def test_list_patches(self, mock_exists, mock_glob):
        patches = self.patcher.list_patches()
        self.assertEqual(len(patches), 3) # One for each directory

    @patch('subprocess.run')
    def test_snapshot(self, mock_run):
        mock_run.return_value.returncode = 0
        with patch('pathlib.Path.exists', return_value=True):
            self.patcher.snapshot('test')
        self.assertTrue(mock_run.called)
        # Should call branch -D then checkout -b
        calls = [call[0][0] for call in mock_run.call_args_list]
        flattened_calls = [item for sublist in calls for item in sublist]
        self.assertIn('branch', flattened_calls)
        self.assertIn('checkout', flattened_calls)

    @patch('subprocess.run')
    def test_restore(self, mock_run):
        mock_run.return_value.returncode = 0
        with patch('pathlib.Path.exists', return_value=True):
            self.patcher.restore('test')
        self.assertTrue(mock_run.called)
        self.assertIn('checkout', mock_run.call_args[0][0])

    @patch('shutil.rmtree')
    @patch('pathlib.Path.exists', return_value=True)
    def test_clean_workspace(self, mock_exists, mock_rmtree):
        self.patcher.clean_workspace()
        self.assertTrue(mock_rmtree.called)

    @patch('subprocess.run')
    @patch('os.path.getsize', return_value=100)
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.remove')
    def test_apply_to_main(self, mock_remove, mock_file, mock_exists, mock_getsize, mock_run):
        # Mock workspace and main directories existing
        with patch('pathlib.Path.exists', return_value=True):
            self.patcher.apply_to_main()

        self.assertTrue(mock_run.called)
        # Verify it called 'git apply'
        calls = [call[0][0] for call in mock_run.call_args_list]
        flattened_calls = [item for sublist in calls for item in sublist]
        self.assertIn('apply', flattened_calls)

if __name__ == '__main__':
    unittest.main()
