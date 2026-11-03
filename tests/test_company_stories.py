import copy
from datetime import datetime,timedelta,timezone
import unittest
from company_stories import deduplicate_company_stories,signatures,is_company_preview

NOW=datetime(2026,11,3,10,tzinfo=timezone.utc)
def row(title):return dict(title=title,category='EQUITIES',decision='eligible')
def sent(title,now=NOW):
 r=row(title);deduplicate_company_stories([r],{},now)
 return {e['key']:{**e,'sent_at':now.isoformat()} for e in r['company_events']}

class CompanyStoriesTests(unittest.TestCase):
 def test_four_real_apple_earnings_rewrites_keep_one(self):
  titles=['Apple results beat Wall Street expectations on strong iPhone sales',
   'Apple earnings beat by $0.11, revenue topped estimates',
   'Apple beats quarterly estimates for profit and revenue',
   'Apple posts stronger-than-expected revenue in first earnings report for new CEO John Ternus']
  rows=[row(t) for t in titles]
  self.assertEqual(len(deduplicate_company_stories(rows,{},NOW)),1)
  self.assertEqual(sum(r['decision']=='duplicate_company_story' for r in rows),3)
 def test_margin_guidance_is_not_hidden_by_the_earnings_beat(self):
  history=sent('Apple results beat Wall Street expectations')
  news=row('Apple forecasts margin drop in holiday quarter as rising memory costs bite')
  self.assertEqual(len(deduplicate_company_stories([news],history,NOW)),1)
 def test_mixed_company_headline_covers_apple_but_not_unseen_company(self):
  history=sent('Apple and Palantir shares slide in premarket trading following post-bell earnings')
  apple=row('Apple shares slide as higher memory costs fuel margin concerns')
  self.assertFalse(deduplicate_company_stories([apple],history,NOW))
  new=row('Apple and Nvidia shares slide after earnings')
  self.assertEqual(len(deduplicate_company_stories([new],history,NOW)),1)
 def test_reaction_reversal_and_large_move_are_new(self):
  history=sent('Apple shares slide after earnings')
  for title in ('Apple shares rise after earnings','Apple shares plunge 6% after earnings'):
   self.assertEqual(len(deduplicate_company_stories([row(title)],history,NOW)),1)
  history=sent('Apple shares plunge 6% after earnings')
  self.assertFalse(deduplicate_company_stories([row('Apple shares fall 7% after earnings')],history,NOW))
  self.assertEqual(len(deduplicate_company_stories([row('Apple shares plunge 11% after earnings')],history,NOW)),1)
 def test_new_target_direction_correction_and_quarter_survive(self):
  history=sent('Apple forecasts margin drop in holiday quarter')
  for title in ('Apple raises margin outlook','Apple cuts margin forecast to 35%',
                'Apple restates earnings: EPS $1.20 instead of $1.40'):
   self.assertEqual(len(deduplicate_company_stories([row(title)],history,NOW)),1)
  history=sent('Apple beats Q3 2026 earnings estimates')
  self.assertEqual(len(deduplicate_company_stories([row('Apple beats Q4 2026 earnings estimates')],history,NOW)),1)
 def test_new_deal_regulation_supply_or_personnel_not_limited(self):
  for title in ('Apple acquires startup for $5 billion','Apple fined $4 billion after earnings',
                'Apple shares fall after factory fire','Apple recalls iPhones; shares fall after earnings',
                'Apple CEO resigns after earnings','Apple cuts iPhone production by 20%'):
   self.assertFalse(signatures(title),title)
 def test_previews_are_rejected_but_actual_forecast_change_survives(self):
  self.assertTrue(is_company_preview('Apple earnings outlook: guidance, not the beat, is the key variable'))
  self.assertTrue(is_company_preview('Apple earnings preview: what to watch'))
  self.assertFalse(is_company_preview('Apple cuts revenue forecast ahead of earnings'))
 def test_rolling_history_crosses_midnight_expires_and_is_read_only(self):
  history=sent('Apple earnings beat Wall Street estimates',NOW-timedelta(hours=12))
  before=copy.deepcopy(history)
  self.assertFalse(deduplicate_company_stories([row('Apple results beat quarterly expectations')],history,NOW))
  self.assertEqual(history,before)
  self.assertEqual(len(deduplicate_company_stories([row('Apple earnings beat Wall Street estimates')],history,NOW+timedelta(hours=13))),1)
 def test_other_companies_and_unknown_news_are_independent(self):
  history=sent('Apple earnings beat Wall Street estimates')
  for title in ('Microsoft earnings beat Wall Street estimates','Apple announces new chip platform'):
   self.assertEqual(len(deduplicate_company_stories([row(title)],history,NOW)),1)

 def test_margin_percentage_is_not_a_share_price_milestone(self):
  history=sent('Apple shares slide after earnings')
  self.assertFalse(deduplicate_company_stories([row('Apple shares slide after earnings as margin forecast drops to 35%')],history,NOW))
