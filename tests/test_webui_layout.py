"""WebUI 布局契约：这些 CSS 取值一旦回退，界面缺陷会重新出现。"""

from pathlib import Path


STYLES = (Path(__file__).parents[1] / "assets" / "styles.css").read_text(
    encoding="utf-8"
)


def test_root_overflow_x_uses_clip_so_sticky_panel_works():
    # overflow-x: hidden 会让 html/body 成为滚动容器，
    # .parameter-panel 的 position: sticky 完全失效（实测随页面滚走）。
    assert "overflow-x: clip;" in STYLES
    assert "overflow-x: hidden;" not in STYLES


def test_statistics_cards_use_auto_fit_columns():
    # 卡片内数值列固定 90px；固定 4 列在窄内容区会把数值挤到 ~42px。
    assert "repeat(auto-fit, minmax(240px, 1fr))" in STYLES


def test_capability_spec_inputs_are_laid_out_in_a_grid():
    # LSL/USL 曾是 block 流，各占满 1113px 整行。
    assert ".capability-specification-controls {" in STYLES
    assert "grid-template-columns: repeat(2, 180px);" in STYLES
