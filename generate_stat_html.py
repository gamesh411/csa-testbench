#!/usr/bin/env python2
import json
import os
import re
from cgi import escape
from collections import defaultdict, OrderedDict
from datetime import timedelta
from difflib import SequenceMatcher

# Credits:
# https://stackoverflow.com/questions/6190331/how-to-implement-an-ordered-default-dict
class OrderedDefaultDict(OrderedDict, defaultdict):
    def __init__(self, default_factory=None, *args, **kwargs):
        super(OrderedDefaultDict, self).__init__(*args, **kwargs)
        self.default_factory = default_factory

try:
    import plotly.offline as py
    import plotly.graph_objs as go
    CHARTS_SUPPORTED = True
except ImportError:
    CHARTS_SUPPORTED = False

HEADER = """
<!DOCTYPE html>
<html lang="en">
<head>
  <title>Detailed Statistics</title>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css"
        integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T"
        crossorigin="anonymous">
  <script src="https://code.jquery.com/jquery-3.3.1.slim.min.js"
          integrity="sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo"
          crossorigin="anonymous"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.14.7/umd/popper.min.js"
          integrity="sha384-UO2eT0CpHqdSJQ6hJty5KVphtPhzWj9WO1clHTMGa3JDZwrnQq4sF86dIHNDz0W1"
          crossorigin="anonymous"></script>
  <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/js/bootstrap.min.js"
          integrity="sha384-JjSmVgyd0p3pXB1rRibZUAYoIIy6OrQ6VrjIEaFf/nJGzIxFDsf4x0xIM+B07jRM"
          crossorigin="anonymous"></script>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
  <script type="text/javascript">
      // Reload Poltly graphs on tab change.
      $(document).ready(function () {
          $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
              var target = $(e.target).attr("href");
              var toRemove = [];
              var toAppend = [];
              $(target).find("SCRIPT").each(function (index, element) {
                  var script = document.createElement('script');
                  script.type = 'text/javascript';
                  script.text = element.text
                  toRemove.push(element);
                  toAppend.push(script);
              });
              toRemove.forEach(function (item) {
                  item.remove();
              });
              toAppend.forEach(function (item) {
                  $(target).append(item);
              });
              $(target).find("DIV").each(function (index, element) {
                   if (element.className.includes("plotly-graph-div")) {
                       Plotly.relayout(element, {height: 500});
                   }
               });
          })
      });
  </script>
  <style> .tab-content { padding: 10px; } </style>
</head>
<body>
<div class="jumbotron text-center">
  <h1>Detailed Static Analyzer Statistics</h1>
</div>
<div class="container">
"""

FOOTER = """
</div>
</div>
<footer>
  <div class="container-fluid bg-light p-3 mb-2">
    <span class="text-muted">This report is created by the
      <a href="https://github.com/Xazax-hun/csa-testbench">CSA-Testbench</a> toolset.</span>
  </div>
</footer>
</body>
</html>
"""


def longest_match(a, b):
    return SequenceMatcher(None, a, b).\
        find_longest_match(0, len(a), 0, len(b)).size


def sort_keys_by_similarity(keys):
    """
    Sort keys by simialrity. This is an approximation of the
    optimal order. For each insertion to an intermediate list we
    calculate a score and choose the best insertion. The score also
    have a penalty part if the insertion reduces the similarity of
    the neighbours.
    """
    result = []
    for key in keys:
        index = 0
        max_score = -1000
        for j in range(len(result)+1):
            score = 0
            if j < len(result):
                score += longest_match(key, result[j])
            if j > 0:
                score += longest_match(key, result[j-1])
            if 0 < j < len(result):
                score -= longest_match(result[j], result[j-1])
            if score > max_score:
                max_score = score
                index = j
        result.insert(index, key)
    return result


# FIXME: Escape strings.
class HTMLPrinter(object):

    def __init__(self, path, config):
        self.html_path = path
        self.charts = config.get("charts", ["Duration", "Result count"])
        self.excludes = ["TU times"]
        self.as_comment = ["Analyzer version"]
        self.projects = OrderedDict()
        with open(self.html_path, 'w') as stat_html:
            stat_html.write(HEADER)
            stat_html.write("<!-- %s -->\n" %
                            escape(json.dumps(config)))
            # Generate nav bar.
            stat_html.write('<nav>\n<div class="nav nav-tabs" '
                            'id="nav-tab" role="tablist">\n')
            active = "active"
            for project in config["projects"]:
                name = escape(project["name"])
                text = '<a class="nav-item nav-link {0}" id="nav-{1}-tab"' \
                       ' data-toggle="tab" href="#nav-{1}" role="tab"' \
                       ' aria-controls="nav-{1}" aria-selected="{2}">{1}</a>' \
                    .format(active, name, active != "")
                stat_html.write(text)
                active = ""
            text = '<a class="nav-item nav-link" id="nav-charts-tab"' \
                   ' data-toggle="tab" href="#nav-charts" role="tab"' \
                   ' aria-controls="nav-charts" aria-selected="false">' \
                   'Charts</a>'
            stat_html.write(text)
            stat_html.write('</div>\n</nav>\n')
            stat_html.write('<div class="tab-content" id="nav-tabContent">\n')

    def finish(self):
        with open(self.html_path, 'a') as stat_html:
            self._generate_charts(stat_html)
            stat_html.write(FOOTER)

    def extend_with_project(self, name, data):
        first = len(self.projects) == 0
        self.projects[name] = data
        stat_html = open(self.html_path, 'a')
        keys = set()
        configurations = list()
        for configuration, val in data.items():
            configurations.append(configuration)
            for stat_name in val:
                keys.add(stat_name)
        keys = sort_keys_by_similarity(keys)

        tab = '<div class="tab-pane fade {0}" ' \
              'id="nav-{1}" role="tabpanel" aria-labelledby="nav-{1}-tab">\n'\
            .format("show active" if first else "", escape(name))
        stat_html.write(tab)
        stat_html.write('<table class="table table-bordered '
                        'table-striped table-sm">\n')
        stat_html.write('<thead class="thead-dark">')
        stat_html.write("<tr>\n")
        stat_html.write("<th>Statistic Name</th>")
        for conf in configurations:
            stat_html.write("<th>%s</th>" % escape(conf))
        stat_html.write("</tr>\n")
        stat_html.write('</thead>\n')
        stat_html.write('<tbody>\n')

        for stat_name in keys:
            if stat_name in self.excludes or \
               stat_name in self.as_comment:
                continue
            stat_html.write("<tr>\n")
            stat_html.write("<td>%s</td>" % escape(stat_name))
            for conf in configurations:
                val = str(data[conf].get(stat_name, '-'))
                stat_html.write("<td>%s</td>" % val)
            stat_html.write("</tr>\n")
        stat_html.write('</tbody>\n')
        stat_html.write("</table>\n\n")

        # Output some values as comments.
        for stat_name in self.as_comment:
            for conf in configurations:
                val = str(data[conf].get(stat_name, '-'))
                stat_html.write("<!-- %s[%s]=%s -->\n" %
                                (escape(conf), escape(stat_name), escape(val)))

        HTMLPrinter._generate_time_histogram(stat_html, configurations, data)
        stat_html.write('</div>\n')
        stat_html.close()

    @staticmethod
    def _generate_time_histogram(stat_html, configurations, data):
        if not CHARTS_SUPPORTED:
            return
        traces = []
        for conf in configurations:
            if "TU times" in data[conf]:
                if not data[conf]["TU times"]:
                    continue
                traces.append(go.Histogram(x=data[conf]["TU times"],
                                           name=conf))
        if not traces:
            return
        layout = go.Layout(barmode='overlay')
        fig = go.Figure(data=traces, layout=layout)
        div = py.plot(fig, show_link=False, include_plotlyjs=False,
                      output_type='div', auto_open=False)
        stat_html.write("<h3>Time per TU histogram</h3>\n")
        stat_html.write(div)

    def _get_color(self, config_name):
        if config_name.startswith('base'):
            return '#7293cb'

        if config_name.startswith('ctu'):
            return '#e1974c'

        if config_name.startswith('odm'):
            return '#84ba5b'

        return '#808585'

    def _generate_charts(self, stat_html):
        stat_html.write('<div class="tab-pane fade" id="nav-charts"'
                        ' role="tabpanel" aria-labelledby="nav-charts-tab">\n')
        if not CHARTS_SUPPORTED:
            stat_html.write("<p>Charts not supported."
                            "Install Plotly python library.</p>\n</div>\n")
            return

        for chart in self.charts:
            names = OrderedDefaultDict(list)
            values = OrderedDefaultDict(list)
            for project, data in self.projects.items():
                for configuration, stats in data.items():
                    values[configuration].append(
                        HTMLPrinter._get_chart_value(stats.get(chart, 0)))
                    names[configuration].append(project)

            # Skip empty charts.
            if all([all([x == 0 for x in values[conf]]) for conf in names]):
                continue

            yaxis_type = 'log' if chart == 'Disk usage' else '-'

            layout = go.Layout(yaxis=go.layout.YAxis(title=chart, type=yaxis_type),
                   xaxis=go.layout.XAxis(title='Methods'),
                   barmode='group',
                   bargap=0.15,
                   bargroupgap=0.1)

            fig = go.Figure(layout=layout)

            for conf, project in names.items():
                color = self._get_color(conf)
                fig.add_trace(go.Bar(x=names[conf], y=values[conf], text=values[conf], textposition='outside', texttemplate='%{text:.3s}', marker_color=color, name=conf))

            chart_directory = os.path.dirname(self.html_path)

            chart_file = chart.replace('#', 'number').replace('%', 'percent')
            chart_file = re.sub(r'[^a-zA-Z0-9\.\-]', '_', chart_file) + '.pdf'

            image_path = os.path.join(chart_directory, chart_file)
            fig.write_image(image_path)

            div = py.plot(fig, show_link=False, include_plotlyjs=False,
                          output_type='div', auto_open=False)
            stat_html.write("<h2>%s</h2>\n" % escape(chart))
            stat_html.write(div)

        stat_html.write("</div>\n")

    @staticmethod
    def _get_chart_value(value):
        if isinstance(value, timedelta):
            return value.seconds
        return float(value)
