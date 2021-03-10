# Prometheus remote storage adapter for Dynatrace

This is an experiment to use Dynatrace as remote storage for Prometheus. It implements both, the `remote_read` as well as the `remote_write` functionality for Prometheus.

## Getting Started
### Installing dependencies
```
### If you use venv
# python3 -m pip install --user virtualenv
# python3 -m venv env
# source env/bin/activate

python3 -m pip install -r requirements.txt
```

### Remote Storage Adapter Configuration
You'll need to configure your tenant url and API token (API v2 with the metrics read/write capabilities). This can be done as ENV variables or inside an [.env file](https://pypi.org/project/python-dotenv/).

```
export DT_TENANT=<your_tenant_url>
export DT_API_TOKEN=<your_apiv2_token>
```

Then you're good to go:
```
python3 main.py
```

### Prometheus Configuration
Point your Prometheus instance to this application. See [documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#remote_write) for further configuration options.

Eg. if your Prometheus is running in a docker container use:
```
remote_read:
 - url: http://host.docker.internal:5000/read

remote_write:
- url: http://host.docker.internal:5000/write
  queue_config:
    max_samples_per_send: 1000
  metadata_config:
    send: true
```

## Limitations
There are some limitation:

### Dyntrace vs Prometheus metric naming
Metric and label/dimension naming rules between Dynatrace and Prometheus are varying slightly. Therefore following conversion will be applied:

`.`, `,` and `-` will be replaced by `_` on remote read (from Dynatrace)

`:` will be replace by `_` on remote write (to Dynatrace)


If you try to query Prometheus for an invalid metric name like `builtin:synthetic.http.duration.geo` (as `.` is not an allowed character) you'll see a message like:
```
Error executing query: invalid parameter "query": 1:18: parse error: unexpected character: '.'
```
As a workaround use the alternative syntax:

```
{__name__="builtin:synthetic.http.duration.geo"}
```

### Prometheus does not list remote metric names
As of now you can not get autocomplete of Dynatrace metrics in the UI. This is a known limitation for remote storage and is being addressed in [prometheus/prometheus#7076](https://github.com/prometheus/prometheus/pull/7076).
