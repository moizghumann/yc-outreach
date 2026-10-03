import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline import main
from prospecting import (PROFILE, WEIGHTS, blank_card, evaluate, research_packet,
                         score_route, screen, screen_all, valid_evidence)
from api import yc

DAY = dt.date(2026, 10, 3)
EVIDENCE = {'claim': 'Company confirms the condition', 'url': 'https://fictional.test/jobs',
            'checked_at': DAY.isoformat()}
COMPANY = {'name': 'Fictional ServiceQueue', 'slug': 'fictional-servicequeue',
           'website': 'https://fictional.test', 'team_size': 3, 'batch': 'Summer 2026',
           'one_liner': 'B2B field service workflow software'}


def route(value=4):
    c = blank_card(screen(COMPANY))['routes']['employment']
    for g in c['gates'].values():
        g.update(state='pass', evidence=copy.deepcopy(EVIDENCE))
    for r in c['ratings'].values():
        r.update(value=value, rationale='A sourced reason', evidence=copy.deepcopy(EVIDENCE))
    return c


class QualificationTests(unittest.TestCase):
    def test_team_ceiling(self):
        self.assertEqual(screen({**COMPANY, 'team_size': 6})['screen']['state'], 'reject')

    def test_unknown_team_is_preserved(self):
        for value in (None, 0, '', -1, True, 'unknown'):
            self.assertTrue(screen({**COMPANY, 'team_size': value})['screen']['unknowns'])

    def test_numeric_string_team(self):
        self.assertEqual(screen({**COMPANY, 'team_size': '3'})['screen']['state'], 'research')

    def test_recent_batches(self):
        self.assertEqual(screen({**COMPANY, 'batch': 'Winter 2024'})['screen']['state'], 'reject')
        self.assertEqual(screen({**COMPANY, 'batch': 'Summer 2027'})['screen']['state'], 'reject')

    def test_specialist_matches_require_review(self):
        c = screen({**COMPANY, 'one_liner': 'AI agents for security operations workflows'})
        self.assertEqual(c['screen']['state'], 'review')

    def test_workflow_rank_exceeds_generic_ai(self):
        ai = screen({**COMPANY, 'one_liner': 'AI-powered copilot'})
        self.assertGreater(screen(COMPANY)['screen']['discovery_rank'], ai['screen']['discovery_rank'])

    def test_inactive(self):
        self.assertEqual(screen({**COMPANY, 'status': 'Inactive'})['screen']['state'], 'reject')

    def test_no_keyword_is_not_a_hard_rejection(self):
        c = screen({**COMPANY, 'one_liner': 'Something unusual'})
        self.assertEqual(c['screen']['state'], 'review')

    def test_direct_ar_held(self):
        c = screen({**COMPANY, 'one_liner': 'Accounts receivable automation'})
        self.assertEqual(c['screen']['state'], 'hold')

    def test_deduplicate_canonical_domain(self):
        self.assertEqual(len(screen_all([COMPANY, {**COMPANY, 'website': 'http://www.fictional.test/'}])), 1)

    def test_imported_company_without_batch(self):
        c = dict(COMPANY, source='Techstars')
        c.pop('batch')
        c.pop('slug')
        self.assertEqual(screen(c)['screen']['state'], 'research')

    def test_remaining_weights_sum_to_90(self):
        self.assertEqual(sum(WEIGHTS.values()), 90)

    def test_full_ratings(self):
        s = score_route(route(), 'employment', DAY)
        self.assertEqual((s['B'], s['E'], s['effective_priority']), (100, 100, 100))

    def test_toolkit_formula(self):
        r = route()
        values = [4,4,3,4,3,3,2,4,4,3,3,4]
        for k, v in zip(WEIGHTS, values):
            r['ratings'][k]['value'] = v
        self.assertEqual(score_route(r, 'employment', DAY)['E'], 84.44)
        self.assertEqual(score_route(r, 'project', DAY)['P'], 90)
        self.assertEqual(score_route(r, 'employment', DAY)['B'], 87.22)

    def test_unknown_budget_cap_with_legacy_geography(self):
        r = route()
        r['gates']['budget']['state'] = 'unknown'
        r['gates']['geography'] = {'state': 'unknown'}
        s = score_route(r, 'employment', DAY)
        self.assertEqual((s['effective_priority'], s['effort']), (59, 'L1'))

    def test_legacy_geography_cannot_reject_or_change_score(self):
        r = route()
        r['gates']['geography'] = {'state': 'reject', 'evidence': EVIDENCE}
        r['ratings']['geography'] = {'value': 999}
        self.assertEqual(score_route(r, 'employment', DAY)['effective_priority'], 100)
        self.assertEqual(score_route(r, 'employment', DAY)['state'], 'qualified')

    def test_blank_cards_and_prompts_exclude_geography_checks(self):
        c = blank_card(screen(COMPANY))
        self.assertNotIn('geography', c['routes']['employment']['gates'])
        self.assertNotIn('geography', c['routes']['employment']['ratings'])
        self.assertNotIn('Pakistan', research_packet(screen(COMPANY)))

    def test_need_cap(self):
        r = route()
        r['gates']['need']['state'] = 'unknown'
        self.assertEqual(score_route(r, 'employment', DAY)['effective_priority'], 54)

    def test_hard_reject_beats_score(self):
        r = route()
        r['gates']['budget']['state'] = 'reject'
        self.assertEqual(score_route(r, 'employment', DAY)['effective_priority'], 0)

    def test_project_is_not_fallback_by_default(self):
        c = blank_card(screen(COMPANY))
        c['routes']['employment'] = route()
        c['routes']['employment']['gates']['budget']['state'] = 'reject'
        e = evaluate(c, DAY)
        self.assertEqual(e['routes']['project']['state'], 'qualify-first')
        self.assertEqual(e['stage'], 'Qualify-first')

    def test_unknown_rating_cannot_be_inflated(self):
        r = route()
        for v in r['ratings'].values():
            v['evidence'] = {}
        self.assertEqual(score_route(r, 'employment', DAY)['E'], 25)

    def test_future_and_stale_evidence(self):
        for day in ('2026-10-04', '2026-08-01'):
            self.assertFalse(valid_evidence({**EVIDENCE, 'checked_at': day}, DAY))

    def test_unsupported_pass_downgraded(self):
        r = route()
        r['gates']['budget']['evidence'] = {}
        self.assertEqual(score_route(r, 'employment', DAY)['gates']['budget'], 'unknown')

    def test_penalties_not_duplicated(self):
        r = route()
        r['penalties'] = ['stale_signal', 'stale_signal']
        self.assertEqual(score_route(r, 'employment', DAY)['penalty'], 8)

    def test_bad_rating(self):
        r = route()
        r['ratings']['match']['value'] = 5
        with self.assertRaises(ValueError):
            score_route(r, 'employment', DAY)

    def test_no_draft_ready_without_card(self):
        c = blank_card(screen(COMPANY))
        c['routes']['employment'] = route()
        c['draft'] = {'subject': 'Workflow', 'body': 'Hello', 'sources_rechecked_at': DAY.isoformat(), 'claim_reviewed': True}
        self.assertFalse(evaluate(c, DAY)['draft_ready'])

    def test_draft_freshness_and_claim_review(self):
        c = blank_card(screen(COMPANY))
        c['routes']['employment'] = route()
        for k in ('observed_condition', 'hypothesis', 'already_shipped_check', 'alternative_explanation',
                  'falsification_question', 'matched_claim', 'permitted_proof', 'claim_limit'):
            c[k] = 'Filled'
        c['contact'] = {'name': 'Fictional Founder', 'route': 'https://fictional.test/contact', 'source': EVIDENCE}
        c['draft'] = {'subject': 'Workflow', 'body': 'Hello', 'sources_rechecked_at': DAY.isoformat(), 'claim_reviewed': True}
        self.assertTrue(evaluate(c, DAY)['draft_ready'])
        c['draft']['sources_rechecked_at'] = '2026-09-29'
        self.assertFalse(evaluate(c, DAY)['draft_ready'])

    def test_research_packet_excludes_private_and_guessed_fields(self):
        c = screen({**COMPANY, 'salary_floor': 12345, 'email_guesses': ['guess@fictional.test']})
        packet = research_packet(c)
        self.assertNotIn('12345', packet)
        self.assertNotIn('guess@fictional.test', packet)

    def test_cli_import_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / 'input.json'
            src.write_text(json.dumps([COMPANY, {**COMPANY, 'name': 'Rejected', 'website': 'https://rejected.test', 'team_size': 50}]))
            out = Path(folder) / 'pipeline'
            main(['screen', '--input', str(src), '--out', str(out)])
            summary = json.loads((out / 'summary.json').read_text())
            self.assertEqual(summary['research_packets'], 1)
            self.assertEqual(summary['reject'], 1)

    def test_profiles_skip_email_lookup(self):
        page = '<div data-page="' + __import__('html').escape(json.dumps({'props': {'company': {
            'website': COMPANY['website'], 'founders': [{'full_name': 'Fictional Founder', 'title': 'CEO'}]}}}), quote=True) + '">'
        with patch.object(yc, 'get', return_value=page), patch.object(yc, 'site_emails') as emails:
            result = yc.founders('fictional', profiles_only=True)
            emails.assert_not_called()
            self.assertNotIn('email_guesses', result['founders'][0])

    def test_api_rejects_arbitrary_targets(self):
        self.assertEqual(yc.route('action=screen&batch=https://example.test')[0], 400)
        self.assertEqual(yc.route('action=profiles&slugs=../../secret')[0], 400)


if __name__ == '__main__':
    unittest.main()
