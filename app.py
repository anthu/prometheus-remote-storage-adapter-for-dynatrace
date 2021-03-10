import requests
import remote_pb2 
import types_pb2
import snappy

from flask import Flask, Response, request
from google.protobuf.json_format import MessageToJson

app = Flask(__name__)
app.config.from_pyfile('config.py')

dim_map = {}

@app.route('/read', methods=["POST"])
def read():
    msg = remote_pb2.ReadRequest()
    msg.ParseFromString(snappy.uncompress(request.data))
    app.logger.debug(msg)

    resp = Response()
    resp.headers['Content-Type'] = 'application/x-protobuf'
    resp.headers['Content-Encoding'] = 'snappy'
    
    query = msg.queries[0]
    res = query_metric(query.matchers[0].value, query.start_timestamp_ms, query.end_timestamp_ms)

    read_response = remote_pb2.ReadResponse()
    query_result = read_response.results.add()

    if 'error' in res:
        app.logger.error(f"Dytrace returned an error: {res['error']}")
        resp.set_data(snappy.compress(read_response.SerializeToString()))
        return resp

    if res['totalCount'] > 0:
        for dt_result in res['result']:
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
    headers = {'Authorization': f"Api-Token {app.config['DT_API_TOKEN']}"}

    x = requests.get(url, headers = headers)

    return(x.json()['displayName'])

def ingest_metric(content):
    url = f"https://{app.config['DT_TENANT']}/api/v2/metrics/ingest"
    headers = {'Authorization': f"Api-Token {app.config['DT_API_TOKEN']}", 'Content-Type': 'text/plain'}

    requests.post(url, headers = headers, data = content)

def query_metric(metric, from_ts, to_ts):
    url = (
        f"https://{app.config['DT_TENANT']}/api/v2/metrics/query?" \
        f"metricSelector={metric}&" \
        f"from={from_ts}&" \
        f"to={to_ts}"
    )
    headers = {'Authorization': f"Api-Token {app.config['DT_API_TOKEN']}"}

    x = requests.get(url, headers = headers)
    return(x.json())

def add_result(query_result, result):
    metric_name = result['metricId'].replace('.','_')
    
    for data in result['data']:
        timeseries = query_result.timeseries.add()
        timeseries.labels.add(name="__name__", value=metric_name)

        for dimension in data['dimensions']:
            if dimension not in dim_map:
                dim_map[dimension] = get_entity(dimension)

        for dimension_name, dimension_value in data['dimensionMap'].items():
            timeseries.labels.add(name=dimension_name.replace('.','_'), value=dim_map[dimension_value])
        
        for i, timestamp in enumerate(data['timestamps']):
            value = data['values'][i]
            if value != None:
                timeseries.samples.add(value = value, timestamp = timestamp)

if __name__ == "__main__":
    app.run()
