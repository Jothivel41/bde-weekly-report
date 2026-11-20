"""Normalize the verified local API snapshot for the requested 15-person roster."""
import argparse,json
from collections import Counter
from datetime import datetime,timedelta,date
from pathlib import Path
from zoneinfo import ZoneInfo
from callyzer import call_row
P=Path(__file__).resolve().parent; IST=ZoneInfo('Asia/Kolkata')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--start', default='2026-09-01')
parser.add_argument('--end', default=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat())
args=parser.parse_args()
O=P/('output/live_'+args.start+'_'+args.end)
ORG='00000000-0000-0000-0000-000000000002'; START=date.fromisoformat(args.start); END=date.fromisoformat(args.end)
def read(name):return json.loads((O/name).read_text())
def phone(value):return ''.join(x for x in str(value or '') if x.isdigit())[-10:]
def day(value):
 if not value:return None
 d=datetime.fromisoformat(value.replace('Z','+00:00'))
 assert d.tzinfo is not None
 return d.astimezone(IST).date()
def in_week(value):return bool(value and START<=day(value)<=END)
def main():
 users=read('admin_users.json')['data']; crm=read('leads_snapshot.json'); raw_calls=read('calls_snapshot.json'); emps=read('callyzer_employees.json')
 assert len(emps['result'])==emps['total_records']
 hierarchy=json.loads((P/'team_hierarchy.json').read_text())
 aliases={'Susmitha':'Sushmitha','Ilayaraja':'Ilayaraja'}
 cally_aliases={'Sushmitha G':'Susmitha','Ilayaraja R':'ilaya','Lalith Kumar':'Lalith','Abbas Mohammed':'abbas'}
 members=[]; mappings=[]; employee_map={}
 for group in hierarchy['teams']:
  for name in group['bdes']:
   prefix=aliases.get(name,name).lower()
   matches=[u for u in users if u.get('organizationId')==ORG and u.get('role')=='sales_person' and u['name'].lower().startswith(prefix)]
   assert len(matches)==1,(name,len(matches));u=matches[0]
   phones={phone(u.get(k)) for k in ('mobile','alternateMobile')}-{''}
   matched=[e for e in emps['result'] if phone(e['emp_number']) in phones]
   method='CRM phone match'
   if not matched:
    alias=cally_aliases.get(u['name'],u['name'].split()[0]).lower()
    matched=[e for e in emps['result'] if e['emp_name'].lower()==alias]
    method='Unique name match; CRM phone differs'
   assert len(matched)==1,(name,'employee match',len(matched))
   e=matched[0]; registered=str(e['emp_country_code'])+'-'+str(e['emp_number'])
   employee_map[str(e['emp_country_code'])+str(e['emp_number'])]=(registered,u['id'])
   members.append({'id':u['id'],'name':u['name'],'vertical':group['vertical'],'team_lead':group['team_lead'] or '', 'callyzer_number':registered})
   mappings.append({'crm_name':u['name'],'callyzer_name':e['emp_name'],'basis':method})
 ids={u['id'] for u in members}; assert len(ids)==15
 arrivals=[]
 for row in crm:
  if row['assignedToId'] not in ids:
   continue
  if in_week(row['createdAt']):
   arrivals.append({'arrival_id':row['id'] + ':created','bde_id':row['assignedToId'],'arrived_at':row['createdAt']})
  for activity in row.get('activities') or []:
   if activity.get('type') == 'lead_reactivated' and in_week(activity.get('createdAt')):
    arrivals.append({'arrival_id':row['id'] + ':reactivated:' + activity['createdAt'],
                     'bde_id':row['assignedToId'],'arrived_at':activity['createdAt']})
 leads=[{'lead_id':r['id'],'bde_id':r['assignedToId'],'received_at':r['assignedAt'],'stage':r['stage'] or ''} for r in crm if r['assignedToId'] in ids and in_week(r['assignedAt'])]
 calls=[]
 for r in raw_calls:
  if str(r['emp_country_code'])+str(r['emp_number']) not in employee_map:continue
  calls.append(call_row(r,employee_map,IST,START,END))
 calls=[r for r in calls if r]
 assert len({r['call_id'] for r in calls})==len(calls)
 completed=Counter((r['assignedToId'],day(r['completedAt']).isoformat()) for r in read('followups_snapshot.json')['data'] if r.get('assignedToId') in ids and r.get('status')=='completed' and in_week(r.get('completedAt')))
 enrolled=Counter((r['assignedToId'],day(r['enrollmentDate']).isoformat()) for r in crm if r['assignedToId'] in ids and r.get('stage') == 'enrolled' and in_week(r['enrollmentDate']))
 revenue_by_day = read('revenue_daily.json')
 revenue_by_bde_day = {}
 for day_key, payload in revenue_by_day.items():
  for row in payload['bde']:
   if row['label'] in {member['name'] for member in members}:
    revenue_by_bde_day[(row['label'], day_key)] = row
 daily=[]
 for u in members:
  for n in range((END-START).days+1):
   dt=(START+timedelta(days=n)).isoformat();k=(u['id'],dt)
   financial = revenue_by_bde_day.get((u['name'], dt), {})
   daily.append(dict(bde_id=u['id'],date=dt,followups=completed[k],pending=None,
                     stageMoves=None,enrolled=enrolled[k],
                     sales=int(financial.get('sales', 0)),
                     saleValue=str(financial.get('saleValue', 0)),
                     revenue=str(financial.get('collections', 0))))
 name_matches=[r['crm_name'] for r in mappings if r['basis'].startswith('Unique')]
 notes=[
  f'Live API snapshot for {START:%d %b %Y}–{END:%d %b %Y} (IST), through the extraction time, Org 02. Scope: the 15 BDEs named by you; other CRM staff, managers and team leads are excluded from totals.',
  'Leads arrived is an arrival cohort: CRM creations plus lead_reactivated activities in the selected IST date range. Leads received is assignment-date based and can include leads at any current stage. Both use current assignedToId because historical ownership is unavailable.',
  'Calls are time-based: recorded outgoing PhoneCall / Voice calls that occurred in the selected IST date range. Each call ID counts once; unique contacts are deduplicated within the selected view. Connected means duration >2 seconds; talk time uses durations of those connected calls.',
  'Callyzer employee matches based on unique names rather than matching CRM phones: '+', '.join(name_matches)+'. These name-based identity matches were approved by you; the phone discrepancy remains documented.',
  'Enrolled = currently enrolled lead records with enrollmentDate in the selected range, attributed to the current BDE. The API supplies no enrollmentId for these records. This is not verified historical seller attribution or a count of every program enrollment.',
  'Follow-ups completed counts completed tasks returned by the follow-up API with completedAt in the selected range. Calls, notes and other follow-up actions are not included.',
  'Booked sale value and Collections received are time-based: each is taken from the CRM Revenue Dashboard for its transaction period, queried one IST day at a time and attributed by its BDE breakdown. They are distinct: booked sale value is not cash received. Historical pending follow-ups and stage-change counts remain unavailable and show as —.',
  'Extraction completed: '+read('extracted_at.json')['at']+'. The CRM pagination total and unique lead IDs reconcile; the Callyzer stream END total reconciles. Sources: CRM /admin/leads, /admin/users, /admin/teams, /admin/followups; Callyzer /employee/get and /call-log/history/stream.'
 ]
 source=dict(sample=False,as_of=datetime.fromisoformat(read('extracted_at.json')['end_exclusive']).strftime('%d %b %Y, %H:%M IST'),coverage={'start':str(START),'end':str(END)},bdes=members,arrivals=arrivals,leads=leads,calls=calls,daily_crm=daily,unavailable_metrics=['pending','stageMoves'],source_notes=notes)
 (O/'normalized_input.json').write_text(json.dumps(source,ensure_ascii=False))
 audit=dict(period=source['coverage'],bdes=len(members),crm_snapshot_records=len(crm),account_call_records=len(raw_calls),leads_arrived=len(arrivals),leads_received=len(leads),calls=len(calls),connected=sum(r['connected'] for r in calls),unique_contacts=len({r['contact_key'] for r in calls}),enrolled=sum(enrolled.values()),followups_completed=sum(completed.values()),mappings=mappings,unavailable_metrics=source['unavailable_metrics'],by_bde=[{'name':u['name'],'vertical':u['vertical'],'arrived':sum(r['bde_id']==u['id'] for r in arrivals),'received':sum(r['bde_id']==u['id'] for r in leads),'calls':sum(r['bde_id']==u['id'] for r in calls)} for u in members])
 (O/'validation_summary.json').write_text(json.dumps(audit,indent=2));print(json.dumps({k:v for k,v in audit.items() if k not in ('mappings','by_bde')}))
if __name__=='__main__':main()
