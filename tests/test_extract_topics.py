import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

spec = importlib.util.spec_from_file_location('extract_topics', Path(__file__).parents[1] / 'scripts/extract_topics.py')
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


class ExtractionTests(unittest.TestCase):
    def test_article_missing_or_challenge_is_rejected(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_article('<html>Please log in</html>')
        article = {'title': 'Example', 'content': '## Section'}
        state = {'props': {'pageProps': {'dehydratedState': {'queries': [
            {'state': {'data': {'qaQuestion': article}}}
        ]}}}}
        html = '<script type="application/json" id="__NEXT_DATA__">' + json.dumps(state) + '</script>'
        self.assertEqual(extractor.extract_article(html), article)

    def test_discovery_does_not_duplicate_route_links(self):
        url = 'https://leetcode.cn/circle/discuss/0viNMK/'
        content = f'''#### 核心刷题路线
| $1$ | [滑窗]({url}) | 定长 | 简单 |
#### 完整题单
1. [滑窗]({url})
2. [滑窗重复]({url})
## Other
1. [不是题单](https://leetcode.cn/circle/discuss/skip/)
'''
        self.assertEqual(len(extractor.discover_topics(content)), 1)
        self.assertEqual(extractor.discover_topics(content)[0]['title_en'], 'Sliding Window & Two Pointers')
        self.assertEqual(extractor.extract_route(content)[0]['order'], 1)

    def test_hierarchy_order_duplicates_and_scores(self):
        content = '''## 一、分类
### §1.1 基础
- [3. 题一](https://leetcode.cn/problems/first/) 1329
[教程](https://leetcode.cn/problems/first/solutions/1/guide/)
**思维扩展**：
- [LCP 68. 特殊题号](https://leetcode.cn/problems/second/)（会员题）
### §1.2 进阶
- [3. 题一](https://leetcode.cn/problems/first/) 非暴力约 2300
```python
- [4. 代码块中的链接](https://leetcode.cn/problems/ignored/)
```
'''
        metadata = {'first': {'id': '3', 'title_en': 'First', 'difficulty': 'Medium', 'paid_only': False}}
        sections, problems = extractor.parse_topic(content, metadata, {'一、分类': 'Category'})
        self.assertEqual(len(problems), 2)
        self.assertEqual(problems['second']['id'], 'LCP 68')
        self.assertIsNone(problems['second']['title_en'])
        self.assertEqual(sections[0]['title_en'], 'Category')
        self.assertEqual(sections[1]['parent_id'], sections[0]['id'])
        self.assertEqual(sections[2]['parent_id'], sections[1]['id'])
        self.assertEqual(sections[3]['parent_id'], sections[0]['id'])
        occurrences = [p for s in sections for p in s['problems']]
        self.assertEqual([p['order'] for p in occurrences], [1, 2, 3])
        self.assertEqual(occurrences[0]['rating'], 1329)
        self.assertIsNone(occurrences[2]['rating'])
        self.assertTrue(occurrences[1]['premium_in_source'])

    def test_empty_topics_and_invalid_metadata_rejected(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.parse_topic('## Empty', {}, {})
        with self.assertRaises(extractor.ExtractionError):
            extractor.parse_metadata({'error': 'challenge'})
        with self.assertRaises(extractor.ExtractionError):
            extractor.discover_topics('No complete-list heading')

    def test_interview_ids_containing_dots_are_not_truncated(self):
        sections, problems = extractor.parse_topic(
            '## Topic\n- [面试题 16.06. 最小差](https://leetcode.cn/problems/smallest-difference-lcci/) 1500', {}, {})
        problem = problems['smallest-difference-lcci']
        self.assertEqual(problem['id'], '面试题 16.06')
        self.assertEqual(problem['title_zh'], '最小差')
        self.assertEqual(sections[0]['problems'][0]['rating'], 1500)

    def test_shorthand_and_descriptive_links_keep_their_source_labels(self):
        content = '''## Topic
- [2407. 最长递增子序列 II](https://leetcode.cn/problems/longest-increasing-subsequence-ii/)
- [2407 题](https://leetcode.cn/problems/longest-increasing-subsequence-ii/)
- [另一种做法](https://leetcode.cn/problems/other/)
'''
        sections, problems = extractor.parse_topic(content, {}, {})
        self.assertEqual(len(sections[0]['problems']), 3)
        self.assertEqual(problems['longest-increasing-subsequence-ii']['id'], '2407')
        self.assertEqual(problems['longest-increasing-subsequence-ii']['title_zh'], '最长递增子序列 II')
        self.assertIsNone(problems['other']['id'])
        self.assertEqual(sections[0]['problems'][2]['source_label'], '另一种做法')

    def test_atomic_output_is_valid_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data' / 'topics.json'
            extractor.atomic_json(path, {'title': '旧数据'})
            extractor.atomic_json(path, {'title': '新数据'})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'title': '新数据'})
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_failed_import_does_not_replace_previous_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'topics.json'
            path.write_text('{"previous": true}', encoding='utf-8')
            bad_html = Path(directory) / 'blocked.html'
            bad_html.write_text('<html>Access denied</html>', encoding='utf-8')
            result = subprocess.run([
                sys.executable, str(Path(extractor.__file__)),
                '--topic-url', 'https://leetcode.cn/circle/discuss/example/',
                '--html', str(bad_html), '--skip-metadata', '--output', str(path),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Article data missing', result.stderr)
            self.assertEqual(path.read_text(encoding='utf-8'), '{"previous": true}')


if __name__ == '__main__':
    unittest.main()
