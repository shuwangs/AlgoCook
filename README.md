# AlgoCook

A lightweight, Python-based algorithm study site (planned). This repository currently contains a manual study-list importer; it does not build or deploy a website.

## Manual import

Python 3.10+; no third-party dependencies or database required. Run from the repository root:

```sh
# First run: import the first topic from the overview.
python3 scripts/extract_topics.py --limit 1

# Import all topics linked under 完整题单.
python3 scripts/extract_topics.py

# Import a specific topic instead of discovering the full list.
python3 scripts/extract_topics.py \
  --topic-url https://leetcode.cn/discuss/post/3578981/ti-dan-hua-dong-chuang-kou-ding-chang-bu-rzz7/ \
  --output data/sliding-window.json
```

Default output: `data/topics.json`. Each run replaces the selected output with a complete snapshot of **only that run's selected topics**; `--limit` and `--topic-url` do not merge with an earlier full import. Use a different `--output` for experiments.

The script reads public article data embedded in LeetCode's HTML. It discovers topic links from [Endlesscheng's overview](https://leetcode.cn/discuss/post/3141566/ru-he-ke-xue-shua-ti-by-endlesscheng-q3yd/) and matches English problem titles against LeetCode's `/api/problems/all/` metadata. Source pages and endpoints may change or become unavailable; the importer reports an error rather than bypassing access restrictions.

## Output

- `source`: author attribution, overview URL, source update date, metadata source.
- `fetched_at`: UTC extraction timestamp.
- `core_route`: the overview's recommended route, separate from the complete topic list; repeated topics remain repeated.
- `topics`: topics in source order, with source URLs and a flat section list containing `parent_id` for nesting.
- `sections[].problems`: ordered occurrences, each referencing a problem by slug and retaining the source link label. Ratings belong to occurrences, not to the deduplicated problem catalog. Repeated appearances remain intact.
- `problems`: one record per problem slug, containing source ID/title, official English title, English/Chinese URLs, and available difficulty/premium metadata.
- `review`: missing English titles and untranslated headings requiring review.

Only the index structure and problem metadata are extracted; teaching paragraphs and solutions are not copied. Missing metadata stays `null`. Shorthand links such as “2407 题” and descriptive link labels are retained; when no full Chinese title or problem ID can be established, those fields stay `null`. English titles are not guessed from slugs. Exact leading four-digit source scores are captured; numbers in prose such as “约 2300” are not treated as official ratings.

### English category names

The 12 known overview topic names have reviewed English labels. Chapter/subsection names and route notes retain their source text until translated. Supply a UTF-8 JSON object with exact source headings as keys:

```json
{
  "一、定长滑动窗口": "Fixed-length Sliding Window",
  "§1.1 基础": "§1.1 Basics",
  "§1.2 进阶（选做）": "§1.2 Advanced (Optional)",
  "思维扩展": "Further Practice"
}
```

```sh
python3 scripts/extract_topics.py --translations translations.json
```

The importer prepares data for an English site; it is not an automatic translator. Original headings stay available for attribution and review.

### Saved pages / offline use

Save a topic's HTML and the official metadata JSON locally, then run:

```sh
python3 scripts/extract_topics.py \
  --topic-url https://leetcode.cn/discuss/post/3578981/ti-dan-hua-dong-chuang-kou-ding-chang-bu-rzz7/ \
  --html saved-topic.html \
  --metadata-file saved-metadata.json \
  --output data/offline-topic.json
```

Use `--skip-metadata` instead of `--metadata-file` to extract the source index only (English titles/difficulty remain null). Offline mode makes no network requests. `--html` must be accompanied by exactly one `--topic-url` identifying its source.

Requests are sequential, with a one-second delay by default and a 30-second timeout per attempt. Use `--delay 2` to slow down or `--timeout 60` for slower connections. Transient failures retry up to twice. A blocked page, invalid source, failed download, or empty topic causes a nonzero exit; the existing output remains untouched. Output is replaced atomically only after every selected topic has parsed successfully.

Review the generated JSON diff before committing data. Nothing runs on a schedule and no publication is configured.

## Checks

```sh
python3 -m unittest discover -s tests -v
```
