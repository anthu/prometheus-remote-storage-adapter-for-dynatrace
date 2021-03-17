import re
from bidict import bidict
import requests
import snappy
from flask import Flask, Response, request
from flask.logging import create_logger
from proto import remote_pb2


app = Flask(__name__)
app.config.from_pyfile('config.py')

log = create_logger(app)

dim_map = {}
dimension_name_bidict = bidict()

@app.route('/read', methods=["POST"])
def read():
    msg = remote_pb2.ReadRequest()
    msg.ParseFromString(snappy.uncompress(request.data))

    resp = Response()
    resp.headers['Content-Type'] = 'application/x-protobuf'
    resp.headers['Content-Encoding'] = 'snappy'

    query = msg.queries[0]
    metric_name = ''
    matchers = []
    for matcher in query.matchers:
        if matcher.name == '__name__':
            metric_name = matcher.value
        else:
            dt_matcher_name = dimension_name_bidict.inverse.get(matcher.name, matcher.name)
            matchers.append(f"eq({dt_matcher_name},{matcher.value})")

    res = query_metric(metric_name, query.start_timestamp_ms, query.end_timestamp_ms, matchers)

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

    ingest_metric("\n".join(to_send))

    return 'OK'

def get_entity(dimension):
    url = f"https://{app.config['DT_TENANT']}/api/v2/entities/{dimension}"
    headers = {
        'Authorization': f"Api-Token {app.config['DT_API_TOKEN']}"
    }

    resp = requests.get(url, headers = headers)

    return resp.json().get('displayName', dimension)

def ingest_metric(content):
    url = f"https://{app.config['DT_TENANT']}/api/v2/metrics/ingest"
    headers = {
        'Authorization': f"Api-Token {app.config['DT_API_TOKEN']}", 
        'Content-Type': 'text/plain'
    }

    requests.post(url, headers = headers, data = content)

def query_metric(metric, from_ts, to_ts, matchers):
    url = (
        f"https://{app.config['DT_TENANT']}/api/v2/metrics/query"
    )
    params = {
        "metricSelector": metric,
        "from": from_ts,
        "to": to_ts
    }

    if len(matchers) > 0:
        params["metricSelector"] += f":filter(or({','.join(matchers)}))"

    headers = {'Authorization': f"Api-Token {app.config['DT_API_TOKEN']}"}
    
    x = requests.get(url, params = params, headers = headers)
    return(x.json())

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
                dim_map[dimension] = get_entity(dimension)

        for dimension_name, dimension_value in data.get('dimensionMap', {}).items():
            prom_dim_name = re.sub(r'[^a-z0-9]', "_", dimension_name.lower())
            dimension_name_bidict.forceput(dimension_name, prom_dim_name)
            timeseries.labels.add(name=prom_dim_name, value=dim_map[dimension_value])

        for i, timestamp in enumerate(data.get('timestamps', [])):
            value = data['values'][i]
            if value is not None:
                timeseries.samples.add(value = value, timestamp = timestamp)

if __name__ == "__main__":
    app.run()
