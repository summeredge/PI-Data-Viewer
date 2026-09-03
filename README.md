# PI Data Viewer

## 项目简介

PI Data Viewer 是用于PI历史数据可视化展示的工程工具。

## 当前状态

Phase 4：

- 项目框架完成；
- Dash页面初始化；
- 独立 PIReader C# 后端完成；
- Python PI Reader 适配接口完成；
- 支持最多 8 个 PI Tag 的时间范围查询；
- 支持 CSV 和 Excel `.xlsx` 本地文件导入；
- 支持 Plotly 多曲线趋势图和基础统计表；
- PI Server 与本地文件都通过 `backend/dataframe_store.py` 在趋势图和统计模块之间流转。

当前版本提供基础页面和 PI Reader 适配接口，不在 Viewer 内重复实现 PI SDK 或 PI 连接配置。

PIReader 使用 PIExport 兼容的 `config.txt`，但 Viewer 不再启动 `PIExport.exe`。运行前设置：

```powershell
$env:PI_CONFIG = "C:\path\to\PIExport\config.txt"
$env:PI_READER_EXE = "C:\path\to\PIReader\PIReader.exe"
```

`PI_READER_EXE` 未设置时，Viewer 会在 `PI_CONFIG` 所在目录查找 `PIReader.exe`。
`PI_CONFIG` 指向现有 PIExport 格式的配置文件（`Server/User/Password/Interval/BlockDays`）；Viewer 只保存路径，不复制或写入 PI 密码和 Server 参数。
Viewer 每次请求只在临时目录生成 `tags.txt`，并通过 stdout 接收 PIReader JSON。

`PIReader/Program.cs` 是 PIReader 的唯一源码基线；`PIReader/PIReader.exe` 是本地构建产物，不是源码，已不纳入 Git 跟踪。修改 `Program.cs` 后必须在 Windows PI SDK 环境中重新运行 `PIReader\build.bat`。Web PI 模式必须使用与当前源码对应的 `PIReader.exe`；缺少该文件时 `start.bat` 仍可启动 CSV/Excel Viewer，但 PI 模式需要先构建。

PIReader 的 C# 项目和不连接 PI Server 的协议测试分别位于 `PIReader/` 和 `PIReader.Tests/`。项目引用安装环境提供的 `OSIsoft.PISDK`、`OSIsoft.PISDKCommon`、`OSIsoft.PITimeServer` interop，需在 Windows PI SDK 环境中用 .NET Framework/MSBuild 构建。

统一读取结果为以 `DatetimeIndex`（名称为 `Timestamp`）为索引、数值列为变量的 pandas DataFrame。PI Server 使用 `read_pi_data(tags, start_time, end_time, interval)`，采样间隔可选 `1m`、`5m`、`10m`、`30m`、`1h`；本地上传文件使用 `read_local_file(contents, filename)`。

## 技术栈

- Python
- Dash
- Plotly
- pandas
- openpyxl（`.xlsx` 读取）

## 运行

安装依赖：

```bash
python -m pip install -r requirements.txt
```

启动应用：

```bash
python app.py
```

浏览器访问 <http://127.0.0.1:8050>。

运行测试：

```bash
pytest
```

## 项目结构

```text
PI-Data-Viewer/
├── app.py
├── config/
├── PIReader/
├── PIReader.Tests/
├── backend/
├── charts/
├── layout/
├── pages/
├── export/
├── tests/
└── requirements.txt
```
