"""Headless regression tests. Run: /usr/bin/python3 -s tests/test-resize-validation.py (distro PyGObject required).
Expected: all tests pass; no connection to the compositor or input synthesis.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

window = load('window', ROOT / 'scripts/kde/window.py')
input_module = load('lcu_input', ROOT / 'scripts/input.py')

class ResizeValidation(unittest.TestCase):
    def test_rejects_invalid_arguments_before_contacting_desktop(self):
        invalid = [
            ['class:probe', '0', '100'], ['class:probe', 'nan', '100'],
            ['class:probe', '100', 'inf'], ['class:probe', '100', '100', '--step', '0'],
            ['class:probe', '100', '100', '--step', '-1'],
            ['class:probe', '100', '100', '--step', '9'],
            ['class:probe', '100', '100', '--step', 'bad'],
            ['class:probe', '100', '100', '--step'],
            ['class:probe', '100', '100', '--edge'],
            ['class:probe', '100', '100', '--edge', 'middle'],
            ['class:probe', '100', '100', '--typo'],
        ]
        with patch.object(window, 'run', side_effect=AssertionError('desktop contacted')):
            for args in invalid:
                with self.subTest(args=args), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        window.drag_resize(args)
                    self.assertEqual(error.exception.code, 1)

    def test_ambiguous_window_match_is_rejected(self):
        with patch.object(window, 'run', return_value={'ok': True, 'windows': [{}, {}]}), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                window.drag_resize(['class:probe', '100', '100'])

    def test_drag_step_bound_and_release(self):
        for step in [0.5, 1, 3, 8]:
            for end in [(20, 17), (-17, -20), (0, 0)]:
                moves, buttons = [], []
                fake = input_module.Input.__new__(input_module.Input)
                fake.move = lambda x,y: moves.append((x,y))
                fake.button = lambda name,down: buttons.append((name,down))
                with patch.object(input_module.time, 'sleep'):
                    fake.drag(0, 0, *end, step=step)
                self.assertEqual(moves[-1], end)
                self.assertEqual(buttons, [('left', True), ('left', False)])
                for a,b in zip(moves, moves[1:]):
                    self.assertLessEqual(max(abs(b[0]-a[0]),abs(b[1]-a[1])), step+1e-9)

    def test_invalid_drag_step_sends_no_input(self):
        fake = input_module.Input.__new__(input_module.Input)
        fake.move = lambda *a: self.fail('input sent')
        for step in [0, -1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                fake.drag(0,0,10,10,step=step)

if __name__ == '__main__':
    unittest.main()
