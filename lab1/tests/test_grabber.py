"""Grabber logic against a FAKE in-memory GitHub (see fakes.py)."""

from fakes import CONTENT, INCLUDES, FakeGitHub

from flutter_rag.grabber import glob_to_regex, grab, select_paths, url_for
from flutter_rag.runconfig import CorpusConfig

CORPUS = CorpusConfig(
    include=[CONTENT + "**/*.md"],
    exclude=[CONTENT + "**/_*.md", CONTENT + "release/release-notes/**"],
    skip_front_matter={"noindex": True, "sitemap": False},
)


def test_glob_double_star_matches_any_depth():
    r = glob_to_regex(CONTENT + "**/_*.md")
    assert r.match(CONTENT + "_top.md")
    assert r.match(CONTENT + "add-to-app/android/_initial-route-cached-engine.md")
    assert not r.match(CONTENT + "add-to-app/android/add-flutter-screen.md")


def test_select_excludes_partials_release_notes_and_includes_dir():
    paths = [
        CONTENT + "ui/a.md",
        CONTENT + "ui/_partial.md",
        CONTENT + "release/release-notes/x.md",
        INCLUDES + "docs/frag.md",
        CONTENT + "ui/img.png",
    ]
    assert select_paths(paths, CORPUS) == [CONTENT + "ui/a.md"]


def test_url_mapping():
    assert url_for("ui/layout/constraints") == "https://docs.flutter.dev/ui/layout/constraints"
    assert url_for("ui/navigation/index") == "https://docs.flutter.dev/ui/navigation"
    assert url_for("index") == "https://docs.flutter.dev/"


def files():
    return {
        CONTENT + "a.md": '---\ntitle: A\n---\nText A {% render "docs/frag.md" %}\n',
        CONTENT + "b.md": "---\ntitle: B\n---\nText B\n",
        CONTENT + "internal.md": "---\ntitle: I\nnoindex: true\n---\nSecret-ish\n",
        INCLUDES + "docs/frag.md": "Fragment\n",
    }


def test_grab_is_incremental_and_detects_changes(tmp_path):
    gh = FakeGitHub(files())
    r1 = grab(CORPUS, "t", tmp_path, gh)
    assert r1.diff.added == ["a", "b"]  # internal.md is skipped by front matter
    assert r1.manifest.documents["internal"].status == "skipped"
    assert r1.manifest.documents["a"].includes  # render dependency tracked
    first_downloads = gh.downloads
    assert first_downloads == 4

    r2 = grab(CORPUS, "t", tmp_path, gh)  # same snapshot again
    assert gh.downloads == first_downloads  # nothing re-downloaded
    assert r2.diff.unchanged == ["a", "b"] and not (r2.diff.added or r2.diff.modified)

    gh.files[INCLUDES + "docs/frag.md"] = "Fragment v2\n"  # only the fragment changes
    del gh.files[CONTENT + "b.md"]
    gh.commit = "c2"
    r3 = grab(CORPUS, "t", tmp_path, gh)
    assert r3.diff.modified == ["a"]
    assert r3.diff.deleted == ["b"]
    assert gh.downloads == first_downloads + 1
    assert (tmp_path / "manifests" / "t" / "c2.json").exists()
