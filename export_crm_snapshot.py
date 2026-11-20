"""Export complete CRM records in one read-only transaction for the BDE report."""
import argparse,json,os
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import psycopg2,requests
from dotenv import load_dotenv,dotenv_values

p=argparse.ArgumentParser();p.add_argument('--db-env',required=True);p.add_argument('--output',required=True);a=p.parse_args()
root=Path(__file__).resolve().parent;out=root/a.output;out.mkdir(parents=True,exist_ok=True)
load_dotenv(a.db_env)
c=psycopg2.connect(host=os.environ['DB_HOST'],port=os.getenv('DB_PORT','5432'),dbname=os.environ['DB_NAME'],user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],connect_timeout=20)
c.set_session(readonly=True,isolation_level='REPEATABLE READ')
org='00000000-0000-0000-0000-000000000002'
def query(sql):
 with c.cursor() as q:
  q.execute(sql,(org,));return [dict(zip([d[0] for d in q.description],r)) for r in q.fetchall()]
def serialize(v):
 if isinstance(v,datetime):return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).isoformat()
 return str(v)
def save(name,obj):(out/name).write_text(json.dumps(obj,default=serialize))
try:
 leads=query('''SELECT id,organization_id AS "organizationId",assigned_to_id AS "assignedToId",assigned_at AS "assignedAt",created_at AS "createdAt",lead_stage AS stage,status,stage_details AS "stageDetails",enrollment_date AS "enrollmentDate" FROM leads WHERE organization_id=%s''')
 activities=query('''SELECT a.lead_id,a.type,a.created_at AS "createdAt" FROM lead_activities a JOIN leads l ON l.id=a.lead_id WHERE l.organization_id=%s AND a.type='lead_reactivated' ''')
 grouped=defaultdict(list)
 for r in activities:grouped[r.pop('lead_id')].append(r)
 for r in leads:r['activities']=grouped[r['id']]
 save('leads_snapshot.json',leads)
 users=query('''SELECT id,name,mobile,alternate_mobile AS "alternateMobile",organization_id AS "organizationId",role FROM admin_users WHERE organization_id=%s''');save('admin_users.json',{'data':users})
 followups=query('''SELECT id,assigned_to_id AS "assignedToId",status,completed_at AS "completedAt" FROM follow_ups WHERE organization_id=%s''');save('followups_snapshot.json',{'data':followups})
 payments=query('''SELECT id,lead_id AS "leadId",raised_by_id AS "raisedById",revenue_counted AS "revenueCounted",payment_date AS "paymentDate",amount_received AS "amountReceived",sale_value AS "saleValue",covered_enrollment_ids AS "coveredEnrollmentIds" FROM lead_payments WHERE organization_id=%s''');save('payments_snapshot.json',{'payments':payments})
 save('crm_db_manifest.json',{'extracted_at':datetime.now(timezone.utc),'readonly':True,'isolation':'REPEATABLE READ','leads':len(leads),'payments':len(payments),'followups':len(followups)})
 print('Consistent DB snapshot:',len(leads),'leads,',len(payments),'payments',flush=True)
finally:c.close()
v=dotenv_values(root/'.env')
r=requests.get(v['CALLYZER_API_BASE_URL'].rstrip('/')+'/employee/get',headers={'Authorization':'Bearer '+v['CALLYZER_API_TOKEN']},params={'page_no':1,'page_size':100},timeout=30);r.raise_for_status();d=r.json()
assert d['message']=='Success' and len(d['result'])==d['total_records']
save('callyzer_employees.json',d)
