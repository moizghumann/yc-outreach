"""Evidence-aware founder qualification. Standard library, no network or sending."""
import copy
import datetime as dt
import json
import re
from urllib.parse import urlparse

WEIGHTS = dict(zip(
    ('severity', 'match', 'proof', 'urgency', 'access', 'budget', 'geography',
     'role', 'project', 'differentiation', 'competition', 'upside', 'efficiency'),
    (12, 10, 10, 10, 8, 10, 10, 5, 5, 5, 4, 4, 7)))
GATES = ('geography', 'budget', 'need', 'authority', 'timing', 'depth', 'reviewer', 'ip')
PENALTIES = {'decision_31_60_days': 15, 'missing_reviewer': 10,
             'stale_signal': 8, 'undefined_acceptance': 10, 'unsponsored_proof': 5}
LANES = {
    'vertical_operations': ('workflow', 'scheduling', 'field service', 'case management',
                            'client portal', 'document collection', 'logistics', 'construction',
                            'approval', 'customer coordination', 'shared inbox', 'fleet management',
                            'property management', 'trucking', 'back-of-house', 'service delivery'),
    'accounting_adjacent': ('bookkeeping', 'accounting', 'reconciliation', 'finance operations'),
    'ai_workflow': ('automation', 'ai agent', 'ai-powered', 'artificial intelligence', 'copilot'),
}
DIRECT_AR = ('accounts receivable', 'receivables', 'debt collection', 'invoice collection',
             'collections automation', 'ar automation')
SPECIALIST = ('robotics', 'robots', 'semiconductor', 'cybersecurity', 'security operations',
              'model training', 'foundation model', 'ai infrastructure', 'control plane',
              'gpu infrastructure', 'defense', 'drug discovery')
PROFILE = {
    'positioning': 'Product Engineer for B2B workflows',
    'country': 'Pakistan', 'max_team_size': 5, 'min_batch_year': 2025,
    'max_batch_year': 2026,
    'effort_split': {'employment': 70, 'project': 30},
    'proof': 'Public product-story work and bounded workflow implementation experience; AI-assisted engineering.',
    'claim_limits': ['No measured revenue or adoption gains', 'No sole-authorship claim',
                     'No senior backend or production-agent expertise claim',
                     'No private employer artifacts or unconsented references'],
}


def today():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def canonical_domain(website):
    host = urlparse(website if '://' in (website or '') else 'https://' + (website or '')).hostname
    return (host or '').lower().removeprefix('www.')


def company_key(c):
    domain = canonical_domain(c.get('website'))
    slug = c.get('slug') or urlparse(c.get('yc_url') or '').path.rstrip('/').split('/')[-1]
    return domain or (('yc:' + slug) if slug else 'name:' + (c.get('name') or '').strip().lower())


def normalize(c):
    c = copy.deepcopy(c)
    c['slug'] = c.get('slug') or urlparse(c.get('yc_url') or '').path.rstrip('/').split('/')[-1]
    c['industry'] = c.get('industry') or c.get('subindustry') or ''
    c['description'] = c.get('description') or c.get('long_description') or ''
    c['location'] = c.get('location') or c.get('all_locations') or ''
    if c.get('slug') and not c.get('yc_url'):
        c['yc_url'] = 'https://www.ycombinator.com/companies/' + c['slug']
    c['id'] = company_key(c)
    c['source'] = c.get('source') or ('YC' if c.get('yc_url') else 'import')
    c.setdefault('sources', [{'url': c.get('yc_url') or c.get('website') or '',
                             'checked_at': today(), 'kind': 'directory'}])
    return c


def screen(company, profile=None):
    """Cheap directory triage. Keyword matches rank research; they never qualify a buyer."""
    p = {**PROFILE, **(profile or {})}
    c = normalize(company)
    text = ' '.join(str(c.get(k) or '') for k in ('name', 'one_liner', 'description', 'industry', 'tags')).lower()
    reasons, unknowns, holds = [], [], []
    team = c.get('team_size')
    try:
        if isinstance(team, bool) or team is None or str(team).strip() == '':
            raise ValueError
        team = float(team)
        if not team.is_integer() or team <= 0:
            raise ValueError
        if team > p['max_team_size']:
            reasons.append('Team exceeds configured size ceiling')
    except (TypeError, ValueError):
        unknowns.append('Team size unknown; verify before investing')
    year = re.search(r'(20\d{2})', str(c.get('batch') or ''))
    if year and not p['min_batch_year'] <= int(year[1]) <= p['max_batch_year']:
        reasons.append('YC batch outside configured discovery window')
    if str(c.get('status') or '').lower() in ('inactive', 'acquired', 'public'):
        reasons.append('Company status outside active early-stage search')
    matches = {lane: [t for t in terms if t in text] for lane, terms in LANES.items()}
    lane = next((lane for lane, terms in matches.items() if terms), 'b2b_general' if 'b2b' in text or 'saas' in text else 'unknown')
    if any(t in text for t in DIRECT_AR):
        lane = 'direct_receivables'
        holds.append('Direct receivables adjacency requires competition/IP clearance')
    if lane == 'unknown':
        unknowns.append('Workflow relevance not established by directory text')
    specialist = [term for term in SPECIALIST if term in text]
    if specialist:
        unknowns.append('Specialist product: verify a bounded interface role with technical review')
    state = 'reject' if reasons else 'hold' if holds else 'research' if lane != 'unknown' else 'review'
    if specialist and state == 'research':
        state = 'review'
    strength = {'vertical_operations': 100, 'accounting_adjacent': 90, 'b2b_general': 50,
                'ai_workflow': 30}.get(lane, 0) + min(9, len(matches.get(lane, [])))
    if c.get('is_hiring') or c.get('isHiring'):
        strength += 10  # Directory hint only, never a role-gate pass.
    if specialist:
        strength = min(strength, 10)
    return {**c, 'screen': {'state': state, 'lane': lane, 'reasons': reasons,
                           'holds': holds, 'unknowns': unknowns, 'matched_terms': matches,
                           'specialist_terms': specialist, 'discovery_rank': strength, 'checked_at': today()},
            'stage': 'Screened' if state != 'reject' else 'Rejected'}


def screen_all(companies, profile=None):
    seen, rows = set(), []
    for c in companies:
        row = screen(c, profile)
        if row['id'] not in seen:
            seen.add(row['id'])
            rows.append(row)
    return sorted(rows, key=lambda r: (r['screen']['state'] == 'reject',
                                      -r['screen']['discovery_rank'], r['name'].lower()))


def valid_evidence(e, as_of=None, max_age=30):
    """Requires an original URL, explicit fact and dated check. No source auto-verification."""
    if not isinstance(e, dict) or not e.get('claim'):
        return False
    u = urlparse(e.get('url') or '')
    if u.scheme not in ('http', 'https') or not u.hostname:
        return False
    try:
        age = ((as_of or dt.date.fromisoformat(today())) - dt.date.fromisoformat(e.get('checked_at', ''))).days
        return 0 <= age <= max_age
    except (ValueError, TypeError):
        return False


def blank_card(c):
    return {
        'company_id': c['id'], 'company': c['name'], 'researched_at': today(),
        'observed_condition': '', 'hypothesis': '', 'already_shipped_check': '',
        'alternative_explanation': '', 'falsification_question': '',
        'why_this_month': '', 'matched_claim': '', 'permitted_proof': '', 'claim_limit': '',
        'contact': {'name': '', 'route': '', 'source': {}},
        'routes': {route: {'gates': {g: {'state': 'unknown', 'evidence': {}} for g in GATES},
                           'ratings': {k: {'value': 1, 'rationale': '', 'evidence': {}} for k in WEIGHTS},
                           'penalties': [], 'notes': ''} for route in ('employment', 'project')},
        'next_action': '', 'due_date': '',
        'draft': {'subject': '', 'body': '', 'sources_rechecked_at': '', 'claim_reviewed': False},
    }


def score_route(route, route_name, as_of=None):
    gates, warnings = {}, []
    for key in GATES:
        g = route.get('gates', {}).get(key, {})
        state = g.get('state', 'unknown')
        if state not in ('pass', 'reject', 'unknown'):
            raise ValueError('Invalid gate state: ' + key)
        if state != 'unknown' and not valid_evidence(g.get('evidence'), as_of):
            warnings.append(key + ': missing or stale evidence; treated as unknown')
            state = 'unknown'
        gates[key] = state
    ratings = {}
    for key in WEIGHTS:
        r = route.get('ratings', {}).get(key, {})
        v = r.get('value', 1)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 4:
            raise ValueError('Rating must be 0–4: ' + key)
        ratings[key] = v if r.get('rationale') and valid_evidence(r.get('evidence'), as_of, 90) else 1
    common = sum(w * ratings[k] / 4 for k, w in WEIGHTS.items() if k not in ('role', 'project'))
    base = common + 5 * ratings['role'] / 4 + 5 * ratings['project'] / 4
    raw = common + 10 * ratings['role' if route_name == 'employment' else 'project'] / 4
    penalties = set(route.get('penalties', []))
    if penalties - PENALTIES.keys():
        raise ValueError('Unknown penalty')
    penalty = sum(PENALTIES[k] for k in penalties)
    caps = []
    if gates['budget'] == 'unknown' and gates['geography'] == 'unknown':
        caps.append(49)
    elif 'unknown' in (gates['budget'], gates['geography']):
        caps.append(59)
    if gates['need'] != 'pass':
        caps.append(54)
    state = 'reject' if 'reject' in gates.values() else 'qualify-first' if 'unknown' in gates.values() else 'qualified'
    effective = 0 if state == 'reject' else max(0, min([100, raw - penalty] + caps))
    # Unresolved gates never buy a deep dive, even if non-budget factors are strong.
    effort = 'L1' if state != 'qualified' else 'L3' if effective >= 80 else 'L2' if effective >= 65 else 'L1'
    return {'state': state, 'gates': gates, 'B': round(base, 2),
            'E' if route_name == 'employment' else 'P': round(raw, 2),
            'effective_priority': round(effective, 2), 'cap': min(caps) if caps else None,
            'penalty': penalty, 'effort': effort, 'warnings': warnings}


def evaluate(card, as_of=None):
    results = {r: score_route(card.get('routes', {}).get(r, {}), r, as_of) for r in ('employment', 'project')}
    available = [(r, v) for r, v in results.items() if v['state'] != 'reject']
    best = max(available, key=lambda rv: rv[1]['effective_priority']) if available else None
    missing = [k for k in ('observed_condition', 'hypothesis', 'already_shipped_check',
                          'alternative_explanation', 'falsification_question',
                          'matched_claim', 'permitted_proof', 'claim_limit') if not card.get(k)]
    contact = card.get('contact', {})
    if not contact.get('name') or not contact.get('route') or not valid_evidence(contact.get('source'), as_of):
        missing.append('verified contact route')
    draft = card.get('draft', {})
    try:
        age = ((as_of or dt.date.fromisoformat(today())) - dt.date.fromisoformat(draft.get('sources_rechecked_at', ''))).days
        fresh = 0 <= age <= 2
    except (ValueError, TypeError):
        fresh = False
    draft_ready = bool(best and not missing and fresh and draft.get('claim_reviewed') is True
                       and draft.get('subject') and draft.get('body') and len(draft['body'].split()) <= 140)
    return {'routes': results, 'recommended_route': best[0] if best else 'reject',
            'effective_priority': best[1]['effective_priority'] if best else 0,
            'missing_card_fields': missing, 'draft_ready': draft_ready,
            'stage': 'Draft ready' if draft_ready else 'Rejected' if not best else
                     'Qualified' if best[1]['state'] == 'qualified' and not missing else 'Qualify-first'}


def research_packet(c, profile=None):
    p = {**PROFILE, **(profile or {})}
    # Explicit projection excludes guessed contacts and arbitrary imported/private fields.
    context = {k: c.get(k) for k in ('id', 'name', 'website', 'yc_url', 'batch', 'team_size',
                                   'one_liner', 'description', 'industry', 'source', 'screen')}
    return '\n'.join([
        '# Research ' + c['name'],
        'Goal: paid remote product-area role or bounded project. Effort: 70% employment / 30% projects.',
        'Country: ' + p['country'] + '. Positioning: ' + p['positioning'],
        'Permitted experience context: ' + p['proof'],
        'Directory facts are discovery leads, not current verified need, headcount or eligibility.',
        'Use original company product, pricing, docs, changelog, careers and founder posts. No contacting or account creation.',
        'Record claim, source URL, publication date, event date and checked_at separately. Source checks must be current.',
        'Read the live listing. Remote/EMEA/funding never proves Pakistan eligibility or allocated budget.',
        'Check what already ships and who owns it. Public absence is not a missing-feature finding.',
        'Produce one observed condition, hypothesis, alternative explanation and falsification question.',
        'Evaluate geography, budget, need, authority, timing, depth/reviewer and IP independently for EACH route.',
        'A restricted vacancy cannot become a project by changing the label. Direct receivables work stays on hold until cleared.',
        'Only verified public work-contact routes; never use guessed emails. Contact-page presence does not verify founder identity.',
        'Match one defensible contribution and permitted proof. ' + '; '.join(p['claim_limits']) + '.',
        'No private salary floor, employer records, proprietary architecture or private chats in the output.',
        'Rate each factor 0–4 with rationale and evidence; unknown = 1. Scores rank effort, not close probability.',
        'Stop at a hard blocker. L1 cap 15 minutes; no custom implementation before sponsor, budget and review path.',
        'Return a completed research-card JSON in the schema below; leave unknown gates unknown. Do not draft generic mail.',
        'Evidence object: {"claim":"exact fact", "url":"original https URL", "checked_at":"YYYY-MM-DD", "published_at":null, "event_at":null}.',
        '\nDirectory context:\n' + json.dumps(context, ensure_ascii=False, indent=2),
        '\nResearch card:\n' + json.dumps(blank_card(c), ensure_ascii=False, indent=2),
    ])
