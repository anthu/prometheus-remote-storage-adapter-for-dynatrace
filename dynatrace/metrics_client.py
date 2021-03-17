import re
import requests
from bidict import bidict

class CachedMetricsClient:

    PAGE_SIZE = 500

    def __init__(self, api_endpoint, api_token, cache_timeout = 0):
        self.endpoint = f"https://{api_endpoint}/api/v2/metrics"
        self.headers = {
            'Authorization': f"Api-Token {api_token}"
        }
        self.cache_timeout = cache_timeout
        self.dimension_label_bidict = bidict()
        self.metrics_discovered = []
        self.metrics_dict = {}
        self.prefetch_metrics()

    def get_dt_metric_from_prom(self, prom_metric_name):
        metric_candidate = re.sub(r'[^a-z0-9:]', "_", prom_metric_name.lower())
        return self.metrics_dict.get(metric_candidate)

    def get_label_from_dimension(self, dimension_name):
        return self.dimension_label_bidict.get(dimension_name.lower())

    def get_dimension_from_label(self, label_name):
        return self.dimension_label_bidict.inverse.get(label_name.lower())

    def prefetch_dimensions(self, metric_id):
        if metric_id in self.metrics_discovered:
            return

        url = f"{self.endpoint}/{metric_id}"
        
        resp = requests.get(url, headers = self.headers).json()
        for dimension in resp.get("dimensionDefinitions", []):
            tar = re.sub(r'[^a-z0-9:]', "_", dimension.get('key','').lower())
            self.dimension_label_bidict.forceput(dimension.get("key"), tar)
        
        self.metrics_discovered.append(metric_id)

    def prefetch_metrics(self, next_page_key=None):
        url = self.endpoint
        if next_page_key is not None:
            params = {
                "nextPageKey": next_page_key
            }
        else:
            params = {
                "fields": "metricId",
                "pageSize": self.PAGE_SIZE
            }

        resp = requests.get(url, params = params, headers = self.headers).json()

        for metric in resp.get("metrics", []):
            dt_metric = metric.get('metricId')
            prom_metric = re.sub(r'[^a-z0-9:]', "_", dt_metric.lower())
            self.metrics_dict[prom_metric] = dt_metric


        if resp.get("nextPageKey") is not None:
            self.prefetch_metrics(resp.get("nextPageKey"))

    def query_metric(self, metric, from_ts, to_ts, matchers):
        url = f"{self.endpoint}/query"
        params = {
            "metricSelector": metric,
            "from": from_ts,
            "to": to_ts
        }

        if len(matchers) > 0:
            params["metricSelector"] += f":filter(and({','.join(matchers)}))"

        return requests.get(url, params = params, headers = self.headers).json()

    def ingest_metric(self, content):
        url = f"{self.endpoint}/ingest"
        headers = self.headers 
        headers['Content-Type'] = 'text/plain'

        requests.post(url, headers = headers, data = content)
