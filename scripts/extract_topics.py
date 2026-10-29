#!/usr/bin/env python3
"""Manually snapshot Endlesscheng study-list indexes, without a database.

Only Python's standard library is required. No scheduled jobs or website build.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

OVERVIEW_URL = 'https://leetcode.cn/discuss/post/3141566/ru-he-ke-xue-shua-ti-by-endlesscheng-q3yd/'
METADATA_URL = 'https://leetcode.cn/api/problems/all/'
LINK = re.compile(r'(?<!!)\[([^\]\n]+)\]\((https://leetcode\.cn/[^\s)]+)\)')
PROBLEM_PATH = re.compile(r'^/problems/([^/]+)/?$')
HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
TOPIC_NAMES = {
    '0viNMK': ('sliding-window-two-pointers', 'Sliding Window & Two Pointers'),
    'SqopEo': ('binary-search', 'Binary Search'),
    '9oZFK9': ('monotonic-stack', 'Monotonic Stack'),
    'YiXPXW': ('grid-graphs', 'Grid Graphs'),
    'dHn9Vk': ('bit-manipulation', 'Bit Manipulation'),
    '01LUak': ('graph-algorithms', 'Graph Algorithms'),
    'tXLS3i': ('dynamic-programming', 'Dynamic Programming'),
    'mOr1u6': ('data-structures', 'Data Structures'),
    'IYT3ss': ('mathematics', 'Mathematics'),
    'g6KTKL': ('greedy', 'Greedy & Problem Solving'),
    'K0n2gO': ('linked-lists-trees-backtracking', 'Linked Lists, Trees & Backtracking'),
    'SJFwQI': ('strings', 'Strings'),
}


class ExtractionError(Exception):
    """A source changed, failed validation, or could not be downloaded."""


class NextDataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == '__NEXT_DATA__':
            self.active = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def extract_article(html):
    parser = NextDataParser()
    parser.feed(html)
    try:
        data = json.loads(''.join(parser.parts))
        queries = data['props']['pageProps']['dehydratedState']['queries']
        for query in queries:
            result = query.get('state', {}).get('data')
            if isinstance(result, dict):
                article = result.get('qaQuestion')
                if isinstance(article, dict) and isinstance(article.get('content'), str):
                    if article['content'].strip():
                        return article
    except (ValueError, KeyError, TypeError):
        pass
    raise ExtractionError('Article data missing. The page may be a login/challenge page or its format changed.')


def fetch(url, timeout, delay):
    if urlparse(url).scheme != 'https' or urlparse(url).hostname != 'leetcode.cn':
        raise ExtractionError(f'Expected an HTTPS leetcode.cn URL: {url}')
    if delay:
        time.sleep(delay)
    print(f'Fetching {url}', file=sys.stderr, flush=True)
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': 'AlgoCook-Manual-Importer/1.0', 'Accept': '*/*'})
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode('utf-8'), response.url
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise ExtractionError(f'HTTP {exc.code} fetching {url}; existing output was not replaced.') from exc
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise ExtractionError(f'Cannot fetch {url}: {exc}') from exc
        time.sleep(2 ** attempt)
    raise ExtractionError(f'Cannot fetch {url}')


def discover_topics(content):
    """Use only the complete-list section, not repeated links in prose/tables."""
    topics = []
    seen = set()
    section_level = None
    for line in content.splitlines():
        heading = HEADING.match(line)
        if heading:
            level, title = len(heading[1]), heading[2].replace('*', '').strip()
            if title == '完整题单':
                section_level = level
                continue
            if section_level is not None and level <= section_level:
                break
        if section_level is None or not re.match(r'^\s*\d+[.)]\s+', line):
            continue
        for label, url in LINK.findall(line):
            path = urlparse(url).path
            if not re.match(r'^/(?:circle/discuss|discuss/post)/', path) or url in seen:
                continue
            seen.add(url)
            key = path.rstrip('/').split('/')[-1]
            slug, english = TOPIC_NAMES.get(key, (key, None))
            topics.append({'id': slug, 'title_zh': label, 'title_en': english, 'url': url, 'order': len(topics) + 1})
    if not topics:
        raise ExtractionError('No topics found in 完整题单. Refusing to write an empty snapshot.')
    return topics


def extract_route(content):
    route = []
    for line in content.splitlines():
        if not line.lstrip().startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) < 4 or not re.fullmatch(r'\d+', re.sub(r'[$*\s]', '', cells[0])):
            continue
        links = LINK.findall(cells[1])
        if links:
            route.append({'order': int(re.sub(r'[$*\s]', '', cells[0])),
                          'title_zh': links[0][0], 'url': links[0][1],
                          'required_zh': cells[2], 'note_zh': cells[3]})
    return route


def parse_metadata(data):
    entries = data.get('stat_status_pairs') if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ExtractionError('Invalid official problem metadata: expected nonempty stat_status_pairs.')
    result = {}
    for entry in entries:
        stat = entry['stat']
        slug = stat['question__title_slug']
        result[slug] = {'id': str(stat['frontend_question_id']), 'title_en': stat['question__title'],
                        'difficulty': {1: 'Easy', 2: 'Medium', 3: 'Hard'}.get(entry.get('difficulty', {}).get('level')),
                        'paid_only': entry.get('paid_only')}
    return result


def parse_topic(content, metadata, translations):
    sections, stack, problems = [], [], {}
    occurrence = 0
    fenced = False
    for line in content.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = HEADING.match(line)
        # Keep short source grouping labels such as 思维扩展 inside their section.
        group = (stack and not heading and 0 < len(line.strip()) <= 30 and not LINK.search(line)
                 and re.search(r'[:：]\s*$', line.replace('*', '').strip()))
        if heading or group:
            level = len(heading[1]) if heading else 7
            title = (heading[2] if heading else line).replace('**', '').strip().rstrip(':：')
            while stack and stack[-1]['level'] >= level:
                stack.pop()
            section = {'id': f's{len(sections) + 1}', 'level': level,
                       'parent_id': stack[-1]['id'] if stack else None,
                       'title_zh': title, 'title_en': translations.get(title),
                       'order': len(sections) + 1, 'problems': []}
            sections.append(section)
            stack.append(section)
            continue
        if not re.match(r'^\s*(?:[-*+]|\d+[.)])\s+', line):
            continue
        for match in LINK.finditer(line):
            label, url = match.groups()
            slug_match = PROBLEM_PATH.fullmatch(urlparse(url).path)
            if not slug_match:
                continue  # Exclude tutorials, solutions, and other posts.
            slug = slug_match[1]
            title_match = re.match(r'^(.+?)\.\s+(.+)$', label)
            source_id, title = title_match.groups() if title_match else (None, None)
            if not title_match:
                short_id = re.fullmatch(r'(\d+)\s*题', label)
                source_id = short_id[1] if short_id else None
            official = metadata.get(slug, {})
            problem_id = official.get('id', source_id)
            previous = problems.get(slug, {})
            problems[slug] = {'id': problem_id or previous.get('id'),
                              'title_zh': title or previous.get('title_zh'),
                              'title_en': official.get('title_en'), 'slug': slug,
                              'url_cn': f'https://leetcode.cn/problems/{slug}/',
                              'url_en': f'https://leetcode.com/problems/{slug}/',
                              'difficulty': official.get('difficulty'),
                              'paid_only': official.get('paid_only')}
            if not stack:
                section = {'id': f's{len(sections) + 1}', 'level': 1, 'parent_id': None,
                           'title_zh': '未分类', 'title_en': 'Uncategorized',
                           'order': len(sections) + 1, 'problems': []}
                sections.append(section)
                stack.append(section)
            suffix = line[match.end():].strip()
            rating = re.match(r'^\$?(\d{4})\$?(?=\s|$)', suffix)
            occurrence += 1
            stack[-1]['problems'].append({'slug': slug, 'order': occurrence,
                                          'source_label': label,
                                          'rating': int(rating[1]) if rating else None,
                                          'premium_in_source': '会员题' in suffix})
    if not occurrence:
        raise ExtractionError('No problem links found. Refusing to replace output with an empty topic.')
    return sections, problems


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            name = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return number


def nonnegative_float(value):
    number = float(value)
    if number < 0 or not number < float('inf'):
        raise argparse.ArgumentTypeError('must be a finite nonnegative number')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--overview-url', default=OVERVIEW_URL)
    parser.add_argument('--topic-url', action='append', help='Import one topic directly; may be repeated.')
    parser.add_argument('--limit', type=positive_int, help='Import only the first N discovered topics.')
    parser.add_argument('--output', type=Path, default=Path('data/topics.json'))
    parser.add_argument('--delay', type=nonnegative_float, default=1.0, help='Seconds before each request (default: 1).')
    parser.add_argument('--timeout', type=positive_int, default=30)
    parser.add_argument('--html', type=Path, help='Parse one saved topic HTML offline instead of fetching articles.')
    parser.add_argument('--metadata-file', type=Path, help='Saved JSON from the official /api/problems/all/ endpoint.')
    parser.add_argument('--skip-metadata', action='store_true', help='Leave English problem titles and difficulty null.')
    parser.add_argument('--translations', type=Path, help='JSON object mapping exact source headings to reviewed English.')
    args = parser.parse_args()
    if args.html and (not args.topic_url or len(args.topic_url) != 1):
        parser.error('--html requires exactly one --topic-url for source attribution')
    if args.html and not (args.metadata_file or args.skip_metadata):
        parser.error('offline --html requires --metadata-file or --skip-metadata')
    if args.skip_metadata and args.metadata_file:
        parser.error('--skip-metadata and --metadata-file cannot be combined')
    try:
        translations = json.loads(args.translations.read_text(encoding='utf-8')) if args.translations else {}
        if not isinstance(translations, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in translations.items()):
            raise ExtractionError('Translations must map source heading strings to English strings.')
        metadata = {}
        if not args.skip_metadata:
            raw = args.metadata_file.read_text(encoding='utf-8') if args.metadata_file else fetch(METADATA_URL, args.timeout, args.delay)[0]
            metadata = parse_metadata(json.loads(raw))
        overview = None
        if args.topic_url:
            topics = [{'id': f'topic-{i}', 'url': url, 'order': i, 'title_en': None}
                      for i, url in enumerate(dict.fromkeys(args.topic_url), 1)]
        else:
            html, resolved = fetch(args.overview_url, args.timeout, args.delay)
            overview = extract_article(html)
            topics = discover_topics(overview['content'])
        if args.limit:
            topics = topics[:args.limit]
        output_topics, all_problems = [], {}
        for topic in topics:
            if args.html:
                html, resolved = args.html.read_text(encoding='utf-8'), topic['url']
            else:
                html, resolved = fetch(topic['url'], args.timeout, args.delay)
            article = extract_article(html)
            known_topic = TOPIC_NAMES.get(article.get('uuid'))
            if known_topic:
                topic = {**topic, 'id': known_topic[0], 'title_en': known_topic[1]}
            sections, problems = parse_topic(article['content'], metadata, translations)
            output_topics.append({**topic, 'source_title': article.get('title'), 'resolved_url': resolved,
                                  'source_updated_at': article.get('updatedAt'), 'sections': sections})
            for slug, problem in problems.items():
                if slug in all_problems and all_problems[slug]['id'] != problem['id']:
                    if all_problems[slug]['id'] and problem['id']:
                        raise ExtractionError(f'Conflicting problem IDs for {slug}')
                previous = all_problems.get(slug, {})
                problem['id'] = problem['id'] or previous.get('id')
                problem['title_zh'] = problem['title_zh'] or previous.get('title_zh')
                all_problems[slug] = problem
            print(f"Parsed {topic['id']}: {len(problems)} unique problems", file=sys.stderr, flush=True)
        missing = [p['slug'] for p in all_problems.values() if not p['title_en']]
        untranslated = sorted({s['title_zh'] for t in output_topics for s in t['sections'] if not s['title_en']})
        snapshot = {'schema_version': 1, 'fetched_at': datetime.now(timezone.utc).isoformat(),
                    'source': {'author': '灵茶山艾府 (Endlesscheng)',
                               'overview_url': None if args.topic_url else args.overview_url,
                               'overview_updated_at': overview.get('updatedAt') if overview else None,
                               'metadata_url': None if args.skip_metadata else METADATA_URL},
                    'core_route': extract_route(overview['content']) if overview else [],
                    'topics': output_topics, 'problems': all_problems,
                    'review': {'missing_english_problem_titles': missing, 'untranslated_headings': untranslated}}
        atomic_json(args.output, snapshot)
        print(f'Saved {len(output_topics)} topics / {len(all_problems)} unique problems to {args.output}')
        print(f'Review: {len(missing)} missing English titles; {len(untranslated)} headings awaiting translation.')
        return 0
    except (ExtractionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
