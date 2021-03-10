
import requests
import remote_pb2 
import types_pb2
import snappy

from flask import Flask, Response, request
from google.protobuf.json_format import MessageToJson

app = Flask(__name__)
app.config.from_pyfile('config.py')

@app.route('/read', methods=["POST"])
def read():
    msg = remote_pb2.ReadRequest()
    msg.ParseFromString(snappy.uncompress(request.data))
    
    query = msg.queries[0]
    res = query_dt(query.matchers[0].value, query.start_timestamp_ms, query.end_timestamp_ms)

    read_response = remote_pb2.ReadResponse()
    query_result = read_response.results.add()

    if 'error' not in res and res['totalCount'] > 0:
        for result in res['result']:
            metric_name = result['metricId'].replace('.','_')

            for data in result['data']:
                timeseries = query_result.timeseries.add()
                timeseries.labels.add(name="__name__", value=metric_name)

                for dim, dim_val in data['dimensionMap'].items():
                    timeseries.labels.add(name=dim.replace('.','_'), value=dim_val)
                
                for i, timestamp in enumerate(data['timestamps']):
                    value = data['values'][i]
                    if value != None:
                        timeseries.samples.add(value = value, timestamp = timestamp)

    resp = Response(snappy.compress(read_response.SerializeToString()))
    resp.headers['Content-Type'] = 'application/x-protobuf'
    resp.headers['Content-Encoding'] = 'snappy'
    
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

    send_to_dt("\n".join(to_send))

    return 'OK'

def send_to_dt(content):
    url = f"{app.config['DT_TENANT']}/api/v2/metrics/ingest"
    headers = {'Authorization': f"Api-Token {app.config['DT_API_TOKEN']}", 'Content-Type': 'text/plain'}

    requests.post(url, headers = headers, data = content)

def query_dt(metric, from_ts, to_ts):
    url = (
        f"{app.config['DT_TENANT']}/api/v2/metrics/query?" \
        f"metricSelector={metric}&" \
        f"from={from_ts}&" \
        f"to={to_ts}"
    )
    headers = {'Authorization': f"Api-Token {app.config['DT_API_TOKEN']}"}

    x = requests.get(url, headers = headers)
    return(x.json())

if __name__ == "__main__":
    app.run()
