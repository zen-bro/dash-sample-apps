import dash
from dash.dependencies import Input, Output, State
import dash_html_components as html
import dash_core_components as dcc
import dash_bootstrap_components as dbc
import dash_table
from dash_table.Format import Format
import plotly.express as px
import plotly.graph_objs as go
import datashader as ds

import numpy as np
from skimage import io, filters, measure
import pandas as pd

import PIL
from skimage import color, img_as_ubyte
from plotly import colors

import base64
import xarray as xr

external_stylesheets = [dbc.themes.BOOTSTRAP]

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server

# Read the image that will be segmented
filename = (
    "https://upload.wikimedia.org/wikipedia/commons/a/ac/Monocyte_no_vacuoles.JPG"
)
img = io.imread(filename, as_gray=True)[:660:2, :800:2]
label_array = measure.label(img < filters.threshold_otsu(img))
current_labels = np.unique(label_array)[np.nonzero(np.unique(label_array))]
# Compute and store properties of the labeled image
prop_names = [
    "label",
    "area",
    "perimeter",
    "eccentricity",
    "euler_number",
    "mean_intensity",
]
prop_table = measure.regionprops_table(
    label_array, intensity_image=img, properties=prop_names
)
table = pd.DataFrame(prop_table)
# Format the Table columns
columns = [
    {"name": label_name, "id": label_name}
    if precision is None
    else {
        "name": label_name,
        "id": label_name,
        "type": "numeric",
        "format": Format(precision=precision),
    }
    for label_name, precision in zip(prop_names, (None, None, 4, 4, None, 3))
]
img = img_as_ubyte(color.gray2rgb(img))
img = PIL.Image.fromarray(img)


def image_with_contour(img, active_labels, data_table, mode="lines", shape=None):
    """
    Figure with contour plot of labels superimposed on background image.

    Parameters
    ----------
    img : URL, dataURI or ndarray
        Background image. If a numpy array, it is transformed into a PIL
        Image object.
    active_labels : list
        the currently visible labels in the datatable
    data_table : pandas.DataFrame
        the currently visible entries of the datatable
    shape: tuple, optional
        Shape of the arrays, to be provided if ``img`` is not a numpy array.
    """
    try:
        sh_y, sh_x = shape if shape is not None else img.shape
    except AttributeError:
        print(
            """the shape of the image must be provided with the
                 ``shape`` parameter if ``img`` is not a numpy array"""
        )
    if type(img) == np.ndarray:
        img = img_as_ubyte(color.gray2rgb(img))
        img = PIL.Image.fromarray(img)
    # Filter the label array based on the currently visible labels
    mask = np.in1d(label_array.ravel(), active_labels, invert=True).reshape(
        label_array.shape
    )
    masked_labels = np.ma.masked_where(mask, label_array)

    print("mode is", mode)
    opacity = 0.4 if mode is None else 1

    fig = px.imshow(img, binary_string=True, binary_backend="jpg")
    # Overlay the current labels
    _, hex_list = zip(*colors.PLOTLY_SCALES["Viridis"])
    label_data_array = xr.DataArray(np.flipud(masked_labels))
    label_multi_byte = ds.transfer_functions.shade(
        label_data_array, cmap=list(hex_list)
    ).to_bytesio()
    label_multi_enc = base64.b64encode(label_multi_byte.getvalue()).decode()
    label_multi_str = "data:image/png;base64,{}".format(label_multi_enc)

    fig.add_image(colormodel="rgba", source=label_multi_str, opacity=opacity)

    # Overlay the colored label info with a hidden (opaque) scatter trace to display hoverinfo
    # see also: https://scikit-image.org/docs/dev/auto_examples/segmentation/plot_regionprops.html#sphx-glr-auto-examples-segmentation-plot-regionprops-py
    overlay_columns = data_table.columns[1:]
    for rid, row in data_table.iterrows():
        label = row.label
        contour = measure.find_contours(label_array == label, 0.5)[0]
        y, x = contour.T
        hoverinfo = "<br>".join(
            [
                f"{prop_name}: {prop_val:.3f}"
                if np.issubdtype(type(prop_val), "float")
                else f"{prop_name}: {prop_val:d}"
                for prop_name, prop_val in row[overlay_columns].iteritems()
            ]
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                opacity=0,
                name=label,
                mode="lines",
                line=dict(color="grey"),
                fill="toself",
                showlegend=False,
                hovertemplate=hoverinfo,
                hoveron="points+fills",
            )
        )

    # Remove axis ticks and labels and have the image fill the container
    fig.update_layout(margin=dict(l=0, r=0, b=0, t=0, pad=0),)
    fig.update_xaxes(showticklabels=False).update_yaxes(showticklabels=False)

    return fig


# Define Modal
howto = """
    Hover over objects to highlight their properties in the table,
    select cell in table to highlight object in image, or
    filter objects in the table to display a subset of objects.

    Learn more about [DataTable filtering syntax](https://dash.plot.ly/datatable/filtering)
    for selecting ranges of properties.
    """
modal = dbc.Modal(
    [
        dbc.ModalHeader("How to use this app"),
        dbc.ModalBody(
            dbc.Row(
                dbc.Col(
                    [
                        dcc.Markdown(howto, id="howto-md"),
                        html.Img(
                            id="help",
                            src="assets/properties.gif",
                            width="80%",
                            style={
                                "border": "2px solid black",
                                "display": "block",
                                "margin-left": "auto",
                                "margin-right": "auto",
                            },
                        ),
                    ]
                )
            )
        ),
        dbc.ModalFooter(dbc.Button("Close", id="howto-close", className="howto-bn",)),
    ],
    id="modal",
    size="lg",
    style={"font-size": "small"},
)

# Buttons
button_gh = dbc.Button(
    "Learn more",
    id="howto-open",
    outline=True,
    color="secondary",
    # Turn off lowercase transformation for class .button in stylesheet
    style={"textTransform": "none"},
)

button_howto = dbc.Button(
    "View Code on github",
    outline=True,
    color="primary",
    href="https://github.com/plotly/dash-sample-apps/tree/master/apps/dash-image-annotation",
    id="gh-link",
    style={"text-transform": "none"},
)

# Define Header Layout
header = dbc.Navbar(
    dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(
                        html.A(
                            html.Img(
                                src=app.get_asset_url("dash-logo-new.png"),
                                height="30px",
                            ),
                            href="https://plotly.com/dash/",
                        )
                    ),
                    dbc.Col(dbc.NavbarBrand("Object Properties App")),
                    modal,
                ],
                align="center",
            ),
            dbc.Row(
                dbc.Col(
                    [
                        dbc.NavbarToggler(id="navbar-toggler"),
                        dbc.Collapse(
                            dbc.Nav(
                                [dbc.NavItem(button_howto), dbc.NavItem(button_gh)],
                                className="ml-auto",
                                navbar=True,
                            ),
                            id="navbar-collapse",
                            navbar=True,
                        ),
                    ]
                ),
                align="center",
            ),
        ],
        fluid=True,
    ),
    color="dark",
    dark=True,
)

# Define Cards
image_card = dbc.Card(
    [
        dbc.CardHeader(html.H2("Explore object properties")),
        dbc.CardBody(
            dbc.Row(
                dbc.Col(
                    dcc.Graph(
                        id="graph",
                        figure=image_with_contour(
                            img, current_labels, table, mode=None
                        ),
                    )
                )
            )
        ),
    ]
)

table_card = dbc.Card(
    [
        dbc.CardHeader(html.H2("Data Table")),
        dbc.CardBody(
            dbc.Row(
                dbc.Col(
                    [
                        dash_table.DataTable(
                            id="table-line",
                            columns=columns,
                            data=table.to_dict("records"),
                            filter_action="native",
                            row_deletable=True,
                            style_table={"overflowY": "scroll"},
                            fixed_rows={"headers": False, "data": 0},
                            style_cell={"width": "85px"},
                        ),
                        dcc.Store(id="cache-label-list", data=current_labels),
                        html.Div(id="row", hidden=True, children=None),
                    ]
                )
            )
        ),
    ]
)

app.layout = html.Div(
    [
        header,
        dbc.Container(
            [dbc.Row([dbc.Col(image_card, md=5), dbc.Col(table_card, md=7)])],
            fluid=True,
        ),
    ]
)


@app.callback(
    Output("table-line", "style_data_conditional"),
    [Input("graph", "hoverData")],
    prevent_initial_call=True,
)
def higlight_row(string):
    """
    When hovering hover label, highlight corresponding row in table,
    using label column.
    """
    index = string["points"][0]["curveNumber"]
    return [
        {
            "if": {"filter_query": "{label} eq %d" % index},
            "backgroundColor": "#3D9970",
            "color": "white",
        }
    ]


@app.callback(
    [
        Output("graph", "figure"),
        Output("cache-label-list", "data"),
        Output("row", "children"),
    ],
    [
        Input("table-line", "derived_virtual_indices"),
        Input("table-line", "active_cell"),
        Input("table-line", "data"),
    ],
    [State("cache-label-list", "data"), State("row", "children"),],
    prevent_initial_call=True,
)
def highlight_filter(indices, cell_index, data, active_labels, previous_row):
    """
    Updates figure and labels array when a selection is made in the table.

    When a cell is selected (active_cell), highlight this particular label
    with a red outline.

    When the set of filtered labels changes, or when a row is deleted.
    """
    _table = pd.DataFrame(data)
    if cell_index and cell_index["row"] != previous_row:
        label = indices[cell_index["row"]] + 1
        mask = (label_array == label).astype(np.float)
        fig = image_with_contour(img, active_labels, _table, mode=None)
        # Add the outline of the selected label as a contour to the figure
        fig.add_contour(
            z=mask,
            contours=dict(coloring="lines"),
            showscale=False,
            line=dict(width=6),
            colorscale="YlOrRd",
            opacity=0.8,
            hoverinfo="skip",
        )
        return [fig, active_labels, cell_index["row"]]
    filtered_labels = _table.loc[indices, "label"].values
    fig = image_with_contour(img, filtered_labels, _table, mode=None)
    return [fig, filtered_labels, previous_row]


@app.callback(
    Output("modal", "is_open"),
    [Input("howto-open", "n_clicks"), Input("howto-close", "n_clicks")],
    [State("modal", "is_open")],
)
def toggle_modal(n1, n2, is_open):
    if n1 or n2:
        return not is_open
    return is_open


# we use a callback to toggle the collapse on small screens
@app.callback(
    Output("navbar-collapse", "is_open"),
    [Input("navbar-toggler", "n_clicks")],
    [State("navbar-collapse", "is_open")],
)
def toggle_navbar_collapse(n, is_open):
    if n:
        return not is_open
    return is_open


if __name__ == "__main__":
    app.run_server(debug=True)
