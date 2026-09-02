# Errors

## [ERR-20260902-001] In-app browser file chooser timeout

**Priority**: low
**Status**: resolved
**Area**: tools

### 摘要
本地 Dash 页面中直接点击 `input[type="file"]` 未触发浏览器文件选择事件，页面级上传验证因此超时中断。

### 错误信息
```text
Timed out after 3000ms waiting for file chooser.
```

### 上下文
- 在本地 PI Data Viewer 测试实例中使用浏览器文件上传流程。
- 直接点击隐藏文件输入后等待 file chooser。

### 建议修复
优先点击页面显示的“Choose File”控件，再等待并设置文件；若仍失败，先重新读取当前 DOM 状态。

### 元数据
- Reproducible: unknown
- See Also: none

---
