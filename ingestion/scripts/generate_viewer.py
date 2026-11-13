import json
import os
import re
from pathlib import Path
from typing import Optional


def _normalize_block_mcq(block: dict) -> dict:
    """Convert a block-format mcq (qnum/question/options[{key,text}]/answer/explanation)
    to the flat viewer shape (question_number/question_text/options[{label,text}]/correct_answer/short_explanation)."""
    return {
        "question_number": block.get("qnum"),
        "question_text": block.get("question", ""),
        "options": [
            {"label": o.get("key") or o.get("label"), "text": o.get("text", "")}
            for o in block.get("options", [])
        ],
        "correct_answer": block.get("answer"),
        "short_explanation": block.get("explanation"),
        "images": block.get("images", []),
        "page": block.get("page"),
    }


def _resolve_image_src(src: str, json_path: Path, output_html: Optional[Path] = None) -> str:
    """Resolve an image src to a path usable in the output HTML.
    Block format stores paths like '/data/<book_id>/assets/foo.png'.
    Files actually live at <book_folder>/assets/foo.png next to the JSON.
    If `output_html` is given, returns a path relative to it (works on http:// and file://).
    Otherwise returns an absolute file:// URI."""
    if not src:
        return ""
    if src.startswith(("http://", "https://", "file://", "data:")):
        return src
    # Strip leading '/data/<book_id>/' prefix and resolve relative to JSON's folder
    rel = src.lstrip("/")
    rel = re.sub(r"^data/[^/]+/", "", rel)
    candidate = (json_path.parent / rel).resolve()
    if not candidate.exists():
        candidate = (json_path.parent / src.lstrip("/")).resolve()
    if not candidate.exists():
        return src
    if output_html is not None:
        try:
            return os.path.relpath(candidate, output_html.parent).replace(os.sep, "/")
        except ValueError:
            pass  # different drives on Windows → fall through to file URI
    return candidate.as_uri()


def _extract_from_block_format(data: dict, json_path: Path):
    """Extract mcqs + metadata from the chapter/sections/blocks format used by klm_anatomy_mcqs."""
    chapter = data.get("chapter", {})
    meta = data.get("metadata", {})
    unit_title = chapter.get("title") or meta.get("chapter_title") or "Chapter"
    unit_num = chapter.get("order") or meta.get("chapter_order") or "??"

    mcqs = []
    items = []  # ordered list of {kind, ...} entries for rendering in reading order
    for section in chapter.get("sections", []):
        for block in section.get("blocks", []):
            btype = block.get("type")
            if btype == "mcq":
                flat = _normalize_block_mcq(block)
                mcqs.append(flat)
                items.append({"kind": "mcq", "mcq": flat})
            elif btype in ("heading", "paragraph", "image"):
                items.append({"kind": btype, "block": block})
    return mcqs, items, unit_title, unit_num


def generate_viewer(json_path: str, output_html: str):
    json_path_p = Path(json_path)
    with open(json_path_p, 'r', encoding='utf-8') as f:
        data = json.load(f)

    items: list = []
    is_block_format = isinstance(data, dict) and isinstance(data.get("chapter"), dict) \
        and isinstance(data["chapter"].get("sections"), list)

    if is_block_format:
        mcqs, items, unit_title, unit_num = _extract_from_block_format(data, json_path_p)
        export_dir = json_path_p.parent
    elif isinstance(data, dict):
        mcqs = data.get("mcqs", [])
        unit_title = data.get("unit_title", "General Physiology")
        unit_num = data.get("unit_number", "??")
        export_dir = json_path_p.parent.parent / "export"
    else:
        mcqs = data
        unit_title = "General Physiology"
        unit_num = "??"
        export_dir = json_path_p.parent.parent / "export"

    # If flat format, build items list as just MCQs so we can share one render loop
    if not is_block_format:
        items = [{"kind": "mcq", "mcq": q} for q in mcqs]
    
    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GoLearnix MCQ Viewer - Topic {{unit_num}}</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .markdown-render { white-space: pre-wrap; font-family: inherit; }
        .markdown-render table { border-collapse: collapse; width: 100%; margin-bottom: 1rem; border: 1px solid #dfe2e5; }
        .markdown-render th, .markdown-render td { border: 1px solid #dfe2e5; padding: 6px 13px; }
        .markdown-render tr:nth-child(2n) { background-color: #f6f8fa; }
        .markdown-render img { max-width: 100%; height: auto; }
        /* Restore sub/sup styling that Tailwind Preflight strips (see FRONTEND_NOTES.md) */
        sub, sup { font-size: 75%; line-height: 0; position: relative; vertical-align: baseline; }
        sup { top: -0.5em; }
        sub { bottom: -0.25em; }
        .sidebar-link:hover { background-color: #f3f4f6; }
        .sidebar-active { background-color: #eef2ff; border-left: 4px solid #4f46e5; color: #4f46e5; }
    </style>
</head>
<body class="bg-gray-50 font-sans">
    <div class="flex h-screen overflow-hidden">
        <!-- Sidebar -->
        <div class="w-72 bg-white border-r flex flex-col">
            <div class="p-6 border-b">
                <h1 class="text-2xl font-black text-indigo-600 tracking-tight">GoLearnix</h1>
                <p class="text-[10px] text-gray-400 font-bold uppercase tracking-widest mt-1">{{unit_title}}</p>
            </div>
            <div class="flex-1 overflow-y-auto p-4 space-y-1">
                {{nav_links}}
            </div>
        </div>

        <!-- Main Content -->
        <div class="flex-1 overflow-y-auto bg-gray-50 scroll-smooth">
            <div id="content" class="max-w-4xl mx-auto py-12 px-6 space-y-12">
                {{questions_html}}
            </div>
        </div>
    </div>

    <script>
        // Initialize Markdown rendering
        const renderer = new marked.Renderer();
        marked.setOptions({
            renderer: renderer,
            gfm: true,
            tables: true,
            breaks: true
        });

        document.querySelectorAll('.markdown-render').forEach(el => {
            const raw = el.textContent.trim();
            el.innerHTML = marked.parse(raw);
        });

        // Basic scroll highlighting
        window.addEventListener('hashchange', () => {
            const hash = window.location.hash;
            document.querySelectorAll('.sidebar-link').forEach(link => {
                if (link.getAttribute('href') === hash) {
                    link.classList.add('sidebar-active');
                } else {
                    link.classList.remove('sidebar-active');
                }
            });
        });
    </script>
</body>
</html>
"""

    nav_links = []
    questions_html = []

    output_html_p = Path(output_html).resolve()

    def _resolve_item_image(src: str) -> str:
        if is_block_format:
            return _resolve_image_src(src, json_path_p, output_html_p)
        # Flat format: images are under export_dir
        img_path = (export_dir / src).resolve()
        if not img_path.exists():
            return src
        try:
            return os.path.relpath(img_path, output_html_p.parent).replace(os.sep, "/")
        except ValueError:
            return img_path.as_uri()

    for item in items:
        kind = item["kind"]

        # ── Non-MCQ blocks (block format only) ─────────────────────────────
        if kind == "heading":
            b = item["block"]
            level = max(1, min(int(b.get("level", 2)), 4))
            size = {1: "text-3xl", 2: "text-2xl", 3: "text-xl", 4: "text-lg"}[level]
            questions_html.append(
                f'<h{level} class="{size} font-bold text-gray-900 tracking-tight">{b.get("text", "")}</h{level}>'
            )
            continue
        if kind == "paragraph":
            b = item["block"]
            questions_html.append(
                f'<div class="markdown-render text-gray-700 leading-relaxed">{b.get("text", "")}</div>'
            )
            continue
        if kind == "image":
            b = item["block"]
            src = _resolve_item_image(b.get("src", ""))
            caption = b.get("caption", "") or ""
            questions_html.append(f"""
                <div class="my-4">
                    <img src="{src}" class="rounded-xl shadow-sm border border-gray-200 bg-white p-2 mx-auto">
                    {f'<p class="text-center text-xs text-gray-400 mt-2 italic">{caption}</p>' if caption else ''}
                </div>
            """)
            continue

        # ── MCQ ────────────────────────────────────────────────────────────
        q = item["mcq"]
        num = q.get("question_number")
        qid = f"q{num}"
        nav_links.append(f'<a href="#{qid}" class="sidebar-link block p-3 rounded-lg text-sm font-medium text-gray-600 transition-colors">Question {num}</a>')

        # Build images HTML — supports either list[str] or list[{src,caption}]
        images_html = ""
        for img in q.get('images', []) or []:
            if isinstance(img, dict):
                img_src_raw = img.get("src", "")
                caption = img.get("caption", "") or img_src_raw
            else:
                img_src_raw = img
                caption = img
            abs_img_path = _resolve_item_image(img_src_raw)
            images_html += f"""
                <div class="my-6">
                    <img src="{abs_img_path}" class="rounded-xl shadow-lg border border-gray-200 bg-white p-2">
                    <p class="text-center text-xs text-gray-400 mt-2 italic">{caption}</p>
                </div>
            """

        # Build options HTML
        options_list = []
        # options in JSON is a list of { "label": "A", "text": "..." }
        opts = q.get("options", [])
        for opt in opts:
            label = opt.get("label")
            text = opt.get("text")
            is_correct = label == q.get("correct_answer")
            
            border_cls = "border-green-500 bg-green-50" if is_correct else "border-gray-100 bg-white"
            label_cls = "text-green-600" if is_correct else "text-indigo-600"
            
            options_list.append(f"""
                <div class="flex items-start space-x-4 p-4 border rounded-xl shadow-sm {border_cls}">
                    <span class="font-black text-lg {label_cls}">{label}</span>
                    <div class="markdown-render flex-1 text-gray-800 leading-relaxed pt-0.5">{text}</div>
                </div>
            """)
        
        options_html = '<div class="grid gap-4 mt-6">' + "".join(options_list) + '</div>'

        questions_html.append(f"""
            <section id="{qid}" class="bg-white p-10 rounded-2xl shadow-sm border border-gray-100 relative">
                <div class="flex justify-between items-center mb-6">
                    <div class="flex items-center space-x-3">
                        <span class="w-10 h-10 flex items-center justify-center bg-indigo-600 text-white rounded-lg font-bold text-lg shadow-md shadow-indigo-200">{num}</span>
                        <h2 class="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{unit_title}</h2>
                    </div>
                    <div class="flex space-x-2">
                         <span class="px-3 py-1 bg-gray-100 text-gray-600 text-[10px] rounded-full font-bold uppercase tracking-tight">Topic {unit_num}</span>
                    </div>
                </div>
                
                <div class="markdown-render text-xl font-semibold text-gray-900 leading-snug mb-8">{q.get('question_text')}</div>
                
                {images_html}
                
                <div class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">Select Response</div>
                {options_html}
                
                <div class="mt-8 pt-8 border-t border-dashed border-gray-100">
                    <details class="group">
                        <summary class="list-none cursor-pointer flex items-center text-sm font-bold text-indigo-500 hover:text-indigo-600 transition-colors">
                            <svg class="w-4 h-4 mr-2 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                            View Explanation & Answer
                        </summary>
                        <div class="mt-4 p-5 bg-indigo-50 rounded-xl text-indigo-900 text-sm leading-relaxed markdown-render">
                            <strong>Correct Answer: {q.get('correct_answer')}</strong><br><br>
                            {q.get('short_explanation', 'No explanation provided.')}
                        </div>
                    </details>
                </div>
            </section>
        """)

    final_html = html_template.replace("{{nav_links}}", "\n".join(nav_links))
    final_html = final_html.replace("{{questions_html}}", "\n".join(questions_html))
    final_html = final_html.replace("{{unit_title}}", str(unit_title))
    final_html = final_html.replace("{{unit_num}}", str(unit_num))

    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(final_html)

if __name__ == "__main__":
    import argparse
    import sys
    
    # Add project root to sys.path to import src
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.core.books import BOOK_METADATA
    from src.core.config import OUTPUT_MCQ_DIR

    parser = argparse.ArgumentParser(description="Generate a web-based preview for MCQ JSON files.")
    parser.add_argument("topic", help="Topic filename (e.g., topic_01.json) or number (e.g., 1)")
    parser.add_argument("--book", default="physiology_mcqs", help="Book key (default: physiology_mcqs)")
    parser.add_argument("--output", default="mcq_preview.html", help="Path to the output HTML file")
    args = parser.parse_args()
    
    # 1. Resolve JSON path
    json_path = Path(args.topic)
    if not json_path.exists():
        # Try to resolve via book metadata
        meta = BOOK_METADATA.get(args.book)
        if meta:
            topic_filename = args.topic
            if topic_filename.isdigit():
                topic_filename = f"topic_{int(topic_filename):02d}.json"
            elif not topic_filename.endswith(".json"):
                topic_filename = f"{topic_filename}.json"
                
            json_path = (
                OUTPUT_MCQ_DIR 
                / meta["year"] 
                / meta["subject"] 
                / meta["display_name"] 
                / "raw" 
                / topic_filename
            )

    if json_path.exists():
        generate_viewer(str(json_path), args.output)
        print(f"\nSuccess! Dashboard generated.")
        print(f"Input: {json_path}")
        print(f"Location: {os.path.abspath(args.output)}")
        print(f"Open this file in your browser to see the results.")
    else:
        print(f"❌ Error: Could not find JSON file at {json_path}")
        print(f"Usage: python scripts/generate_viewer.py <topic_number_or_file> [--book <book_key>]")
