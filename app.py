from pathlib import Path
from tempfile import NamedTemporaryFile

from dash import Dash
from flask import jsonify, request
from werkzeug.utils import secure_filename

from backend.dataframe_store import store_dataframe
from backend.file_reader import read_local_file
from pages.viewer import layout, register_callbacks


_SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}

app = Dash(__name__)
app.title = "PI Data Viewer"
app.layout = layout
register_callbacks(app)


@app.server.route("/api/upload", methods=["POST"])
def upload_file():
    upload = request.files.get("file")
    filename = str(upload.filename or "") if upload is not None else ""
    suffix = Path(filename).suffix.lower()
    if upload is None or not filename:
        return jsonify({"ok": False, "error": "请选择文件"}), 400
    if suffix not in _SUPPORTED_EXTENSIONS:
        return jsonify({"ok": False, "error": "不支持的文件类型，仅支持 .csv 和 .xlsx"}), 400

    safe_filename = secure_filename(filename) or f"upload{suffix}"
    temp_path = None
    try:
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
            temp_path = Path(temporary_file.name)
        upload.save(temp_path)
        frame = read_local_file(temp_path)
        store_dataframe(frame)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "上传文件失败"}), 500
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return jsonify(
        {
            "ok": True,
            "filename": safe_filename,
            "rows": len(frame),
            "columns": [str(column) for column in frame.columns],
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
