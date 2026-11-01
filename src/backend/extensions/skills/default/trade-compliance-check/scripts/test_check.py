from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from check import check,digest,ROOT

class ComplianceTests(unittest.TestCase):
    def data(self):return json.loads((ROOT/'references/example-input.json').read_text())
    def reviewed(self):
        d=self.data();d['evidence']=[dict(id='e',reference='TEST ONLY: reviewer supplied record',text='Fixture evidence, not a legal assessment',retrieved_at='2026-10-30T00:00:00Z',valid_until='2026-12-01T00:00:00Z')]
        for row in check(d)['checks']:
            d['reviews'].append(dict(check_id=row['check_id'],scope_hash=row['scope_hash'],rule_hash=row['rule_hash'],evidence_hash=digest(d['evidence']),evidence_ids=['e'],decision='satisfied',reviewer='test reviewer',note='Synthetic test only',reviewed_at='2026-10-31T00:00:00Z',valid_until='2026-11-20T00:00:00Z'))
        return d
    def test_germany_food_contact_routing(self):
        x=check(self.data());ids={r['check_id'] for r in x['checks']}
        self.assertIn('DE:EU-FOOD',ids);self.assertIn('DE:DE-LOCAL',ids);self.assertIn('DE:PLATFORM-AMAZON',ids)
        self.assertNotIn('DE:US-FOOD',ids);self.assertNotIn('DE:EU-ELECTRICAL',ids)
        self.assertEqual(x['status'],'needs_review');self.assertEqual(x['sensitive_scan']['status'],'no_lexical_hits')
    def test_outreach_excludes_shipment_requirements(self):
        d=self.data();d.update(stage='outreach',channel='email');ids={r['check_id'] for r in check(d)['checks']}
        self.assertIn('DE:BASE-OUTREACH',ids);self.assertNotIn('DE:EU-FOOD',ids);self.assertNotIn('DE:BASE-SHIP',ids)
    def test_unknown_feature_not_silently_excluded(self):
        d=self.data();d['product']['features']['food_contact']=None
        row=next(r for r in check(d)['checks'] if r['check_id']=='DE:EU-FOOD')
        self.assertEqual(row['selection'],'potential');self.assertEqual(row['status'],'scope_confirmation_required')
    def test_unknown_market_and_missing_scope(self):
        d=self.data();d['markets']=['CA'];x=check(d)
        self.assertIn('CA:market_pack_missing',x['coverage_gaps']);self.assertFalse(x['release_authorized'])
        d['markets']=[];x=check(d);self.assertIn('missing_target_market',x['coverage_gaps'])
        self.assertTrue(any(r['selection']=='potential' for r in x['checks']))
    def test_eu_national_coverage_and_multiple_markets(self):
        d=self.data();d['markets']=['FR','US'];x=check(d);ids={r['check_id'] for r in x['checks']}
        self.assertIn('FR:EU-FOOD',ids);self.assertIn('US:US-FOOD',ids);self.assertNotIn('US:EU-FOOD',ids)
        self.assertIn('FR:national_pack_missing_EU_topics_only',x['coverage_gaps'])
    def test_valid_supplied_reviews_still_not_legal_approval(self):
        x=check(self.reviewed());self.assertEqual(x['status'],'scoped_checklist_reviewed')
        self.assertEqual(x['legal_compliance'],'not_determined');self.assertFalse(x['release_authorized'])
        self.assertEqual(x['reuse_summary']['reused'],len(x['checks']))
    def test_changed_market_does_not_reuse_other_market(self):
        d=self.reviewed();d['markets']=['US'];x=check(d)
        self.assertEqual(x['reuse_summary']['reused'],0);self.assertTrue(x['ignored_previous_reviews'])
    def test_text_only_invalidates_dependent_checks(self):
        d=self.reviewed();d['fields'][0]['text']='Steel drinking bottle';x=check(d)
        rows={r['check_id']:r for r in x['checks']}
        self.assertEqual(rows['DE:BASE-CLAIMS']['status'],'review_invalidated')
        self.assertTrue(rows['DE:EU-FOOD']['supplied_review_reused'])
    def test_stale_or_changed_evidence_and_future_review(self):
        for change in ['expired','changed','future','missing']:
            d=self.reviewed()
            if change=='expired':d['as_of']='2027-01-01T00:00:00Z'
            if change=='changed':d['evidence'][0]['text']='new evidence'
            if change=='future':d['reviews'][0]['reviewed_at']='2026-11-02T00:00:00Z'
            if change=='missing':d['evidence']=[]
            with self.subTest(change=change):self.assertGreater(check(d)['reuse_summary']['invalidated'],0)
    def test_rule_version_invalidates_review(self):
        d=self.reviewed();pack=json.loads((ROOT/'references/packs.json').read_text());pack['rules'][0]['version']='2'
        x=check(d,pack);row=next(r for r in x['checks'] if r['check_id']=='DE:BASE-CLAIMS')
        self.assertIn('rule_changed',row['issues'])
    def test_sensitive_hit_prevents_clean_summary(self):
        d=self.reviewed();d['fields'][0]['text']='CE certified lamp'
        x=check(d);self.assertEqual(x['status'],'needs_review')
        self.assertTrue(any(r['rule_id']=='S401' for r in x['sensitive_scan']['hits']))
    def test_invalid_inputs(self):
        for change in ['time','feature','duplicate','stage']:
            d=self.data()
            if change=='time':d['as_of']='2026-11-01T12:00:00'
            if change=='feature':d['product']['features']['children']='false'
            if change=='duplicate':d['markets']=['DE','DE']
            if change=='stage':d['stage']='unknown'
            with self.subTest(change=change),self.assertRaises(ValueError):check(d)
    def test_cli_actual_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'report.json'
            args=[sys.executable,str(ROOT/'scripts/check.py'),'--input',str(ROOT/'references/example-input.json'),'--output',str(out)]
            r=subprocess.run(args,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads(out.read_text())['status'],'needs_review')
            self.assertEqual(subprocess.run(args,capture_output=True).returncode,2)
if __name__=='__main__':unittest.main()
