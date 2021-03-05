
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
    
    json = MessageToJson(msg)
    query = msg.queries[0]
    res = query_dt(query.matchers[0].value, query.start_timestamp_ms, query.end_timestamp_ms)

    read_response = remote_pb2.ReadResponse()
    query_result = read_response.results.add()

    if not res['error'] and res['totalCount'] > 0:
        for result in res['result']:
            metric_name = result['metricId'].replace(':','__').replace('.','_')

            for data in result['data']:
                timeseries = query_result.timeseries.add()

                label = timeseries.labels.add()
                label.name = "__name__"
                label.value = metric_name

                for dim, dim_val in data['dimensionMap'].items():
                    label = timeseries.labels.add()
                    label.name = dim.replace(':','__').replace('.','_')
                    label.value = dim_val
                
                for i, timestamp in enumerate(data['timestamps']):
                    value = data['values'][i]
                    if value != None:
                        sample = timeseries.samples.add()
                        sample.value = value
                        sample.timestamp = timestamp

    resp = Response(snappy.compress(read_response.SerializeToString()))
    resp.headers['Content-Type'] = 'application/x-protobuf'
    resp.headers['Content-Encoding'] = 'snappy'
    
    return resp

@app.route('/write', methods=["POST"])
def write():
    msg = remote_pb2.WriteRequest()
    msg.ParseFromString(snappy.uncompress(request.data))
    json = MessageToJson(msg)

    to_send = ""
    for timeseries in msg.timeseries:
        
        dt_name = dt_dimensions = ""

        for label in timeseries.labels:
            if label.name == '__name__':
                dt_name = label.value
            else:
                dt_dimensions += label.name + "=" + label.value + ","

        dt = dt_name + "," + dt_dimensions.rstrip(',')

        for sample in timeseries.samples:
            if str(sample.value) != "nan":
                to_send += dt + " " + str(sample.value) + " " + str(sample.timestamp) + "\n"

    f = open("to_send.txt", "w")
    f.write(to_send)
    f.close()

    send_to_dt(to_send)

    return 'OK'

def send_to_dt(content):
    url = app.config["DT_TENANT"] + '/api/v2/metrics/ingest'
    headers = {'Authorization': 'Api-Token ' + app.config["DT_API_TOKEN"], 'Content-Type': 'text/plain'}

    x = requests.post(url, headers = headers, data = content)
    print(x.content)

def query_dt(metric, from_ts, to_ts):
    url = app.config["DT_TENANT"] + '/api/v2/metrics/query?metricSelector=' + metric + "&from=" + str(from_ts) + "&to=" + str(to_ts)
    headers = {'Authorization': 'Api-Token ' + app.config["DT_API_TOKEN"]}

    x = requests.get(url, headers = headers)
    print(x.json())
    return(x.json())

if __name__ == "__main__":
    app.run()
