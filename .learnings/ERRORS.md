# Errors

## [ERR-20260904-001] PowerShell 变量赋值调用语法错误

**Priority**: low
**Status**: resolved
**Area**: tools

### 摘要
环境校验命令把 PowerShell 变量赋值写成了调用表达式，导致解释器和依赖检查未执行。

### 错误信息
```text
The expression after '&' in a pipeline element produced an object that was not valid.
```

### 上下文
- 在 PI Data Viewer 中准备使用项目专用 Python 解释器运行测试。
- 错误写法为 `& $python = '...'; & $python -c ...`。

### 建议修复
先用 `$python = '...'` 赋值，再单独使用 `& $python -c ...` 调用解释器。

### 元数据
- Reproducible: yes
- See Also: none

---

## [ERR-20260904-002] 项目虚拟环境首次启动权限错误

**Priority**: low
**Status**: resolved
**Area**: tools

### 摘要
创建项目专用 Python 3.11 环境时，首次启动其 Scripts/python.exe 被系统拒绝；授权上下文下重试后可正常运行。

### 错误信息
```text
[Errno 13] Permission denied: 'C:\\Users\\shaoy\\Documents\\PythonEnvs\\pi-data-viewer\\Scripts\\python.exe'
Unable to create process using '"C:\\Users\\shaoy\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" -m pip list'
```

### 上下文
- PI Data Viewer 没有现成受控环境，需要在 `C:\Users\shaoy\Documents\PythonEnvs` 下创建项目环境。
- 目录和依赖已生成；使用项目环境解释器的授权上下文验证并运行测试成功。

### 建议修复
先区分 venv 创建失败与解释器执行权限问题；保留项目环境，使用同一环境解释器重试，不切换到 Codex bundled Python。

### 元数据
- Reproducible: unknown
- See Also: none

---

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
