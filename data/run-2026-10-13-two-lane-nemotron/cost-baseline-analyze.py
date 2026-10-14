#!/usr/bin/env python3
"""Analyze a local aggregate receipt; matplotlib is optional for the PNG plot.

uv run --with matplotlib cost-baseline-analyze.py cost-baseline-raw.json
Writes summary JSON and the exact SQL/PromQL appendix beside the input.
"""
import collections
import datetime as dt
import json
import math
from pathlib import Path
import statistics as st
import sys


def fit(x, y):
    xm, ym = st.mean(x), st.mean(y)
    xx = sum((v - xm) ** 2 for v in x)
    if len(x) < 3 or xx == 0:
        raise ValueError('At least three distinct traffic observations required')
    slope = sum((v-xm)*(w-ym) for v,w in zip(x,y)) / xx
    intercept = ym - slope*xm
    residual = sum((w-intercept-slope*v)**2 for v,w in zip(x,y))
    yy = sum((v-ym)**2 for v in y)
    sigma = math.sqrt(residual/(len(x)-2))
    return {'fixed': intercept, 'per_stream': slope, 'r2': 1-residual/yy if yy else None,
            'intercept_se': sigma*math.sqrt(1/len(x)+xm*xm/xx), 'slope_se': sigma/math.sqrt(xx), 'n':len(x)}


def main():
    p = Path(sys.argv[1]); d = json.loads(p.read_text()); r = d['results']
    daily = [z for z in r['unit_cost'] if z['settled']=='true' and int(z['runs'])==1]
    dates = {z['date'] for z in daily}
    model = fit([float(z['tx_hours']) for z in daily],[float(z['audio_cost']) for z in daily])
    by_component = collections.defaultdict(float)
    hourly_cost = collections.defaultdict(float)
    for z in r['billing']:
        if z['component'].startswith(('pool:backend-listen','pool:pusher','pool:parakeet','pool:nllb','pool:vad','pool:diarizer','gcs:audio')):
            hourly_cost[z['hour']] += float(z['net_cost'])
        if z['hour'][:10] in dates:
            by_component[z['component']] += float(z['net_cost'])/(24*len(dates))
    traffic = dict((int(t),float(v)) for t,v in r['listen']['data']['result'][0]['values'])
    joined = []
    for h, cost in hourly_cost.items():
        if h[:10] not in dates: continue
        t = int(dt.datetime.fromisoformat(h).replace(tzinfo=dt.timezone.utc).timestamp())
        if t in traffic: joined.append((traffic[t],cost))
    hourly_model = fit([x for x,y in joined],[y for x,y in joined])
    summary = {'billing_dates': sorted(dates), 'wall_clock_usd_per_hour':dict(by_component),
               'allocated_cost_per_tx_hour':sum(float(z['audio_cost']) for z in daily)/sum(float(z['tx_hours']) for z in daily),
               'daily_allocation_ols':model, 'hourly_prod_pool_and_storage_ols':hourly_model, 'fleet':{}, 'traffic':{}, 'latency':{}}
    for k in ('gpu_util','gpu_memory_mib','nodes','gpu_coverage'):
        summary['fleet'][k] = {}
        for z in r[k]['data']['result']:
            vals = [float(v) for t,v in z['values'] if math.isfinite(float(v))]
            summary['fleet'][k][z['metric']['pool']] = {'samples':len(vals),'min':min(vals),'mean':st.mean(vals),'max':max(vals)}
    for k in ('listen','pusher'):
        buckets = collections.defaultdict(list)
        for t,v in r[k]['data']['result'][0]['values']:
            buckets[dt.datetime.fromtimestamp(t,dt.timezone.utc).hour].append(float(v))
        shape = {h:st.mean(v) for h,v in buckets.items()}
        summary['traffic'][k] = shape
    for k in ('asr_service_rtf','window_post_p95','window_first_text_p95'):
        results = r[k]['data']['result']
        vals = [float(v) for z in results for t,v in z['values'] if math.isfinite(float(v))]
        summary['latency'][k] = {'samples':len(vals),'mean':st.mean(vals),'max':max(vals),'last':vals[-1]} if vals else {'samples':0}
    (p.parent/'cost-baseline-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    appendix = ['# Exact receipt queries', '', f"UTC window: {d['start']} inclusive to {d['end_exclusive']} exclusive. Source: `{d['source_sha']}`.", '',
                'Select `ro-prod`; all Kubernetes calls use `--context gke_based-hardware_us-central1_prod-omi-gke`. Prometheus uses the service proxy recorded below; hourly step is 3600 seconds.', '']
    for name,q in d['queries'].items():
        appendix += ['## '+name,'']
        if isinstance(q,dict): appendix += ['```json',json.dumps(q,indent=2),'```','']
        else: appendix += ['```sql' if name in ('unit_cost','allocated_components','audio_reconciliation','billing') else '```text',q,'```','']
    (p.parent/'cost-baseline-queries.md').write_text('\n'.join(appendix))
    print(json.dumps(summary,indent=2))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('Install matplotlib to regenerate the plot',file=sys.stderr);return
    fig,axes = plt.subplots(1,3,figsize=(15,4.5))
    x=[float(z['tx_hours']) for z in daily];y=[float(z['audio_cost']) for z in daily]
    axes[0].scatter(x,y)
    axes[0].plot([min(x),max(x)],[model['fixed']+model['per_stream']*v for v in [min(x),max(x)]],color='orange')
    axes[0].set(xlabel='Transcription hours/day',ylabel='Allocated audio cost $/day',title=f"Five settled days; R²={model['r2']:.2f}")
    axes[1].scatter([x for x,y in joined],[y for x,y in joined],s=12,alpha=.5)
    axes[1].set(xlabel='Listen connections (hourly snapshot)',ylabel='Production pools + audio GCS $/hour',title=f"Hourly cost vs streams; R²={hourly_model['r2']:.2f}")
    for k in ('listen','pusher'):
        shape=summary['traffic'][k];axes[2].plot(list(shape),list(shape.values()),label=k)
    axes[2].set(xlabel='UTC hour',ylabel='Mean concurrent connections',title='Seven-day traffic shape');axes[2].legend()
    fig.tight_layout();fig.savefig(p.parent/'cost-baseline-plot.png',dpi=150)


if __name__=='__main__':main()
