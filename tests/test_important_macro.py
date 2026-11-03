import json
import tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import unittest
from decimal import Decimal
import important_macro as m

T=datetime(2026,11,6,13,30,tzinfo=timezone.utc)
def row(title='Non-Farm Employment Change',value='',forecast='200K',eid=1):
 return dict(id=eid,name=title,currency='USD',dateline=int(T.timestamp()),actual=value,forecast=forecast,previous='190K',timeMasked=False)
def html(rows):return '<script>window.calendarComponentStates[1]={days:'+json.dumps([{'events':rows}])+',other:1}</script>'
def weekly():return json.dumps([dict(title='Non-Farm Employment Change',country='USD',date=T.isoformat())])
class MacroTests(unittest.TestCase):
 def test_country_and_text_exclusions(self):
  for title,c in [('CPI m/m','USD'),('Official Bank Rate','GBP'),('SNB Policy Rate','CHF')]:self.assertTrue(m.selected(title,c))
  for title,c in [('Federal Funds Rate','GBP'),('BOE Gov Bailey Speaks','GBP'),('Congressional Elections','USD'),('GDP m/m','CAD')]:self.assertFalse(m.selected(title,c))
 def test_exact_utc_window(self):
  self.assertEqual(len(m.upcoming(weekly(),T-timedelta(seconds=600))),1)
  for now in (T,T+timedelta(seconds=1),T-timedelta(seconds=601)):self.assertFalse(m.upcoming(weekly(),now))
 def test_parser_real_structure_identity_not_local_time(self):
  self.assertEqual(m.match_event(m.page_events(html([row()])),row()['name'],'USD',T)['id'],1)
  for rows in ([row(eid=2)],[dict(row(),dateline=int(T.timestamp())+60)],[dict(row(),timeMasked=True)]):
   with self.assertRaises(ValueError):m.match_event(m.page_events(html(rows)),row()['name'],'USD',T,1)
 def test_duplicate_ids_and_days_fail_closed(self):
  for body in (html([row(),row()]),html([row()])+html([row(eid=2)])):
   with self.assertRaises(ValueError):m.page_events(body)
 def test_units_and_negative_values(self):
  self.assertEqual(m.comparison('0.25M','200K'),(Decimal('50000'), 'count'))
  self.assertEqual(m.comparison('-0.2%','0.1%')[0],Decimal('-0.3'))
  with self.assertRaises(ValueError):m.comparison('4.5%','4.5')
 def result(self,title,actual,forecast):return dict(title=title,currency='USD',actual=actual,forecast=forecast,previous='0')
 def test_cpi_positive_and_negative_conditions(self):
  for actual,arrow in [('0.4%','↓'),('0.1%','↑')]:
   msg=m.format_result([self.result('Core CPI m/m',actual,'0.2%')],T,T+timedelta(seconds=10))
   self.assertIn('EUR/USD '+arrow,msg);self.assertIn('si les taux US',msg)
 def test_nfp_unemployment_conflict_is_mixed_no_arrows(self):
  msg=m.format_result([self.result('Non-Farm Employment Change','250K','200K'),self.result('Unemployment Rate','4.5%','4.3%')],T,T)
  self.assertIn('MIXTES',msg);self.assertNotIn('↑',msg);self.assertNotIn('↓',msg)
 def test_no_surprise_from_previous_or_unknown_forecast(self):
  for f in ('','250K'):
   msg=m.format_result([self.result('Non-Farm Employment Change','250K',f)],T,T)
   self.assertNotIn('↑',msg);self.assertNotIn('↓',msg)
 def simulate(self,*,status=200,send_error=False,save_error=False):
  clock=[T-timedelta(seconds=120)];sent=[];saves=[]
  def now():return clock[0]
  def sleep(n):clock[0]+=timedelta(seconds=n)
  def get(url):
   if url==m.WEEK:return m.HTTPResult(200,weekly())
   if now()<T:return m.HTTPResult(200,html([row()]))
   return m.HTTPResult(status,html([row(value='250K',forecast='999K')]))
  def send(msg):
   self.assertEqual(json.loads(path.read_text())['events'][m.timestamp(T)]['status'],'send_pending')
   self.assertGreaterEqual(len(saves),2)
   sent.append(msg)
   if send_error:raise RuntimeError('private transport')
  def save():
   saves.append(1)
   if save_error:raise ValueError('not saved')
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'state.json'
   kwargs=dict(now=now,sleep=sleep,get=get,send=send,save=save,verify=lambda:dict(is_bot=True,username=m.EXPECTED_BOT),path=path)
   if save_error:
    with self.assertRaises(ValueError):m.watch(**kwargs)
   else:
    outcome=m.watch(**kwargs)
    self.assertEqual(m.watch(**kwargs),'outside_window') # after T0 no new capture
    self.assertEqual(json.loads(path.read_text())['events'][m.timestamp(T)]['status'],outcome)
   return sent,saves
 def test_watch_one_result_remote_reservation_before_post(self):
  sent,saves=self.simulate();self.assertEqual(len(sent),1);self.assertEqual(len(saves),3);self.assertIn('Publié : 250K',sent[0]);self.assertIn('Attendu : 200K',sent[0]);self.assertNotIn('999K',sent[0])
 def test_access_refusal_closes_without_result(self):
  sent,_=self.simulate(status=403);self.assertEqual(len(sent),1);self.assertIn('indisponibles',sent[0]);self.assertNotIn('Publié',sent[0])
 def test_uncertain_post_not_retried(self):
  sent,_=self.simulate(send_error=True);self.assertEqual(len(sent),1)
 def test_failed_checkpoint_blocks_post(self):
  sent,_=self.simulate(save_error=True);self.assertFalse(sent)

 def test_incomplete_batch_has_no_direction(self):
  msg=m.format_result([self.result('Core CPI m/m','0.4%','0.2%'),self.result('CPI m/m','0.5%','')],T,T)
  self.assertIn('incomplète',msg);self.assertNotIn('↑',msg);self.assertNotIn('↓',msg)
 def test_durable_snapshot_resumes_after_release(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'state.json';key=m.timestamp(T)
   snapshot=dict(title='Non-Farm Employment Change',currency='USD',id=1,forecast='200K',previous='190K')
   m.write_json(path,{'events':{key:dict(status='armed',forecast_at=m.timestamp(T-timedelta(seconds=60)),items=[snapshot])}})
   sent=[]
   def get(url):return m.HTTPResult(200,weekly() if url==m.WEEK else html([row(value='250K',forecast='999K')]))
   kwargs=dict(path=path,now=lambda:T+timedelta(seconds=30),get=get,save=lambda:None,send=sent.append,verify=lambda:dict(is_bot=True,username=m.EXPECTED_BOT))
   self.assertEqual(m.watch(**kwargs),'completed');self.assertIn('Attendu : 200K',sent[0])
   self.assertEqual(m.watch(**kwargs),'outside_window');self.assertEqual(len(sent),1)

 def test_identical_responsive_calendar_copies_are_allowed(self):
  self.assertEqual(len(m.page_events(html([row()])+html([row()]))),1)
