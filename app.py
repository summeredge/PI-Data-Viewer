from dash import Dash

from pages.viewer import layout, register_callbacks

app = Dash(__name__)
app.title = "PI Data Viewer"
app.layout = layout
register_callbacks(app)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
