"""Four-way comparison on the user's 26 captures: ungraded, starter, trained v3, candidate(s)."""
import sys, glob, os, numpy as np
from PIL import Image
from parr.artifacts import Artifacts
from parr.pipeline import Pipeline
from parr.grain import GrainParams
from parr.color import srgb_to_oklab, oklab_to_lch
A="/Users/george.babanau/2026-09-07"; B="/Users/george.babanau/2026-09-07-trained-comparison-v3"
ids=sorted(os.path.basename(p)[:6] for p in glob.glob(A+"/*_ungraded.jpg"))
def stats(px):
    lab=srgb_to_oklab(px); lch=oklab_to_lch(lab); L,C=lab[:,0],lch[:,1]
    return dict(p5=np.percentile(L,5), p50=np.median(L), p95=np.percentile(L,95), std=L.std(),
                C=C.mean(), Ccol=C[C>0.06].mean() if (C>0.06).any() else np.nan,
                sat=(C>0.12).mean(), neut=np.hypot(*lab[C<0.03,1:].mean(0)) if (C<0.03).any() else np.nan)
def load(p,step=4): return np.asarray(Image.open(p).convert("RGB"))[::step,::step].reshape(-1,3).astype(np.float32)/255
rows={}
for name,pat in (("ungraded",A+"/{}_ungraded.jpg"),("starter",A+"/{}_parr.jpg"),("trained v3",B+"/{}_ungraded_parr.jpg")):
    acc=[stats(load(pat.format(i))) for i in ids if os.path.exists(pat.format(i))]
    rows[name]={k:np.nanmean([a[k] for a in acc]) for k in acc[0]}
for d in sys.argv[1:]:
    a=Artifacts.load(d); a.grain=GrainParams(enabled=False); pipe=Pipeline(a)
    acc=[]
    for i in ids:
        u=np.asarray(Image.open(f"{A}/{i}_ungraded.jpg").convert("RGB"))
        g=pipe.process(u); g=g[0] if isinstance(g,tuple) else g
        acc.append(stats(g[::4,::4].reshape(-1,3).astype(np.float32)/255))
    rows[os.path.basename(d.rstrip("/"))]={k:np.nanmean([x[k] for x in acc]) for k in acc[0]}
print(f"{'':16s} {'p5 L':>6s} {'med':>5s} {'p95':>5s} {'stdL':>5s} | {'chroma':>6s} {'colours':>7s} {'>0.12':>6s} {'neutral':>7s}")
for k,v in rows.items():
    print(f"{k:16s} {v['p5']:6.3f} {v['p50']:5.3f} {v['p95']:5.3f} {v['std']:5.3f} | {v['C']:6.4f} {v['Ccol']:7.4f} {100*v['sat']:5.1f}% {v['neut']:7.4f}")
print(f"{'-- Ektar ref':16s} {0.187:6.3f} {0.542:5.3f} {0.908:5.3f} {0.246:5.3f} | {0.0364:6.4f} {0.0863:7.4f} {2.6:5.1f}% {0.0074:7.4f}")
print(f"{'-- Velvia ref':16s} {0.183:6.3f} {0.475:5.3f} {0.850:5.3f} {0.219:5.3f} | {0.0497:6.4f} {0.0920:7.4f} {7.3:5.1f}% {0.0100:7.4f}")
