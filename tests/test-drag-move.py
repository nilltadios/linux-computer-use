"""uv run --python 3.15 tests/test-drag-move.py MATCH --grab GX GY --output NEW_DIR.
Requires the existing, user-authorized test window. Moves it physically in eight
directions, plus a tiny drag and a no-op; checks target, unchanged size, moving
flag and restored pointer. Restores original geometry in finally. Expected exit 0.
Inspect a fresh screenshot before choosing the non-interactive header grab point.
--smoke instead tests a tiny move, a tiny move near a screen edge, and a no-op.
"""
import argparse,json,math,subprocess,sys,tempfile,time
from pathlib import Path
L=str(Path(__file__).resolve().parents[1]/'lcu')
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('match')
p.add_argument('--grab',nargs=2,type=float,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--smoke',action='store_true')
args=p.parse_args()
OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=False);rows=[]
def call(argv,name,allowed=(0,)):
    r=subprocess.run([L,*map(str,argv)],capture_output=True,text=True,timeout=120)
    (OUT/f'{name}.json').write_text(json.dumps({'command':[L,*map(str,argv)],'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2))
    if r.returncode not in allowed: raise RuntimeError(f'{name}: {r.returncode} {r.stdout} {r.stderr}')
    return json.loads(r.stdout),r.returncode
wins,_=call(['window','info',args.match],'original')
assert len(wins)==1
w=wins[0];m='id:'+w['id'];a=w['area']
assert not any(w[k] for k in ['maximized','minimized','fullscreen'])
bx=math.floor(a['x']+(a['width']-w['width'])/2)
by=math.floor(a['y']+(a['height']-w['height'])/2)
gx,gy=args.grab
cases=[('right',90,0),('left',-90,0),('down',0,70),('up',0,-70),('down-right',90,70),('down-left',-90,70),('up-right',90,-70),('up-left',-90,-70),('tiny',2,-3),('no-op',0,0)]
if args.smoke:
    cases=[('tiny',2,-3),('near-left-tiny',-2,0),('no-op',0,0)]
print('Output:',OUT,flush=True)
try:
    for label,dx,dy in cases:
        start_x=a['x']+18 if label=='near-left-tiny' else bx
        call(['window','geometry',m,start_x,by,w['width'],w['height']],label+'-reset')
        state,_=call(['window','wait-stable',m],label+'-stable');before=state[0]
        call(['capture','shot',OUT/f'{label}-before.png','--window',m],label+'-capture')
        pointer,_=call(['window','pointer'],label+'-pointer-before')
        tx,ty=before['x']+dx,before['y']+dy
        r,rc=call(['window','drag-move',m,tx,ty,'--grab',gx,gy],label+'-drag',allowed=(0,1,3))
        actual,_=call(['window','info',m],label+'-after');actual=actual[0]
        after_pointer,_=call(['window','pointer'],label+'-pointer-after')
        position=max(abs(actual['x']-tx),abs(actual['y']-ty))<1
        size=all(abs(actual[k]-before[k])<1 for k in ['width','height'])
        restored=max(abs(after_pointer[k]-pointer[k]) for k in ['x','y'])<1
        moving=r.get('move_started',False) if label!='no-op' else r.get('changed') is False
        ok=rc==0 and position and size and restored and moving
        row={'match':args.match,'case':label,'passed':ok,'exit':rc,'target':[tx,ty],'actual':[actual['x'],actual['y']],'size_preserved':size,'pointer_restored':restored,'move_started':r.get('move_started',False),'move_check_passed':moving}
        rows.append(row);(OUT/'results.json').write_text(json.dumps(rows,indent=2))
        print(('PASS' if ok else 'FAIL'),label,json.dumps(row),flush=True)
        if rc==1: break
finally:
    call(['window','geometry',m,w['x'],w['y'],w['width'],w['height']],'restore')
    final,_=call(['window','wait-stable',m],'restore-stable')
    restored=all(abs(final[0][k]-w[k])<1 for k in ['x','y','width','height'])
    summary={'passed':sum(r['passed'] for r in rows),'operations':len(rows),'expected':len(cases),'original_restored':restored,'all_passed':len(rows)==len(cases) and all(r['passed'] for r in rows) and restored}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    print('Summary:',json.dumps(summary),flush=True)
sys.exit(0 if summary['all_passed'] else 1)
