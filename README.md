# NGINX Instance Counter

## Description

This tool helps tracking NGINX Plus instances managed by NGINX Controller and NGINX Instance Manager

It has been tested against:

- NGINX Controller 3.18, 3.18.2
- NGINX Instance Manager 1.0.1

Communication to NGINX Controller / NGINX Instance Manager is based on REST API, current features are:

- REST API mode
  - /instances - returns JSON output
  - /metrics - returns Prometheus compliant output
- Push mode
  - POSTs instance statistics to a user-defined HTTP(S) URL (STATS_PUSH_MODE: CUSTOM)
  - Pushes instance statistics to pushgateway (STATS_PUSH_MODE: NGINX_PUSH)
  - Basic authentication support
  - User-defined push interval (in seconds)

## Deployment modes

Pull mode: Instance Counter fetches stats

<img src="./images/nginx-imagecounter-pull.jpg"/>

Push mode: Instance Counter pushes stats to a remote data collection and visualization environment (suitable for distributed setups)

<img src="./images/nginx-imagecounter-push.jpg"/>

## Prerequisites

- Kubernetes or Openshift cluster
- Private registry to push the NGINX Instance Counter image
- NGINX Controller 3.18, 3.18.2 or NGINX Instance Manager 1.0.1

# How to build

## For Kubernetes/Openshift

The NGINX Instance Counter image is available on Docker Hub as:

```
fiorucci/nginx-instance-counter:1.6
```

The 1.instancecounter.yaml file references that by default.

If you need to build and push NGINX your own image to a private registry:

```
git clone fabriziofiorucci/NGINX-InstanceCounter
cd NGINX-InstanceCounter/nginx-instance-counter

docker build --no-cache -t PRIVATE_REGISTRY:PORT/nginx-instance-counter:1.6 .
docker push PRIVATE_REGISTRY:PORT/nginx-instance-counter:1.6
```

## As a native python application

NGINX Instance Counter requires:

- Any Linux distribution
- Python 3 (tested on 3.9+)
- [Flask framework](https://flask.palletsprojects.com/en/2.0.x/)
- [Requests](https://docs.python-requests.org/en/master/)

nginx-instance-counter/nicstart.sh is a sample script to run NGINX Instance Counter from bash

# How to deploy

## For Kubernetes/Openshift

```
cd NGINX-InstanceCounter/manifests
```

Edit 1.instancecounter.yaml to customize:

- image name:
  - To be set to your private registry image (only if not using the image available on Docker Hub)
- environment variables:
  - NGINX_CONTROLLER_TYPE - either NGINX_CONTROLLER or NGINX_INSTANCE_MANAGER
  - NGINX_CONTROLLER_FQDN - the FQDN of your NGINX Controller / NGINX Instance Manager instance - format must be http[s]://FQDN:port
  - NGINX_CONTROLLER_USERNAME - the username for NGINX Controller authentication
  - NGINX_CONTROLLER_PASSWORD - the password for NGINX Controller authentication

  - STATS_PUSH_ENABLE - if set to "true" push mode is enabled, disabled it set to "false"
  - STATS_PUSH_MODE - either CUSTOM or NGINX_PUSH, to push (HTTP POST) JSON to custom URL and to push metrics to pushgateway, respectively
  - STATS_PUSH_URL - the URL where to push statistics
  - STATS_PUSH_INTERVAL - the interval in seconds between two consecutive push
  - STATS_PUSH_USERNAME - (optional) the username for POST Basic Authentication
  - STATS_PUSH_PASSWORD - (optional) the password for POST Basic Authentication
- Ingress host:
  - By default it is set to counter.nginx.ff.lan

For standalone operations (ie. REST API + optional push to custom URL):

```
kubectl apply -f 0.ns.yaml
kubectl apply -f 1.instancecounter.yaml
```

To push statistics to pushgateway also apply:

```
kubectl apply -f 2.prometheus.yaml
kubectl apply -f 3.grafana.yaml
kubectl apply -f 4.pushgateway.yaml
```

By default 2.prometheus.yaml is configured for push mode, it must be edited decommenting the relevant section for pull mode

To setup visualization:

- Grafana shall be configured with a Prometheus datasource using by default http://prometheus.nginx.ff.lan
- Import the dashboard NGINX-InstanceCounter-dashboard.json in Grafana

Service names created by default as Ingress resources are:

- counter.nginx.ff.lan - REST API and Prometheus scraping endpoint
- pushgateway.nginx.ff.lan - Pushgateway web GUI
- prometheus.nginx.ff.lan - Prometheus web GUI
- grafana.nginx.ff.lan - Grafana visualization web GUI

## As a native python application

Edit nginx-instance-counter/nicstart.sh and run it

# Usage

## REST API mode

To get instance statistics in JSON format:

NGINX Instance Manager

```
$ curl -s http://counter.nginx.ff.lan/instances | jq
{
  "subscription": {
    "id": "NGX-Subscription-1-TRL-XXXXXX",
    "type": "INSTANCE_MANAGER",
    "version": "2"
  },
  "instances": [
    {
      "nginx_plus_online": 0,
      "nginx_oss_online": 1
    }
  ],
  "details": [
    {
      "instance_id": "f821413d-9664-4fb9-b8b9-595490912bb7",
      "uname": "Linux testserver 5.7.6 #1 SMP PREEMPT Fri Jun 26 17:39:22 CEST 2020 x86_64 QEMU Virtual CPU version 2.5+ AuthenticAMD GNU/Linux",
      "containerized": "False",
      "type": "oss",
      "version": "1.20.1"
    }
  ]
}
```

NGINX Controller

```
$ curl -s http://counter.nginx.ff.lan/instances | jq
{
  "subscription": {
    "id": "NGX-Subscription-1-TRL-XXXXXX",
    "type": "NGINX Controller",
    "version": "3.18.2"
  },
  "instances": [
    {
      "location": "unspecified",
      "nginx_plus_online": 2,
      "nginx_plus_offline": 0
    }
  ],
  "details": [
    {
      "instance_id": "3b074010-df8d-498c-af41-d54c4ffb1021",
      "uname": "linux Ubuntu 18.04.5 LTS (Bionic Beaver) x86_64 QEMU Virtual CPU version 2.5+",
      "containerized": "",
      "type": "plus",
      "version": "1.19.10"
    },
    {
      "instance_id": "c891eebe-4def-459e-bb29-eb715e7846a8",
      "uname": "linux Ubuntu 18.04.5 LTS (Bionic Beaver) x86_64 QEMU Virtual CPU version 2.5+",
      "containerized": "",
      "type": "plus",
      "version": "1.19.10"
    }
  ]
}
```

Prometheus endpoint:

Pulling from NGINX Instance Manager

```
$ curl -s http://counter.nginx.ff.lan/metrics
# HELP nginx_oss_online_instances Online NGINX OSS instances
# TYPE nginx_oss_online_instances gauge
nginx_oss_online_instances{subscription="NGX-Subscription-1-TRL-064788",instanceType="INSTANCE_MANAGER",instanceVersion="2"} 2
# HELP nginx_plus_online_instances Online NGINX Plus instances
# TYPE nginx_plus_online_instances gauge
nginx_plus_online_instances{subscription="NGX-Subscription-1-TRL-064788",instanceType="INSTANCE_MANAGER",instanceVersion="2"} 0
```

Pulling from NGINX Controller

```
$ curl -s http://counter.nginx.ff.lan/metrics
# HELP nginx_plus_online_instances Online NGINX Plus instances
# TYPE nginx_plus_online_instances gauge
nginx_plus_online_instances{subscription="NGX-Subscription-1-TRL-046027",instanceType="NGINX Controller",instanceVersion="3.18.2",location="test"} 0
# HELP nginx_plus_offline_instances Offline NGINX Plus instances
# TYPE nginx_plus_offline_instances gauge
nginx_plus_offline_instances{subscription="NGX-Subscription-1-TRL-046027",instanceType="NGINX Controller",instanceVersion="3.18.2",location="test"} 0
# HELP nginx_plus_online_instances Online NGINX Plus instances
# TYPE nginx_plus_online_instances gauge
nginx_plus_online_instances{subscription="NGX-Subscription-1-TRL-046027",instanceType="NGINX Controller",instanceVersion="3.18.2",location="unspecified"} 2
# HELP nginx_plus_offline_instances Offline NGINX Plus instances
# TYPE nginx_plus_offline_instances gauge
nginx_plus_offline_instances{subscription="NGX-Subscription-1-TRL-046027",instanceType="NGINX Controller",instanceVersion="3.18.2",location="unspecified"} 283
```

## Push mode to custom URL

Sample unauthenticated POST payload:

```
POST /callHome HTTP/1.1
Host: 192.168.1.18
User-Agent: python-requests/2.22.0
Accept-Encoding: gzip, deflate
Accept: */*
Connection: keep-alive
Content-Type: application/json
Content-Length: 267

{
  "subscription": {
    "id": "NGX-Subscription-1-TRL-XXXXXX",
    "type": "INSTANCE_MANAGER",
    "version": "2"
  },
  "instances": [
    {
      "nginx_plus_online": 0,
      "nginx_oss_online": 1
    }
  ],
  "details": [
    {
      "instance_id": "f821413d-9664-4fb9-b8b9-595490912bb7",
      "uname": "Linux vm-gw 5.7.6 #1 SMP PREEMPT Fri Jun 26 17:39:22 CEST 2020 x86_64 QEMU Virtual CPU version 2.5+ AuthenticAMD GNU/Linux",
      "containerized": "False",
      "type": "oss",
      "version": "1.20.1"
    }
  ]
}
```

Sample POST payload with Basic Authentication

```
POST /callHome HTTP/1.1
Host: 192.168.1.18
User-Agent: python-requests/2.22.0
Accept-Encoding: gzip, deflate
Accept: */*
Connection: keep-alive
Content-Type: application/json
Content-Length: 267
Authorization: Basic YWE6YmI=

{
  "subscription": {
    "id": "NGX-Subscription-1-TRL-XXXXXX",
    "type": "INSTANCE_MANAGER",
    "version": "2"
  },
  "instances": [
    {
      "nginx_plus_online": 0,
      "nginx_oss_online": 1
    }
  ],
  "details": [
    {
      "instance_id": "f821413d-9664-4fb9-b8b9-595490912bb7",
      "uname": "Linux vm-gw 5.7.6 #1 SMP PREEMPT Fri Jun 26 17:39:22 CEST 2020 x86_64 QEMU Virtual CPU version 2.5+ AuthenticAMD GNU/Linux",
      "containerized": "False",
      "type": "oss",
      "version": "1.20.1"
    }
  ]
}
```


# Visualization

<img src="./images/grafana.1.jpg"/>

<img src="./images/grafana.2.jpg"/>
