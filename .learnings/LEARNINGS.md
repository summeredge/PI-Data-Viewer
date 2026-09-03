# Learnings

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
