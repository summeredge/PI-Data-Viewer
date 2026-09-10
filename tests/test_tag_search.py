from dash import no_update

from pages import viewer


def _component_ids(value):
    if hasattr(value, "to_plotly_json"):
        value = value.to_plotly_json()
    if isinstance(value, dict):
        props = value.get("props", {})
        if isinstance(props, dict) and props.get("id"):
            yield props["id"]
        children = props.get("children") if isinstance(props, dict) else None
        for child in children if isinstance(children, (list, tuple)) else [children]:
            if child is None:
                continue
            yield from _component_ids(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _component_ids(child)


def test_tag_search_layout_has_modal_controls():
    ids = set(_component_ids(viewer.layout))

    assert {
        "open-tag-search-button",
        "tag-search-modal",
        "tag-search-mask",
        "tag-search-button",
        "tag-search-results",
        "add-tag-search-button",
        "close-tag-search-button",
        "tag-search-status",
    }.issubset(ids)


def test_tag_search_modal_opens_and_closes(monkeypatch):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "open-tag-search-button")
    opened = viewer.manage_tag_search(1, 0, 0, 0, None, [], "A.PV")
    assert opened[0] == {"display": "flex"}

    monkeypatch.setattr(viewer, "_triggered_id", lambda: "close-tag-search-button")
    closed = viewer.manage_tag_search(1, 0, 0, 1, None, [], "A.PV")
    assert closed[0] == {"display": "none"}


def test_tag_search_displays_results_and_supports_multi_select(monkeypatch):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "tag-search-button")
    monkeypatch.setattr(viewer, "search_pi_tags", lambda mask: ["A.PV", "B.PV"])
    searched = viewer.manage_tag_search(0, 1, 0, 0, "FIC*", [], "A.PV")

    assert searched[1] == [
        {"label": "A.PV", "value": "A.PV"},
        {"label": "B.PV", "value": "B.PV"},
    ]
    assert searched[2] == []
    assert searched[4] == "找到 2 个位号"

    monkeypatch.setattr(viewer, "_triggered_id", lambda: "add-tag-search-button")
    added = viewer.manage_tag_search(0, 1, 1, 0, "FIC*", ["B.PV", "C.PV"], "A.PV")
    assert added[2] == []
    assert added[3] == "A.PV\nB.PV\nC.PV"
    assert added[4] == "已添加选中位号"


def test_tag_search_handles_empty_and_failed_results(monkeypatch):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "tag-search-button")
    monkeypatch.setattr(viewer, "search_pi_tags", lambda mask: [])
    empty = viewer.manage_tag_search(0, 1, 0, 0, "NOT_EXIST_*", [], None)
    assert empty[1] == []
    assert empty[4] == "未找到匹配的位号"

    def fail_search(mask):
        raise RuntimeError("PI server unavailable")

    monkeypatch.setattr(viewer, "search_pi_tags", fail_search)
    failed = viewer.manage_tag_search(0, 2, 0, 0, "FIC*", [], None)
    assert failed[4] == "搜索失败：PI server unavailable"


def test_tag_search_respects_eight_tag_limit(monkeypatch):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "add-tag-search-button")
    current = "\n".join(f"TAG{index}.PV" for index in range(8))
    result = viewer.manage_tag_search(0, 0, 1, 0, None, ["TAG8.PV"], current)

    assert result[3] is no_update
    assert result[4] == "最多支持8个位号"
