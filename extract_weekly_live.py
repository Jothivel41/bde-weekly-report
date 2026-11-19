"""Retrieve a bounded read-only CRM and Callyzer snapshot in IST."""
import argparse,json,time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
from zoneinfo import ZoneInfo
import requests
from dotenv import dotenv_values
P=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--start', default='2026-09-01')
parser.add_argument('--end', default=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat())
args=parser.parse_args()
V=dotenv_values(P/'.env'); IST=ZoneInfo('Asia/Kolkata')
from datetime import timedelta
START=datetime.fromisoformat(args.start).replace(tzinfo=IST)
END=datetime.fromisoformat(args.end).replace(tzinfo=IST)+timedelta(days=1)
assert 1 <= (END-START).days <= 180, 'Provide 1 to 180 calendar days'
QUERY_END=min(END,datetime.now(IST))
assert QUERY_END>START
OUT=P/('output/live_'+args.start+'_'+args.end)
ORG='00000000-0000-0000-0000-000000000002'
def save(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False))
def get_page(page):
 for attempt in range(3):
  try:
   r=requests.get(V['CRM_API_BASE_URL']+'/admin/leads',headers={'x-api-key':V['CRM_API_KEY']},params={'page':page,'limit':100},timeout=90,allow_redirects=False);r.raise_for_status();d=r.json()
   keep=('id','organizationId','assignedToId','assignedAt','createdAt','stage','stageEnteredAt','enrollmentId','enrollmentDate','activities','collectionAmounts')
   return d['pagination'],[{k:row.get(k) for k in keep} for row in d['data']]
  except requests.RequestException:
   if attempt==2:raise
   time.sleep(2)
def main():
 OUT.mkdir(exist_ok=True)
 for route, filename in [('admin/users','admin_users.json'),('admin/teams','admin_teams.json'),('admin/stages','admin_stages.json'),('admin/followups','followups_snapshot.json')]:
  r=requests.get(V['CRM_API_BASE_URL']+'/'+route,headers={'x-api-key':V['CRM_API_KEY']},params={'page':1,'limit':100},timeout=30,allow_redirects=False);r.raise_for_status();data=r.json()
  if isinstance(data,dict) and 'pagination' in data: assert len(data['data'])==data['pagination']['total']
  save(filename,data)
 r=requests.get(V['CALLYZER_API_BASE_URL'].rstrip('/')+'/employee/get',headers={'Authorization':'Bearer '+V['CALLYZER_API_TOKEN']},params={'page_no':1,'page_size':100},timeout=30,allow_redirects=False);r.raise_for_status();data=r.json()
 assert data['message']=='Success' and len(data['result'])==data['total_records'];save('callyzer_employees.json',data)
 time.sleep(2.1)
 if not (OUT/'leads_snapshot.json').exists():
  meta,rows=get_page(1);print('CRM pagination:',meta,flush=True)
  with ThreadPoolExecutor(max_workers=4) as pool:
   jobs={pool.submit(get_page,p):p for p in range(2,meta['totalPages']+1)}
   for f in as_completed(jobs):
    m,part=f.result();assert m['total']==meta['total'];rows.extend(part)
    if jobs[f]%10==0:print('CRM page',jobs[f],flush=True)
  assert len(rows)==meta['total'] and len({r['id'] for r in rows})==len(rows)
  assert all(r['organizationId']==ORG for r in rows)
  save('leads_snapshot.json',rows);save('leads_pagination.json',meta);print('CRM saved',len(rows),flush=True)
 if not (OUT/'calls_snapshot.json').exists():
  rows=[]; completions=[]; chunk_start=START
  chunks=OUT/'call_chunks';chunks.mkdir(exist_ok=True)
  with requests.Session() as session:
   session.headers.update({'Authorization':'Bearer '+V['CALLYZER_API_TOKEN'],'Accept':'application/x-ndjson'})
   while chunk_start<QUERY_END:
    chunk_end=min(chunk_start+timedelta(days=7),QUERY_END)
    path=chunks/(chunk_start.date().isoformat()+'.json')
    if path.exists():
     batch=json.loads(path.read_text())
    else:
     filters={'call_from':int(chunk_start.timestamp()),'call_to':int(chunk_end.timestamp())-1,'call_types':['Outgoing'],'call_method':'PhoneCall','call_mode':'Voice'}
     for attempt in range(3):
      part=[];terminator=None
      try:
       time.sleep(2.2)
       with session.post(V['CALLYZER_API_BASE_URL'].rstrip('/')+'/call-log/history/stream',json=filters,timeout=(10,90),stream=True,allow_redirects=False) as r:
        r.raise_for_status()
        for line in r.iter_lines(delimiter=b'\n'):
         if not line.strip():continue
         try:d=json.loads(line)
         except ValueError:
          (chunks/'malformed_response_line.bin').write_bytes(line)
          raise
         if d.get('type')=='END':terminator=d;break
         row=d['result']
         part.append({k:row.get(k) for k in ('id','emp_name','emp_code','emp_number','emp_country_code','emp_tags','client_number','client_country_code','call_date','call_time','duration','call_type')})
       assert terminator and terminator['message']=='Success' and terminator['total_records']==len(part)
       batch={'rows':part,'completion':terminator,'start':chunk_start.isoformat(),'end_exclusive':chunk_end.isoformat()}
       path.write_text(json.dumps(batch));break
      except (requests.RequestException,ValueError,AssertionError):
       if attempt==2:raise
       print('Retrying call batch',chunk_start.date(),flush=True);time.sleep(3)
    rows.extend(batch['rows']);completions.append(batch['completion'])
    print('Callyzer batch',chunk_start.date(),len(batch['rows']),flush=True)
    chunk_start=chunk_end
  assert len({r['id'] for r in rows})==len(rows)
  save('calls_snapshot.json',rows);save('calls_stream_completion.json',{'batches':completions,'total_records':len(rows)});print('Callyzer saved',len(rows),flush=True)
 save('extracted_at.json',{'at':datetime.now(IST).isoformat(),'start':START.isoformat(),'end_exclusive':QUERY_END.isoformat()})
if __name__=='__main__':main()
