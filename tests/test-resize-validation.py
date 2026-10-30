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

    def test_resize_zone_under_panel_sends_no_press(self):
        # A GTK window whose bottom edge is 4 px above a floating panel: its resize zone
        # (the shadow below the frame) is under the panel's window, so nothing may be pressed.
        from types import SimpleNamespace
        w = {'id': 'probe', 'normal': True, 'maximized': False, 'minimized': False, 'fullscreen': False,
             'decorated': False, 'resizing': False, 'moving': False, 'output': 'DP-1',
             'x': 100, 'y': 4, 'width': 800, 'height': 906,
             'client': {'x': 100, 'y': 4, 'width': 800, 'height': 906},
             'buffer': {'x': 75, 'y': -21, 'width': 850, 'height': 956},
             'screen': {'x': 0, 'y': 0, 'width': 1700, 'height': 960},
             'area': {'x': 0, 'y': 0, 'width': 1700, 'height': 914},
             'min_size': {'width': 400, 'height': 250}}
        panel = {'id': 'panel', 'normal': False, 'dock': True, 'desktop': False, 'class': 'plasmashell'}
        buttons, closed = [], []
        fake = SimpleNamespace(move=lambda *p: None, button=lambda *b: buttons.append(b), close=lambda: closed.append(True))
        def run(action, *args, **kwargs):
            if action == 'info': return {'ok': True, 'windows': [w]}
            if action == 'pointer': return {'ok': True, 'pointer': {'x': 1, 'y': 1}}
            if action == 'raise': return {'ok': True, 'windows': [w]}
            if action == 'at':
                y = kwargs.get('args', args[1] if len(args) > 1 else None)[1]
                return {'ok': True, 'windows': [panel] if y >= 898 else [w]}
            self.fail('unexpected action ' + action)
        out = io.StringIO()
        with patch.dict(sys.modules, {'input': SimpleNamespace(Input=lambda: fake, keycode=lambda k: 0)}), \
                patch.object(window, 'run', side_effect=run), patch.object(window, 'wait_stable', return_value=[w]), \
                patch.object(window.time, 'sleep'), contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit):
                window.drag_resize(['id:probe', '800', '800', '--edge', 'bottom'])
        self.assertIn('under a panel', out.getvalue())
        self.assertEqual(sum(down for _, down in buttons), 0)
        self.assertEqual(closed, [True])


class MoveValidation(unittest.TestCase):
    def sample(self):
        return {'id': 'probe', 'normal': True, 'maximized': False, 'minimized': False,
                'fullscreen': False, 'decorated': True, 'client': {'y': 130},
                'x': 100, 'y': 100, 'width': 400, 'height': 300, 'moving': False, 'resizing': False}

    def test_bad_move_arguments_never_contact_desktop(self):
        for args in [[], ['id:a','100','100'], ['id:a','100','100','--grab','10'],
                     ['id:a','nan','100','--grab','10','10'],
                     ['id:a','100','100','--grab','10','inf'],
                     ['id:a','100','100','--grab','10','10','--typo']]:
            with self.subTest(args=args), patch.object(window,'run',side_effect=AssertionError('desktop contacted')):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                    window.drag_move(args)

    def test_refuses_ambiguous_or_maximized_window(self):
        w=self.sample()
        for wins in [[w,w],[dict(w,maximized=True)]]:
            with patch.object(window,'run',return_value={'ok':True,'windows':wins}):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                    window.drag_move(['id:probe','200','200','--grab','100','15'])

    def test_refuses_grab_in_content(self):
        with patch.object(window,'run',return_value={'ok':True,'windows':[self.sample()]}):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                window.drag_move(['id:probe','200','200','--grab','100','100'])

    def test_offscreen_destination_is_refused_before_input(self):
        def run(action,*args,**kwargs):
            if action=='info': return {'ok':True,'windows':[self.sample()]}
            if action=='areas': return {'ok':True,'outputs':[{'area':{'x':0,'y':0,'width':1000,'height':800}}]}
            self.fail('unexpected desktop action '+action)
        with patch.object(window,'run',side_effect=run):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                window.drag_move(['id:probe','950','200','--grab','100','15'])

    def test_blocked_grab_sends_no_press_and_cleans_up(self):
        self.exercise_grab(blocked=True)

    def test_failed_move_releases_button_without_retry(self):
        self.exercise_grab(blocked=False)

    def test_pointer_interference_sends_no_press(self):
        self.exercise_grab(blocked=False, changed_pointer=True)

    def exercise_grab(self, blocked, changed_pointer=False):
        from types import SimpleNamespace
        buttons,moves,closed=[],[],[]
        fake=SimpleNamespace(move=lambda *p:moves.append(p),
                             button=lambda *b:buttons.append(b),close=lambda:closed.append(True))
        def run(action,*args,**kwargs):
            if action=='info': return {'ok':True,'windows':[self.sample()]}
            if action=='areas': return {'ok':True,'outputs':[{'area':{'x':0,'y':0,'width':1000,'height':800}}]}
            if action=='pointer':
                point=moves[-1] if moves and not changed_pointer else (11,12)
                return {'ok':True,'pointer':dict(zip(('x','y'),point))}
            if action=='at': return {'ok':True,'windows':[{'id':'other' if blocked else 'probe'}]}
            self.fail('unexpected action '+action)
        with patch.dict(sys.modules,{'input':SimpleNamespace(Input=lambda:fake)}), patch.object(window,'run',side_effect=run), patch.object(window.time,'sleep'):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                window.drag_move(['id:probe','200','200','--grab','100','15','--no-raise'])
        self.assertEqual(sum(down for _,down in buttons),0 if blocked or changed_pointer else 1)
        self.assertEqual(buttons[-1],('left',False))
        self.assertEqual(moves[-1],(11,12))
        self.assertEqual(closed,[True])


if __name__ == '__main__':
    unittest.main()
