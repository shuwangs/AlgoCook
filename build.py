import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
output = ROOT / "dist"

topic_output = output / "topics"
topic_output.mkdir(parents=True, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=select_autoescape(["html"]),
)

template = env.get_template("index.html")
topic_template = env.get_template("topic.html")

# read local data
data_path = ROOT / "data" / "topics.json"
data = json.loads(data_path.read_text(encoding="utf-8"))

topics =  []

for topic in data.get("topics",  []):
    problem_slugs = {
        problem["slug"]
        for section in topic["sections"]
        for problem in section["problems"]
    }
    topics.append({
    "id": topic["id"],
    "name": topic["title_en"] or "Untitled Topic",
    "problem_count": len(problem_slugs),
})
    
html = template.render(
    site_name="AlgoCook",
    topics=topics,
    total_problems = len(data.get("problems", [])),
)

for topic in data["topics"]:
    topic_html = topic_template.render(
        topic=topic,
        problems=data["problems"],
    )

    page_path = topic_output / f"{topic['id']}.html"
    page_path.write_text(topic_html, encoding="utf-8")

print(f"Built {len(data['topics'])} topic pages")
output.mkdir(exist_ok=True)
(output / "index.html").write_text(html, encoding="utf-8")

print("Built dist/index.html")


# FOr each topic, generate a page with the list of problems and their details



