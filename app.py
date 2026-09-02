from dash import Dash, html


app = Dash(__name__)
app.title = "PI Data Viewer"
app.layout = html.Div(
    [
        html.H1("PI Data Viewer"),
        html.Div(
            [
                html.Aside(
                    [
                        html.H2("Parameters"),
                        html.P("Parameter area placeholder"),
                    ],
                    style={
                        "borderRight": "1px solid #d9d9d9",
                        "padding": "1rem",
                        "width": "240px",
                    },
                ),
                html.Main(
                    [
                        html.H2("Chart Area"),
                        html.P("Chart area placeholder"),
                    ],
                    style={"flex": "1", "padding": "1rem"},
                ),
            ],
            style={"display": "flex", "minHeight": "400px"},
        ),
    ],
    style={"fontFamily": "Arial, sans-serif", "margin": "2rem"},
)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
