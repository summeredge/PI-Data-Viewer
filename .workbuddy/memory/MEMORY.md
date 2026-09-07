# PI Data Viewer — 长期项目笔记

## 技术栈基线
- Python 3.11.9，Dash 4.4.1 + Plotly 7.0.0 + pandas/numpy/scipy。
- venv：`C:/Users/shaoy/Documents/PythonEnvs/pi-data-viewer/Scripts/python.exe`。
- 启动：`app.py`；默认监听 127.0.0.1:8050。

## Plotly 7 子图列宽陷阱（2026-09 复盘）
- 仅靠外层 Div 的 `width:N%` 不能保证每个箱子宽度恒定：当 `make_subplots` 只有一个子图（cols=1）时，y 轴 tick 文字宽度会「吃进」绘图区，位号越多 y 轴越宽，每个箱体相对越宽。
- 正确做法：固定 `cols=MAX_TAGS`、`column_widths=[1/MAX_TAGS]*MAX_TAGS`，并把未使用的 subplot 行/列 `visible=False` 隐藏。每个 subplot 列宽即 1/MAX_TAGS，与数据轴无关。
- 活动 x/y 轴要显式 `visible=True`（否则 `layout.xaxis.visible` 返回 `None`，影响断言与 JS 状态查询）。

## Dash 4 DOM 关键类名（2026-09）
- `dcc.Input`：`className` 落在容器 `div.dash-input-container`，内层 `input.dash-input-element` 自带 padding。
- `dcc.Dropdown` 根：`.dash-dropdown-wrapper`；触发器 `<button class="dash-dropdown">`；菜单 Radix Popover。**旧 react-select v1 的 `.Select-control` / `.is-disabled` 已失效**。
- `dcc.Checklist` / `RadioItems`：选项为 `<label class="dash-options-list-option">`；行内变体 `optionClassName: "dash-checklist-inline"` / `"dash-radioitems-inline"`。
- `dcc.Tabs` 容器：`<div.tab-parent> <div.tab-container> <div.tab> </div>* </div> <div.tab-content>`，渲染为**普通 div、无 role/tabIndex**——键盘可达性必须 JS 补齐。
- `dcc.Tabs.mobile_breakpoint` 默认 **800**，以下 tab 变纵向堆叠。

## 测试运行注意
- 本机沙箱有 `safe-delete` shim：pytest 临时目录 `C:\Users\shaoy\AppData\Local\Temp\...` 的清理可能被批量阻断（`SAFE_DELETE_BULK_REJECTED` / `FAIL_CLOSED`），这是**清理告警，不是测试失败**。
- 规避：指定 `--basetemp=.pytest_tmp`（项目内子目录）；运行结束手动 `rm -rf .pytest_tmp`。
- 不在 hot-path 改 `backend/`、`charts/` 业务算法；UI 改动必须回归 `tests/test_boxplot.py`、`tests/test_scatter_matrix.py`、`tests/test_control_chart.py`、`tests/test_trend_statistics.py`。

## 项目约定
- **不动「基础统计」卡片网格**（用户特别声明「这是我特殊设计的」）；状态标签仅做视觉语义强化，不改文案逻辑。
- 工具结构统一为 `src/tools/<id>/{index,logic,view,bind}.ts` 的思路，在 PI Data Viewer 里体现为 `charts/<feature>.py` + `pages/viewer.py` 回调 + 静态 `assets/styles.css`，不在 `app.py` 加 if/switch。
- 严格遵守「不复制」原则：实现按公开标准（IAPWS-IF97、IEC 60534-2-1、IEC 61131、Emerson/Spirax Sarco 手册、Colebrook-White/Swamee-Jain 等）核对，不照搬第三方代码/文本/数据表。