import re
from bidict import bidict
import requests
import snappy
from flask import Flask, Response, request
from flask.logging import create_logger
from proto import remote_pb2
from dynatrace.entity_client import CachedEntityClient
from dynatrace.metrics_client import CachedMetricsClient

app = Flask(__name__)
app.config.from_pyfile('config.py')

log = create_logger(app)

dim_map = {}
dimension_name_bidict = bidict()

entity_client = CachedEntityClient(app.config['DT_TENANT'], app.config['DT_API_TOKEN'])
metrics_client = CachedMetricsClient(app.config['DT_TENANT'], app.config['DT_API_TOKEN'])

@app.route('/read', methods=["POST"])
def read():
    msg = remote_pb2.ReadRequest()
    msg.ParseFromString(snappy.uncompress(request.data))

    resp = Response()
    resp.headers['Content-Type'] = 'application/x-protobuf'
    resp.headers['Content-Encoding'] = 'snappy'

    query = msg.queries[0]
    metric_name = ''
    for matcher in query.matchers:
        if matcher.name == '__name__':
            metric_name = metrics_client.get_dt_metric_from_prom(matcher.value)

    metrics_client.prefetch_dimensions(metric_name)

    matchers = []
    for matcher in query.matchers:
        if matcher.name != '__name__':
            dt_matcher_name = metrics_client.get_dimension_from_label(matcher.name)
            entity_client.prefetch_entities(dt_matcher_name)

            dt_matcher_value = entity_client.get_entity_id(matcher.value)
            matchers.append(f"eq({dt_matcher_name},{dt_matcher_value})")

    res = metrics_client.query_metric(metric_name, query.start_timestamp_ms, query.end_timestamp_ms, matchers)

    read_response = remote_pb2.ReadResponse()
    query_result = read_response.results.add()

    if 'error' in res:
        log.error("Dytrace returned an error: %s", res['error'])
        resp.set_data(snappy.compress(read_response.SerializeToString()))
        return resp

    for dt_result in res.get('result', []):
        add_result(query_result, dt_result)

    resp.set_data(snappy.compress(read_response.SerializeToString()))

    return resp

@app.route('/write', methods=["POST"])
def write():
    msg = remote_pb2.WriteRequest()
    msg.ParseFromString(snappy.uncompress(request.data))

    to_send = []
    for timeseries in msg.timeseries:

        dt_dimensions = []
        for label in timeseries.labels:
            if label.name == '__name__':
                dt_dimensions.insert(0, label.value)
            else:
                dt_dimensions.append(f"{label.name}={label.value}")

        dt = ",".join(dt_dimensions)

        for sample in timeseries.samples:
            if str(sample.value) != "nan":
                to_send.append(f"{dt} {str(sample.value)} {str(sample.timestamp)}")

    metrics_client.ingest_metric("\n".join(to_send))

    return 'OK'

def add_result(query_result, result):
    metric_name_elements = re.sub(r'[^a-z0-9:]', "_", result.get('metricId','').lower()).split(":")

    metric_name = metric_name_elements[0]
    if metric_name_elements[0] == 'builtin' or metric_name_elements[0] == 'ext':
        metric_name += f":{metric_name_elements[1]}"

    for data in result['data']:
        timeseries = query_result.timeseries.add()
        timeseries.labels.add(name="__name__", value=metric_name)

        for dimension in data.get('dimensions', []):
            if dimension not in dim_map:
                dim_map[dimension] = entity_client.get_entity_name(dimension)

        for dimension_name, dimension_value in data.get('dimensionMap', {}).items():
            timeseries.labels.add(name=metrics_client.get_label_from_dimension(dimension_name), value=dim_map[dimension_value])

        for i, timestamp in enumerate(data.get('timestamps', [])):
            value = data['values'][i]
            if value is not None:
                timeseries.samples.add(value = value, timestamp = timestamp)

if __name__ == "__main__":
    app.run()
