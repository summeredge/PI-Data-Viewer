# PI Data Viewer

## 项目简介

PI Data Viewer 是用于PI历史数据可视化展示的工程工具。

## 当前状态

Phase 1：

- 项目框架完成；
- Dash页面初始化；
- 等待PI读取模块开发。

当前版本只提供基础页面和模块占位接口，不包含 PI SDK、数据读取、图形分析或数据库功能。

## 技术栈

- Python
- Dash
- Plotly
- pandas

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
├── backend/
├── charts/
├── layout/
├── export/
├── tests/
└── requirements.txt
```
