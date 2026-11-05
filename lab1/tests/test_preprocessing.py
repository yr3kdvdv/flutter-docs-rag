from flutter_rag.preprocessing.chunking import chunk_document, estimate_tokens
from flutter_rag.preprocessing.clean import clean_markdown
from flutter_rag.runconfig import ChunkingConfig

PAGE = """---
title: Add a Flutter screen
description: How to launch a screen.
---

<?code-excerpt path-base="x/"?>
<img src='/a.png' alt="hero">

{% comment %}
Internal note that must disappear.
{% endcomment %}

Read about [constraints][] and [`Widget`]({{site.api}}/flutter/widgets/Widget-class.html).
Generic types like `List<String>` stay intact.

[constraints]: /ui/layout/constraints

:::note
Make sure to import it.
:::

## Launch it {:#launch}

<Tabs key="lang">
<Tab name="Kotlin">

```kotlin title="Main.kt"
val x = listOf<String>() // <Tab name="not a tab">
```

</Tab>
<Tab name="Java">

```java
List<String> x = new ArrayList<>();
```

</Tab>
</Tabs>

{% render "docs/shared.md" %}
"""

INCLUDE = "---\ntitle: ignored\n---\nShared fragment text.\n"


def resolve(target):
    return INCLUDE if target == "docs/shared.md" else None


def test_clean_removes_markup_but_keeps_text_and_code():
    doc = clean_markdown(PAGE, resolve)
    body = doc.body
    assert doc.title == "Add a Flutter screen"
    for gone in ["{%", "{{", "<img", "<?code-excerpt", ":::", "Internal note", "<Tabs", "]: /"]:
        assert gone not in body, gone
    assert "Read about constraints and `Widget`." in body
    assert "`List<String>`" in body  # inline code untouched
    assert "Note:\nMake sure to import it." in body
    assert "Kotlin:" in body and "Java:" in body  # tab labels kept
    # code blocks are byte-for-byte, including text that looks like markup
    assert 'val x = listOf<String>() // <Tab name="not a tab">' in body
    assert "List<String> x = new ArrayList<>();" in body
    assert "Shared fragment text." in body and "title: ignored" not in body
    assert doc.missing_renders == []


def test_missing_render_is_reported_not_silently_kept():
    doc = clean_markdown('{% render "docs/nope.md" %}\ntext', lambda t: None)
    assert doc.missing_renders == ["docs/nope.md"]
    assert "render" not in doc.body


def test_section_chunks_keep_heading_path_anchor_and_page_prefix():
    doc = clean_markdown(PAGE, resolve)
    chunks = chunk_document(
        document_id="a/b",
        title=doc.title,
        url="https://docs.flutter.dev/a/b",
        body=doc.body,
        cfg=ChunkingConfig(),
    )
    launch = [c for c in chunks if c.section_path == ["Launch it"]]
    assert launch and launch[0].anchor == "launch"
    assert launch[0].source_url == "https://docs.flutter.dev/a/b#launch"
    assert launch[0].embed_text.startswith("Page: Add a Flutter screen > Launch it\n\n")
    assert launch[0].has_code


def test_chunk_ids_are_deterministic():
    doc = clean_markdown(PAGE, resolve)
    kw = dict(document_id="a/b", title="t", url="u", body=doc.body, cfg=ChunkingConfig())
    assert [c.chunk_id for c in chunk_document(**kw)] == [c.chunk_id for c in chunk_document(**kw)]


def _code(lines: int) -> str:
    body = "\n".join(f"  final value{i} = compute({i}); // padding text" for i in range(lines))
    return f"## Code\n\n```dart\n{body}\n```\n"


def test_code_under_soft_cap_is_not_split():
    cfg = ChunkingConfig(max_tokens=200, code_soft_cap_tokens=1024)
    body = _code(40)  # ~500 tokens: above max_tokens, below the soft cap
    chunks = chunk_document(document_id="d", title="t", url="u", body=body, cfg=cfg)
    assert len(chunks) == 1 and not chunks[0].code_split
    assert chunks[0].text.startswith("```dart") and chunks[0].text.endswith("```")


def test_code_over_soft_cap_is_split_and_refenced():
    cfg = ChunkingConfig(max_tokens=200, code_soft_cap_tokens=300)
    chunks = chunk_document(document_id="d", title="t", url="u", body=_code(60), cfg=cfg)
    assert len(chunks) > 1
    for c in chunks:
        assert c.code_split
        assert c.text.startswith("```dart\n") and c.text.endswith("\n```")
        assert estimate_tokens(c.text) <= cfg.max_tokens
    joined = "".join(c.text for c in chunks)
    assert joined.count("final value") == 60  # no line lost


def test_anchors_match_docs_site_rules():
    # Real ids observed on docs.flutter.dev (2026-10-23).
    body = (
        "### Step 1: Add FlutterActivity to AndroidManifest.xml\n\nx\n\n"
        "### Convert the `http.Response` to an `Album`\n\nx\n\n"
        "### Provider.of\n\nx\n\n"
        "## 3. Convert the response into a custom Dart object\n\nx\n\n"
        "### Recipes {:.no_toc}\n\nx\n\n### Recipes {:.no_toc}\n\nx\n\n"
        "### Custom {:#my-id}\n\nx\n"
    )
    cfg = ChunkingConfig(max_tokens=512)
    chunks = chunk_document(document_id="d", title="t", url="u", body=body, cfg=cfg)
    assert [c.anchor for c in chunks] == [
        "step-1-add-flutteractivity-to-androidmanifest-xml",
        "convert-the-http-response-to-an-album",
        "provider-of",
        "3-convert-the-response-into-a-custom-dart-object",
        "recipes",
        "recipes-1",
        "my-id",
    ]
    assert chunks[4].section_path[-1] == "Recipes"  # attribute removed from the heading text
