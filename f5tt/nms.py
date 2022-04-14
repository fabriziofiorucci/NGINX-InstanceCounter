import os
import sys
import ssl
import json
import sched,time,datetime
import requests
import time
import threading
import smtplib
import urllib3.exceptions
import base64
from requests import Request, Session
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from email.message import EmailMessage

import cveDB
import f5ttCH

this = sys.modules[__name__]

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

this.nms_fqdn=''
this.nms_username=''
this.nms_password=''
this.nms_proxy={}

# Module initialization
def init(fqdn,username,password,proxy,nistApiKey,ch_host,ch_port,ch_user,ch_pass,sample_interval):
  this.nms_fqdn=fqdn
  this.nms_username=username
  this.nms_password=password
  this.nms_proxy=proxy

  print('Initializing NMS [',this.nms_fqdn,']')

  cveDB.init(nistApiKey = nistApiKey,proxy=proxy)

  f5ttCH.init(ch_host,ch_port,ch_user,ch_pass)
  t=threading.Thread(target=pollingThread,args=(sample_interval,))
  t.start()


# Periodic sample thread running every 'sample_interval' minutes
def pollingThread(sample_interval):
  print('Starting polling thread every',sample_interval,'minutes')

  while True:
    now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    instancesJson,retcode = nmsInstances(mode='JSON')
    print(now,'Collecting instances usage',instancesJson['instances'] if 'instances' in instancesJson else 'invalid')

    if 'instances' in instancesJson:
      query='insert into f5tt.tracking (ts,data) values (\''+str(now)+'\',\''+json.dumps(instancesJson['instances'])+'\')'

      f5ttCH.connect()
      out=f5ttCH.execute(query)
      f5ttCH.close()

    time.sleep(sample_interval)

### NGINX Management System REST API

def nmsRESTCall(method,uri):
  s = Session()
  req = Request(method,this.nms_fqdn+uri,auth=(this.nms_username,this.nms_password))

  p = s.prepare_request(req)
  s.proxies = this.nms_proxy
  res = s.send(p,verify=False)

  if res.status_code == 200:
    data = res.json()
  else:
    data = {}

  return res.status_code,data


### NGINX Management System query functions

# Returns NGINX OSS/Plus instances managed by NMS in JSON format
def nmsInstances(mode):
  # Fetching NMS license
  status,license = nmsRESTCall(method='GET',uri='/api/platform/v1/license')

  if status != 200:
    return {'error': 'fetching license failed'},status

  # Fetching NMS system information
  status,system = nmsRESTCall(method='GET',uri='/api/platform/v1/systems')

  if status != 200:
    return {'error': 'fetching systems information failed'},status

  subscriptionId=license['currentStatus']['subscription']['id']
  instanceType=license['currentStatus']['state']['currentInstance']['features'][0]['id']
  instanceVersion=license['currentStatus']['state']['currentInstance']['version']
  instanceSerial=license['currentStatus']['state']['currentInstance']['id']
  totalManaged=0

  plusManaged=0
  for i in system['items']:
    for instance in i['nginxInstances']:
      totalManaged+=1
      if instance['build']['nginxPlus'] == True:
        plusManaged+=1

  output=''

  subscriptionDict = {}
  subscriptionDict['id'] = subscriptionId
  subscriptionDict['type'] = instanceType
  subscriptionDict['version'] = instanceVersion
  subscriptionDict['serial'] = instanceSerial

  output = {}
  output['subscription'] = subscriptionDict
  output['details'] = []

  onlineNginxPlus = 0
  onlineNginxOSS = 0

  for i in system['items']:
    systemId=i['uid']

    # Fetch system details
    status,systemDetails = nmsRESTCall(method='GET',uri='/api/platform/v1/systems/'+systemId+'?showDetails=true')
    if status != 200:
      return {'error': 'fetching system details failed for '+systemId},status

    for instance in i['nginxInstances']:
      # Fetch instance details
      instanceUID = instance['uid']

      status,instanceDetails = nmsRESTCall(method='GET',uri='/api/platform/v1/systems/'+systemId+'/instances/'+instanceUID)
      if status != 200:
        return {'error': 'fetching instance details failed for '+systemId+' / '+instanceUID},status

      # Fetch CVEs
      allCVE=cveDB.getNGINX(version=instanceDetails['build']['version'])

      detailsDict = {}
      detailsDict['instance_id'] = instance['uid']
      detailsDict['osInfo'] = systemDetails['osRelease']
      detailsDict['hypervisor'] = systemDetails['processor'][0]['hypervisor']
      detailsDict['type'] = "oss" if instanceDetails['build']['nginxPlus'] == False else "plus"
      detailsDict['version'] = instanceDetails['build']['version']
      detailsDict['last_seen'] = instance['status']['lastStatusReport']
      detailsDict['state'] = instance['status']['state']
      detailsDict['createtime'] = instance['startTime']
      detailsDict['modules'] = instanceDetails['loadableModules']
      detailsDict['networkconfig'] = {}
      detailsDict['networkconfig']['networkInterfaces'] = systemDetails['networkInterfaces']
      detailsDict['hostname'] = systemDetails['hostname']
      detailsDict['name'] = systemDetails['displayName']
      detailsDict['CVE'] = []
      detailsDict['CVE'].append(allCVE)

      if detailsDict['state'] == 'online':
        onlineNginxOSS = onlineNginxOSS + 1 if detailsDict['type'] == "oss" else onlineNginxOSS
        onlineNginxPlus = onlineNginxPlus + 1 if detailsDict['type'] == "plus" else onlineNginxPlus

      output['details'].append(detailsDict)

  instancesDict = {}
  instancesDict['nginx_plus'] = {}
  instancesDict['nginx_oss'] = {}
  instancesDict['nginx_plus']['managed'] = plusManaged
  instancesDict['nginx_plus']['online'] = onlineNginxPlus
  instancesDict['nginx_plus']['offline'] = plusManaged - onlineNginxPlus
  instancesDict['nginx_oss']['managed'] = int(totalManaged)-int(plusManaged)
  instancesDict['nginx_oss']['online'] = onlineNginxOSS
  instancesDict['nginx_oss']['offline'] = int(totalManaged)-int(plusManaged)-onlineNginxOSS

  output['instances'] = instancesDict

  if mode == 'PROMETHEUS' or mode == 'PUSHGATEWAY':
    if mode == 'PROMETHEUS':
      pOutput = '# HELP nginx_oss_online_instances Online NGINX OSS instances\n'
      pOutput = pOutput + '# TYPE nginx_oss_online_instances gauge\n'

    pOutput = pOutput + 'nginx_oss_online_instances{subscription="'+output['subscription']['id']+'",instanceType="'+output['subscription']['type']+'",instanceVersion="'+output['subscription']['version']+'",instanceSerial="'+output['subscription']['serial']+'"} '+str(int(totalManaged)-int(plusManaged))+'\n'

    if mode == 'PROMETHEUS':
      pOutput = pOutput + '# HELP nginx_plus_online_instances Online NGINX Plus instances\n'
      pOutput = pOutput + '# TYPE nginx_plus_online_instances gauge\n'

    pOutput = pOutput + 'nginx_plus_online_instances{subscription="'+subscriptionId+'",instanceType="'+instanceType+'",instanceVersion="'+instanceVersion+'",instanceSerial="'+instanceSerial+'"} '+str(plusManaged)+'\n'

    output = pOutput

  return output,200


# Returns the CVE-centric JSON
def nmsCVEjson():
  fullJSON,retcode = nmsInstances(mode='JSON')
  cveJSON = {}

  for d in fullJSON['details']:
    nginxHostname = d['hostname']
    nginxVersion = d['version']

    for cve in d['CVE'][0]:
      if cve not in cveJSON:
        cveJSON[cve] = d['CVE'][0][cve]
        cveJSON[cve]['devices'] = []

      deviceJSON = {}
      deviceJSON['hostname'] = nginxHostname
      deviceJSON['version'] = nginxVersion

      cveJSON[cve]['devices'].append(deviceJSON)

  return cveJSON,200


# Returns the time-based instances usage distribution JSON
def nmsTimeBasedJson(monthStats,hourInterval):
  output = {}
  output['subscription'] = {}
  output['instances'] = []

  # Fetching NMS license
  status,license = nmsRESTCall(method='GET',uri='/api/platform/v1/license')

  if status == 200:
    output['subscription']['id']=license['currentStatus']['subscription']['id']
    output['subscription']['type']=license['currentStatus']['state']['currentInstance']['features'][0]['id']
    output['subscription']['version']=license['currentStatus']['state']['currentInstance']['version']
    output['subscription']['serial']=license['currentStatus']['state']['currentInstance']['id']

  # Clickhouse data aggregation
  query = " \
    SELECT \
      min(ts) as from, \
      max(ts) as to, \
      max(toInt64(JSONExtractRaw(data, 'nginx_oss', 'managed'))) AS nginx_oss_managed, \
      max(toInt64(JSONExtractRaw(data, 'nginx_oss', 'online'))) AS nginx_oss_online, \
      max(toInt64(JSONExtractRaw(data, 'nginx_oss', 'offline'))) AS nginx_oss_offline, \
      max(toInt64(JSONExtractRaw(data, 'nginx_plus', 'managed'))) AS nginx_plus_managed, \
      max(toInt64(JSONExtractRaw(data, 'nginx_plus', 'online'))) AS nginx_plus_online, \
      max(toInt64(JSONExtractRaw(data, 'nginx_plus', 'offline'))) AS nginx_plus_offline \
    FROM f5tt.tracking \
    WHERE ts >= (select timestamp_sub(month,"+str(-monthStats)+",toStartOfMonth(now()))) \
    AND ts < (addDays(toStartOfMonth(addMonths(now() + toIntervalMonth(1),"+str(monthStats)+")),-1)) \
    GROUP BY toStartOfInterval(toDateTime(ts), toIntervalHour("+str(hourInterval)+")) \
    ORDER BY max(ts) ASC \
  "

  f5ttCH.connect()
  out=f5ttCH.execute(query)
  f5ttCH.close()

  if out != None:
    if out != []:
      for tuple in out:
        if len(tuple) == 8:
          item = {}
          item['ts'] = {}
          item['ts']['from'] = str(tuple[0])
          item['ts']['to'] = str(tuple[1])
          item['nginx_oss'] = {}
          item['nginx_oss']['managed'] = tuple[2]
          item['nginx_oss']['online'] = tuple[3]
          item['nginx_oss']['offline'] = tuple[4]
          item['nginx_plus'] = {}
          item['nginx_plus']['managed'] = tuple[5]
          item['nginx_plus']['online'] = tuple[6]
          item['nginx_plus']['offline'] = tuple[7]

          output['instances'].append(item)
    return output,200
  else:
    return {"message":"ClickHouse unreachable"},503
