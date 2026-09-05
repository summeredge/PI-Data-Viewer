# Learnings

## [LRN-20260905-001] 重复 Dash 区块必须用唯一锚点补丁

**Priority**: medium
**Status**: resolved
**Area**: tools

### 内容
在多个 Tab 和 callback 具有相似结构时，以通用 `html.P` 或 `Input("variable-selector")` 为上下文的补丁可能落到 Box Plot 或 Trend。新增控件后必须按唯一组件 ID 或 callback Output 定位，并检查 callback map 的实际输入。

### 建议修复
补丁使用 `label="Control Chart"`、`Output("control-chart-graph", ...)` 等唯一锚点；随后用 `rg` 检查落点，并为 callback 输入列表保留回归测试。

### 元数据
- Source: error
- See Also: none

---

## [LRN-20260905-002] Minitab I-MR 判异规则边界

**Priority**: medium
**Status**: resolved
**Area**: tools

### 内容
Minitab I-MR 默认仅启用 Test 1；I 图可选 Test 1–8，MR 图仅应用 Test 1–4。连续点规则在完成窗口的点发出信号，缺失值必须打断窗口；所有规则在完整序列上计算后再投影到显示采样点。

### 建议修复
保持 Test 1 默认值；统一返回逐规则布尔序列，图层显示触发编号，并将所有信号点纳入有界显示采样。

### 元数据
- Source: task_review
- See Also: LRN-20260904-002

---

## [LRN-20260904-001] Dash 下拉控件的实际高度

**Priority**: low
**Status**: resolved
**Area**: tools

### 内容
Dash 4 的 `dcc.Dropdown` 组件配置中的高度不一定直接作用于实际渲染的下拉根节点；需要在所属页面范围内用 CSS 选择器补充 `height` 和 `min-height`，才能保证盒模型尺寸一致。

### 建议修复
涉及控件尺寸时，同时检查浏览器实际盒模型，不要只验证 Dash layout JSON 中的 `style` 属性。

### 元数据
- Source: task_review
- See Also: none

---

## [LRN-20260904-002] I-MR 控制限与显示采样分离

**Priority**: medium
**Status**: resolved
**Area**: tools

### 内容
I-MR 的均值、移动极差和控制限必须基于完整有效序列计算；浏览器显示点只作为最后一步采样，并保留异常点索引，避免大数据量绘图改变控制结果或隐藏异常。

### 建议修复
把完整计算结果与 display series 分开传递；任何降采样都不能重新计算 `X̄`、`MR̄` 或控制限。

### 元数据
- Source: task_review
- See Also: none

---

## [LRN-20260903-001] Dash 4.4.1 原生文件控件

**Priority**: medium
**Status**: resolved
**Area**: tools

### 内容
Dash 4.4.1 的 `dash.html` 没有 `Input` 组件，不能直接用 `html.Input(type="file")` 渲染原生文件选择器。需要通过 Dash assets 注入可见的 `input[type="file"]`，再由 clientside callback 读取 `File` 对象并提交 multipart 请求。

### 建议修复
涉及本地文件上传时，先检查当前 Dash 版本的 HTML 组件清单；不要把 `dcc.Upload` 的 Base64 内容作为生产上传链路，也不要假设 `html.Input` 始终存在。

### 元数据
- Source: task_review
- See Also: ERR-20260902-001

---
