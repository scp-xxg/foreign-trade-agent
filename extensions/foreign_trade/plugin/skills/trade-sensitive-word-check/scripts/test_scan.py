import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from scan import scan, ROOT

def run(text, **context):
    return scan({'fields':[{'id':'body','text':text}], 'context':context})
def ids(result):
    return {rid for hit in result['hits'] for rid in hit['related_rule_ids']}

class SensitiveScanTests(unittest.TestCase):
    def test_source_25_cases_with_documented_correction(self):
        source=(ROOT/'references/source-lexicon-v4.0.md').read_text()
        section=source[source.index('## 18.'):source.index('## 19.')]
        rows=re.findall(r'^\| (\d+) \| `([^`]+)`.*?\| ([^|]+) \| ([^|]+) \|$',section,re.M)
        self.assertEqual(len(rows),25)
        for number,text,expected,level in rows:
            with self.subTest(case=number,text=text):
                result=run(text); found=ids(result)
                if number=='5':self.assertIn('S403',found)
                elif number=='21':self.assertIn('DE301',found)
                elif number=='22':self.assertIn('JP301',found)
                elif expected.strip()=='—':self.assertEqual(found,set())
                else:self.assertIn(expected.strip(),found)
    def test_no_neighbor_whitelist_bypass(self):
        self.assertIn('S402',ids(run('FDA registered facility; FDA approved LED lamp')))
        self.assertIn('S406',ids(run('Compatible with iPhone. Apple authorized supplier')))
        self.assertIn('S301',ids(run('Our best price. Best regards')))
    def test_unicode_and_original_offsets(self):
        text='标题\nＣＥ\u200b certified lamp'
        hit=next(h for h in run(text)['hits'] if h['rule_id']=='S401')
        self.assertEqual(hit['match'],'ＣＥ\u200b certified')
        self.assertEqual(text[slice(*hit['span'])],hit['match'])
        self.assertEqual((hit['line'],hit['column']),(2,1))
        self.assertIn('S302',ids(run('#1 supplier')))
    def test_normal_substrings_and_context(self):
        self.assertNotIn('S404',ids(run('creature healthy')))
        self.assertIn('S404',ids(run('heat treatment')))  # Context review must distinguish industrial usage.
        x=run('Made in Germany; WhatsApp +49 123; treatment',platform='email',market='DE')
        self.assertEqual(x['context']['platform'],'email')
        self.assertTrue(all(h['applicability']=='not_determined' for h in x['hits']))
        self.assertFalse(x['external_action_executed'])
        self.assertFalse(x['coverage']['legal_or_platform_approval'])
    def test_culture_and_geography_not_legal_verdict(self):
        result=run('Halal products, Hong Kong address')
        self.assertEqual(result['recommended_action'],'review_in_context')
        self.assertTrue(all(h['level']=='L1' for h in result['hits']))
    def test_supported_multilingual_candidates(self):
        for text,rid in [('TÜV geprüft','DE301'),('le meilleur','FR301'),('el mejor','ES301'),('o melhor','PT301'),('Bismillah','AR101'),('самый лучший','RU301'),('最高級','JP301'),('무독성','KR301')]:
            with self.subTest(text=text):self.assertIn(rid,ids(run(text)))
    def test_validation_and_no_empty_success(self):
        for data in [{},{'fields':[]},{'fields':[{'id':'a','text':''}]},{'fields':[{'id':'a','text':'x'},{'id':'a','text':'y'}]},{'fields':[{'id':'a','text':'x'*200001}]},{'fields':[{'id':'a','text':'x'}],'context':{'approved':True}}]:
            with self.subTest(data=str(data)[:60]),self.assertRaises(ValueError):scan(data)
    def test_no_hits_still_not_approved_and_hash_changes(self):
        a=run('Best regards');b=run('Best wishes')
        self.assertEqual(a['status'],'no_lexical_hits');self.assertFalse(a['coverage']['legal_or_platform_approval'])
        self.assertNotEqual(a['input_sha256'],b['input_sha256'])
        self.assertIsNone(a['metrics']['precision'])
    def test_truncation_never_claims_complete(self):
        x=run('best price '*2100)
        self.assertEqual(x['status'],'incomplete');self.assertFalse(x['scan_complete']);self.assertEqual(len(x['hits']),2000)
    def test_cli_file_report_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            inp=Path(directory)/'input.json';out=Path(directory)/'output.json'
            inp.write_text(json.dumps({'fields':[{'id':'body','text':'CE certified'}]}))
            command=[sys.executable,str(ROOT/'scripts/scan.py'),'--input',str(inp),'--output',str(out)]
            first=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr);self.assertIn('S401',ids(json.loads(out.read_text())))
            original=out.read_bytes();second=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(second.returncode,2);self.assertEqual(out.read_bytes(),original)
if __name__=='__main__':unittest.main()
