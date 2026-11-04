import unittest
from datetime import datetime,timedelta,timezone
from news_pipeline import inflation_signature, inflation_history_from_results, rank_eligible, _event_key
NOW=datetime(2026,11,4,11,30,tzinfo=timezone.utc)
def row(title):return dict(title=title,category='MACRO',score=7,published_at=NOW.isoformat(),decision='eligible')
def history(title):
 base,value=inflation_signature(title,NOW.isoformat())
 return {_event_key(base,value):dict(base=base,value=value,sent_at=NOW.isoformat())}
class InflationStoriesTests(unittest.TestCase):
 def test_real_three_headlines_keep_one(self):
  rows=[row(t) for t in ['Euro zone inflation rises to three-year high','Euro zone inflation hits 4% for first time in three years as interest rate hike looms','Eurozone inflation hits 4% for first time since 2023, piling pressure on ECB']]
  self.assertEqual(len(rank_eligible(rows,now=NOW)),1)
 def test_reprises_suppressed_across_runs_unknown_rate_does_not_hide_new_value(self):
  h=history('Eurozone inflation hits 4%')
  self.assertFalse(rank_eligible([row('Euro zone inflation rises to three-year high')],h,NOW))
  self.assertFalse(rank_eligible([row('Euro zone inflation hits 4% for first time since 2023')],h,NOW))
  self.assertEqual(len(rank_eligible([row('Eurozone inflation revised from 4% to 4.1%')],h,NOW)),1)
  self.assertEqual(len(rank_eligible([row('Eurozone inflation hits 4%')],history('Eurozone inflation rises to three-year high'),NOW)),1)
 def test_core_monthly_country_period_and_final_values_stay_distinct(self):
  h=history('Eurozone annual inflation hits 4% in October 2026 flash estimate')
  for title in ('Eurozone core inflation rises to 2.5%','Eurozone monthly inflation rises to 0.3%',
                'German annual inflation rises to 4%','Eurozone inflation hits 4% in September 2026',
                'Eurozone final inflation comes in at 4%'):
   self.assertEqual(len(rank_eligible([row(title)],h,NOW)),1,title)
 def test_policy_expectations_and_market_moves_are_not_inflation_reprises(self):
  for title in ('ECB hikes rates as eurozone inflation hits 4%', 'ECB warns eurozone inflation could rise',
                'Eurozone inflation expected to rise to 4%','Eurozone inflation expectations rise to 4%',
                'Euro rises as eurozone inflation hits 4%', 'Eurozone bond yields rise as inflation hits 4%',
                'German state inflation rises to 4%','Eurozone inflation revised lower'):
   self.assertIsNone(inflation_signature(title,NOW.isoformat()),title)
 def test_us_alias_and_history_expiry(self):
  self.assertTrue(inflation_signature('United States inflation rises to 4%',NOW.isoformat()))
  self.assertEqual(len(rank_eligible([row('Eurozone inflation hits 4%')],history('Eurozone inflation hits 4%'),NOW+timedelta(hours=25))),1)
 def test_confirmed_structured_result_suppresses_rss_not_uncertain_or_mixed_metrics(self):
  event=dict(status='completed',telegram_accepted_at=NOW.isoformat(),items=[dict(title='CPI Flash Estimate y/y',actual='4.0%',currency='EUR')])
  h=inflation_history_from_results({'events':{'x':event}},NOW)
  self.assertFalse(rank_eligible([row('Eurozone inflation hits 4%')],h,NOW))
  self.assertEqual(len(rank_eligible([row('Eurozone core inflation rises to 2.5%')],h,NOW)),1)
  for status in ('send_pending','send_uncertain','unavailable'):
   self.assertFalse(inflation_history_from_results({'events':{'x':dict(event,status=status)}},NOW))

 def test_other_macro_data_with_inflation_context_is_not_a_cpi_result(self):
  for title in ('US GDP grows 3.4% as September inflation accelerates',
                'US borrowing costs hit fresh highs on inflation fears'):
   self.assertIsNone(inflation_signature(title,NOW.isoformat()),title)
