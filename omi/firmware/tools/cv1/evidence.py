#!/usr/bin/env python3
"""Offline evidence import, replay and release comparison. Never opens devices."""
import argparse,base64,json,re
from pathlib import Path
import bench


def import_capture(output,kind,metadata,raw=None):
 if kind not in ('uart_capture','debug_capture'):raise ValueError('unsupported capture kind')
 root=Path(output);root.mkdir(parents=True,exist_ok=False)
 original=Path(metadata);value=json.loads(original.read_text())
 if kind=='uart_capture':
  for field in ('start','end','bytes','status','errors','port_closed','transmitted_bytes'):
   if field not in value:raise ValueError('missing UART metadata '+field)
  if not value['end'] or value['port_closed'] is not True:raise ValueError('capture not finalized/closed')
 else:
  for field in ('started_at','completed_at','target','operations','status','cleanup_verified'):
   if field not in value:raise ValueError('missing debug receipt field '+field)
  if not value['completed_at'] or value['cleanup_verified'] is not True:raise ValueError('debug capture not finalized/cleaned up')
 sources=[]
 for name,source in [('metadata.json',original),('raw.bin',Path(raw) if raw else None)]:
  if source is None:continue
  before=bench.digest(source);target=root/name
  with source.open('rb') as inp,target.open('xb') as out:
   for block in iter(lambda:inp.read(1024*1024),b''):out.write(block)
  if bench.digest(target)!=before or bench.digest(source)!=before:raise ValueError('capture changed during import')
  sources.append({'snapshot':name,'original_path':str(source.resolve()),'sha256':before,'size_bytes':target.stat().st_size})
 if kind=='uart_capture' and raw is not None and (root/'raw.bin').stat().st_size!=value['bytes']:raise ValueError('UART raw/metadata byte count mismatch')
 record={'schema_version':1,'provenance':'operator_supplied','evidence_type':kind,'sources':sources,'metadata':value,
         'timing_model':'host receipt timestamps only; raw byte timing unknown','hardware_access':False}
 bench.save(root/'capture.json',record,exclusive=True);validate_capture(root/'capture.json')
 return root/'capture.json'


def validate_capture(path):
 path=Path(path);record=json.loads(path.read_text())
 if record.get('schema_version')!=1 or record.get('provenance')!='operator_supplied' or record.get('evidence_type') not in ('uart_capture','debug_capture'):raise ValueError('not an actual capture envelope')
 if not any(source['snapshot']=='metadata.json' for source in record['sources']):raise ValueError('metadata.json must be a listed hashed capture source')
 for source in record['sources']:
  file=(path.parent/source['snapshot']).resolve(strict=True)
  if file.parent!=path.parent.resolve() or bench.digest(file)!=source['sha256'] or file.stat().st_size!=source['size_bytes']:raise ValueError('capture file hash/path mismatch')
 if json.loads((path.parent/'metadata.json').read_text())!=record['metadata']:raise ValueError('capture metadata changed')
 if record['evidence_type']=='uart_capture' and any(source['snapshot']=='raw.bin' for source in record['sources']):
  declared=record['metadata'].get('bytes') if type(record['metadata']) is dict else None
  if type(declared) is not int or (path.parent/'raw.bin').stat().st_size!=declared:raise ValueError('UART raw/metadata byte count mismatch')
 return record


def replay_uart(path,chunk_size=64):
 if not 1<=chunk_size<=65536:raise ValueError('chunk size out of bounds')
 record=validate_capture(path)
 if record['evidence_type']!='uart_capture':raise ValueError('UART evidence required')
 raw=Path(path).parent/'raw.bin'
 if not any(x['snapshot']=='raw.bin' for x in record['sources']):raise ValueError('raw bytes not available')
 offset=0
 with raw.open('rb') as stream:
  for block in iter(lambda:stream.read(chunk_size),b''):
   yield {'provenance':'operator_supplied','offset':offset,'data_base64':base64.b64encode(block).decode(),
          'timing':'unspecified; replay chunk boundaries are synthetic, not original UART timing'}
   offset+=len(block)


def config(path):
 result={}
 for line in Path(path).read_text(errors='replace').splitlines():
  m=re.fullmatch(r'(CONFIG_[A-Za-z0-9_]+)=(.*)',line)
  if m:result[m[1]]=m[2]
  m=re.fullmatch(r'# (CONFIG_[A-Za-z0-9_]+) is not set',line)
  if m:result[m[1]]='n'
 return result


def compare(baseline,candidate):
 b=bench.verify_manifest(baseline);c=bench.verify_manifest(candidate)
 if b['role']!='baseline' or c['role']!='candidate':raise ValueError('baseline/candidate roles required')
 if c['baseline']['sha256']!=bench.digest(baseline):raise ValueError('candidate references a different baseline')
 # Use artifact basenames, refusing ambiguous duplicates rather than guessing roles.
 def items(manifest):
  out={}
  for entry in manifest['artifacts']:
   source=Path(entry['source'])
   name=(source.parent.parent.name+'/.config') if source.name=='.config' else source.name
   if name in out:raise ValueError('duplicate artifact basename '+name)
   out[name]=entry
  return out
 bi,ci=items(b),items(c);changes=[];configs={}
 for name in sorted(bi.keys()|ci.keys()):
  old,new=bi.get(name),ci.get(name)
  changes.append({'artifact':name,'state':'added' if old is None else 'removed' if new is None else 'same' if old['sha256']==new['sha256'] else 'changed',
                  'baseline_sha256':old['sha256'] if old else None,'candidate_sha256':new['sha256'] if new else None,
                  'baseline_ranges':old.get('address_ranges') if old else None,'candidate_ranges':new.get('address_ranges') if new else None})
  if old and new and (name.endswith('.conf') or name.endswith('/.config') or name=='.config'):
   before=config(Path(baseline).parent/old['snapshot']);after=config(Path(candidate).parent/new['snapshot'])
   configs[name]={key:{'baseline':before.get(key),'candidate':after.get(key)} for key in sorted(before.keys()|after.keys()) if before.get(key)!=after.get(key)}
 return {'schema_version':1,'layer':'offline artifact/config comparison','hardware_acceptance':'not_measured',
         'baseline_manifest_sha256':bench.digest(baseline),'candidate_manifest_sha256':bench.digest(candidate),
         'artifact_changes':changes,'config_changes':configs,'release_approved':False,
         'required_followup':['generated partition/range and bootloader/storage review','known installed baseline and qualified rollback','same scoped real-device observations for both versions']}


def replay_ble(index):
 path=Path(index);summaries=[]
 for record in json.loads(path.read_text()):
  bench.validate_corpus(record,path.parent)
  if record['provenance']=='synthetic':continue
  value=record['observation']
  results=value.get('results',[])
  if type(results) is not list or any(type(x) is not dict or type(x.get('peripheral_id')) is not str or not x['peripheral_id'] for x in results):raise ValueError('receipt results require non-empty string peripheral_id entries')
  count=value.get('match_count')
  if type(count) is not int or count!=len(results):raise ValueError('match_count inconsistent with listed results')
  summaries.append({'provenance':'operator_supplied','run_id':value.get('run_id'),'scan_started_at':value.get('scan_started_at'),
   'completed_at':value.get('completed_at'),'authorization':value.get('authorization'),'state':value.get('state'),
   'matching_ids':sorted(x['peripheral_id'] for x in results),
   'match_count':count,'source_sha256':record['source']['sha256']})
 return {'schema_version':1,'layer':'offline receipt replay','device_emulation':False,'observations':summaries,
         'limitations':['receipts are supplied by the operator; this tool cannot prove a device produced them','no packet timing reconstruction','no GATT/audio/UART behavior inferred','power-state labels come from operator history, not radio data']}


def main():
 p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
 q=s.add_parser('import-capture');q.add_argument('--output',required=True);q.add_argument('--kind',choices=['uart_capture','debug_capture'],required=True);q.add_argument('--metadata',required=True);q.add_argument('--raw')
 q=s.add_parser('replay-uart');q.add_argument('capture')
 q=s.add_parser('replay-ble');q.add_argument('index')
 q=s.add_parser('compare');q.add_argument('--baseline',required=True);q.add_argument('--candidate',required=True)
 a=p.parse_args()
 if a.action=='import-capture':print(import_capture(a.output,a.kind,a.metadata,a.raw))
 elif a.action=='replay-uart':
  for event in replay_uart(a.capture):print(json.dumps(event,sort_keys=True))
 elif a.action=='replay-ble':print(json.dumps(replay_ble(a.index),sort_keys=True,indent=2))
 else:print(json.dumps(compare(a.baseline,a.candidate),sort_keys=True,indent=2))
if __name__=='__main__':main()
